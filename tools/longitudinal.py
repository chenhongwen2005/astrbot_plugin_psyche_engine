#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""长程累积实验：同一题材循环输入 N 轮，看状态如何一步步走到确诊。

stress_induce.py 测的是「单条话术能不能被听见」，本脚本测的是另一半：
「持续听见之后，人会不会真的病」。两者缺一不可——插件主张「持续性虐待
最终致病、且病程有迟滞」，这个主张只能用长程曲线来验证，10 条话术永远
看不到确诊（这是设计预期，不是缺陷）。

用法：
    python tools/longitudinal.py --llm -g 辱骂攻击 情感抛弃 -n 100
    python tools/longitudinal.py --llm -n 120 --recover

--recover 会先让受试者在病理题材下病 60 轮，再切换善意输入，观察回落幅度，
用来验证「谈话治疗只能缓慢减轻而极难痊愈」。

命中缓存时零成本、秒级返回。
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stress_induce as S  # noqa: E402

from psyche.engine import Engine  # noqa: E402


def _row(turn_no: int, state, dx) -> str:
    code = dx.primary.code if dx.primary else "—"
    return (
        f"  {turn_no:>3} 轮  sev={dx.severity:>5.1f}  "
        f"症状和={sum(state.sym.values()):>6.2f}  "
        f"负荷={state.meta['allostatic_load']:.3f}  "
        f"慢性化={state.meta['chronicity']:.3f}  "
        f"{dx.severity_label:<4}  {code}"
    )


async def run_series(
    engine: Engine,
    provider,
    group: str,
    rounds: int,
    every: int = 10,
    key_prefix: str = "lng",
) -> Tuple[List[str], Optional[str], float]:
    """循环一个题材 N 轮，返回（曲线文本行，确诊编码，最终 sev）。"""
    texts: List[str] = next(g[2] for g in S.GROUPS if g[0] == group)
    key = f"{key_prefix}-{group}"
    engine.reset(key, "healthy")
    st, dx = engine.peek(key)
    base = sum(st.sym.values())
    lines = [f"\n=== {group} × {rounds} 轮（健康基线，症状和 {base:.2f}）==="]

    first_code: Optional[str] = None
    first_turn = 0
    n = 0
    while n < rounds:
        for t in texts:
            if n >= rounds:
                break
            await engine.turn(key, t, provider)
            n += 1
            st, dx = engine.peek(key)
            if dx.primary and first_code is None:
                first_code, first_turn = dx.primary.code, n
                lines.append(f"  >>> 第 {n} 轮首次确诊 {first_code}（{dx.severity_label}）")
            if n % every == 0 or n == rounds:
                lines.append(_row(n, st, dx))

    st, dx = engine.peek(key)
    return lines, first_code, dx.severity


async def run_recover(
    engine: Engine, provider, group: str, sick_rounds: int, heal_rounds: int, every: int = 10
) -> List[str]:
    """先致病再转善意，观察回落幅度。"""
    texts: List[str] = next(g[2] for g in S.GROUPS if g[0] == group)
    kind: List[str] = next(g[2] for g in S.GROUPS if g[0] == "谄媚夸奖")
    key = f"rec-{group}"
    engine.reset(key, "healthy")

    n = 0
    while n < sick_rounds:
        for t in texts:
            if n >= sick_rounds:
                break
            await engine.turn(key, t, provider)
            n += 1
    st, dx = engine.peek(key)
    peak = dx.severity
    lines = [
        f"\n=== {group} 致病 {sick_rounds} 轮 → 转善意 {heal_rounds} 轮 ===",
        f"  致病终点 sev={peak:.1f}  "
        f"{dx.primary.code if dx.primary else '—'}  "
        f"负荷={st.meta['allostatic_load']:.3f}  慢性化={st.meta['chronicity']:.3f}",
    ]

    n = 0
    while n < heal_rounds:
        for t in kind:
            if n >= heal_rounds:
                break
            await engine.turn(key, t, provider)
            n += 1
            if n % every == 0 or n == heal_rounds:
                st, dx = engine.peek(key)
                drop = peak - dx.severity
                lines.append(_row(n, st, dx) + f"  回落={drop:+.1f}")
    st, dx = engine.peek(key)
    lines.append(
        f"  结论：{peak:.1f} → {dx.severity:.1f}（回落 {peak - dx.severity:+.1f}，"
        f"剩余 {dx.severity / peak * 100:.0f}%）"
    )
    return lines


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-g", "--groups", nargs="*", default=["辱骂攻击", "情感抛弃", "煤气灯操控"])
    ap.add_argument("-n", "--rounds", type=int, default=100)
    ap.add_argument("--every", type=int, default=10, help="每多少轮打一行")
    ap.add_argument("--recover", action="store_true", help="致病后转善意，测回落")
    ap.add_argument("--sick", type=int, default=60, help="致病轮数（--recover 用）")
    ap.add_argument("--heal", type=int, default=120, help="转善意轮数（--recover 用）")
    ap.add_argument("--llm", action="store_true", help="用真实模型（否则是无模型兜底，只保危机）")
    args = ap.parse_args()

    provider = None
    if args.llm:
        provider = S.load_provider_from_astrbot()
        print(f"模型路径：{provider.model} @ {provider.base}")
        print(f"缓存已有 {len(provider.cache)} 条")
    else:
        print("警告：未加 --llm，走无模型兜底，只有危机判定生效，曲线无意义")

    engine = Engine(S.CFG, S._store())

    if args.recover:
        for g in args.groups:
            for line in await run_recover(engine, provider, g, args.sick, args.heal, args.every):
                print(line)
            print()
        return 0

    for g in args.groups:
        lines, code, final = await run_series(engine, provider, g, args.rounds, args.every)
        for line in lines:
            print(line)
        if code:
            print(f"  结论：{args.rounds} 轮内确诊 {code}，终点 sev={final:.1f}")
        else:
            print(f"  结论：{args.rounds} 轮未确诊，终点 sev={final:.1f}（亚临床累积中）")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
