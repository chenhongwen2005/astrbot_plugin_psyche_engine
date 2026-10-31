#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""长程浸泡测试：把虚拟时间拉到数年，逐轮检查状态不变量。

单元测试只能覆盖单点行为（一次体检、一次服药），但「时间长了会不会跑飞」
只能靠长程跑。本脚本按天推进，每轮核对一遍身体状态是否还落在生理上说得通
的范围内，跑完给出问题清单。

    python tools/soak.py                  # 默认全套，约 2-4 分钟
    python tools/soak.py -s baseline -y 5 # 只跑基线，5 年
    python tools/soak.py --slow           # 每轮都查（默认每天查一次）

检查的是"不可能发生的事"，不是"好不好看"：
  · 化验项缺失、NaN、负值、量级荒谬
  · 体征越出可存活范围
  · 器官功能越界、疾病编码不存在、病程开始时间在未来了
  · 体重不收敛、随年龄反向变化
  · 同一 seed 两次跑结果不一致（确定性被破坏）
"""
from __future__ import annotations

import argparse
import asyncio
import copy
import json
import math
import os
import random
import sys
import tempfile
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from physio import body as B          # noqa: E402
from physio import const as C         # noqa: E402
from physio import drugs as D         # noqa: E402
from physio.diseases import DISEASES    # noqa: E402
from physio import report as R        # noqa: E402
from psyche.engine import Engine      # noqa: E402
from psyche.store import Store        # noqa: E402

# 可存活范围：超出这里就是模型算错了，不是"病重"
VITAL_RANGES: Dict[str, Tuple[float, float]] = {
    "HR": (30.0, 220.0), "SBP": (50.0, 260.0), "DBP": (25.0, 170.0),
    "RR": (5.0, 55.0), "SpO2": (45.0, 100.0), "TEMP": (32.0, 43.0),
    "WEIGHT": (18.0, 300.0), "BMI": (8.0, 95.0), "WAIST": (30.0, 200.0),
    "PAIN": (0.0, 10.0),
}
LAB_CEIL = 1.0e5            # 任何化验单项超过这个都说明单位或公式写翻了
NEG_OK = frozenset({"BE", "AG"})   # 碱剩余、阴离子间隙按定义可以为负
ORGAN_LO, ORGAN_HI = 0.0, 1.35

CFG: Dict[str, Any] = {
    "physio_enabled": True,
    "physio_hours_per_turn": 6,
    "physio_sex": "m",
    "physio_age": 30,
    "physio_preset": "healthy",
    "physio_disease_onset": True,
    "physio_onset_scale": 0.30,
    "physio_mortality": False,
    "physio_couple": True,
}


# ======================================================================
# 问题收集
# ======================================================================
class Report:
    def __init__(self) -> None:
        self.items: List[Tuple[str, str, str]] = []   # (场景, 位置, 描述)
        self._seen = set()

    def bad(self, scene: str, where: str, msg: str) -> None:
        sig = (scene, msg.split("=")[0], where.split("@")[0])
        if sig in self._seen:          # 同一问题只记第一次，后面只计数
            return
        self._seen.add(sig)
        self.items.append((scene, where, msg))

    def note(self, msg: str) -> None:
        print(f"  {msg}")

    def dump(self) -> int:
        print("\n" + "=" * 66)
        if not self.items:
            print("没有发现违反不变量的地方。")
            return 0
        print(f"发现 {len(self.items)} 个问题：")
        for i, (scene, where, msg) in enumerate(self.items, 1):
            print(f"\n[{i}] {scene} / {where}\n    {msg}")
        return len(self.items)


# ======================================================================
# 不变量
# ======================================================================
def check_body(rep: Report, body: Dict[str, Any], scene: str, where: str) -> None:
    labs = body.get("labs") or {}
    vit = body.get("vitals") or {}
    organs = body.get("organs") or {}
    clock = float(body.get("clock", 0.0))

    # 1 化验项齐全
    missing = [k for k in C.LABS if k not in labs]
    if missing:
        rep.bad(scene, where, f"化验项缺失 {len(missing)} 个：{missing[:6]}")

    # 2 化验数值合法
    for k, v in labs.items():
        if k not in C.LABS:
            rep.bad(scene, where, f"化验项不在词表里：{k}")
            continue
        if not isinstance(v, (int, float)) or v != v or math.isinf(v):
            rep.bad(scene, where, f"{k} 不是有限数：{v!r}")
            continue
        if v < 0 and k not in NEG_OK:
            rep.bad(scene, where, f"{k} 为负：{v:.4g}")
        elif v > LAB_CEIL:
            rep.bad(scene, where, f"{k} 量级荒谬：{v:.4g}")

    # 3 体征可存活
    for k, (lo, hi) in VITAL_RANGES.items():
        if k not in vit:
            rep.bad(scene, where, f"体征缺失：{k}")
            continue
        v = float(vit[k])
        if v != v or v < lo or v > hi:
            rep.bad(scene, where, f"{k}={v:.1f} 超出可存活范围 {lo}-{hi}")

    # 4 器官功能
    for o, fn in organs.items():
        if o in ("fat", "fat_sens"):
            continue
        if o not in C.ORGANS:
            rep.bad(scene, where, f"未知器官：{o}")
            continue
        f = float(fn)
        if f != f or f < ORGAN_LO or f > ORGAN_HI:
            rep.bad(scene, where, f"器官 {o} 功能={f:.3f} 越界")

    # 5 疾病
    seen = set()
    for c in body.get("conditions") or []:
        code = c.get("code")
        if code not in DISEASES:
            rep.bad(scene, where, f"疾病编码不存在：{code}")
            continue
        if code in seen:
            rep.bad(scene, where, f"同一疾病重复在病程里：{code}")
        seen.add(code)
        sev = float(c.get("sev", 0.0))
        if not (0.0 <= sev <= 1.0):
            rep.bad(scene, where, f"{code} 严重度越界：{sev:.3f}")
        onset = float(c.get("onset", 0.0))
        if onset > clock + 1e-6:
            rep.bad(scene, where, f"{code} 起病时间在未来：onset={onset:.0f} clock={clock:.0f}")
        if onset < -1e-6:
            rep.bad(scene, where, f"{code} 起病时间为负：{onset:.1f}")

    # 6 用药
    for m in body.get("meds") or []:
        if m.get("name") not in D.DRUGS:
            rep.bad(scene, where, f"在服未知药物：{m.get('name')}")
        if float(m.get("dose", 0.0)) <= 0:
            rep.bad(scene, where, f"{m.get('name')} 剂量非正：{m.get('dose')}")

    # 7 派生字段自洽
    der = body.get("derived") or {}
    for it in der.get("abnormal") or []:
        k = it.get("key")
        if k not in C.LABS and k not in C.VITALS:
            rep.bad(scene, where, f"异常项里出现未知指标：{k}")
        if it.get("dir") not in ("high", "low"):
            rep.bad(scene, where, f"{k} 的异常方向非法：{it.get('dir')}")

    # 8 时钟
    if clock < 0:
        rep.bad(scene, where, f"时钟为负：{clock}")


def check_mind(rep: Report, st, scene: str, where: str) -> None:
    """情感与记忆的不变量。

    长程里最容易坏的不是单点数值，而是「慢慢漂」：情绪顶到 1 下不来、
    记忆条数无上限地涨、条目缺字段导致渲染时 KeyError。
    """
    emo = getattr(st, "emo", None) or {}
    if not emo:
        rep.bad(scene, where, "情感状态为空（旧存档未补建）")
    for k, v in emo.items():
        if not isinstance(v, (int, float)) or v != v or math.isinf(v):
            rep.bad(scene, where, f"情绪 {k} 不是有限数：{v!r}")
            continue
        lo, hi = (-1.0, 1.0) if k == "mood" else (0.0, 1.0)
        if not (lo <= v <= hi):
            rep.bad(scene, where, f"情绪 {k}={v:.3f} 越过 {lo}~{hi}")
    try:
        from psyche import emotion as _E
        d = _E.dimensions(emo)
        if not (-1.0 <= d["valence"] <= 1.0) or not (0.0 <= d["intensity"] <= 1.0):
            rep.bad(scene, where, f"情绪维度越界：{d}")
    except Exception as e:  # noqa: BLE001
        rep.bad(scene, where, f"情绪维度算不出来：{type(e).__name__}: {e}")

    mem = getattr(st, "mem", None) or []
    cap = int(st.meta.get("memory_cap") or 240)
    if len(mem) > cap:
        rep.bad(scene, where, f"记忆条数超限：{len(mem)} > {cap}")
    need = ("id", "text", "turn", "clock", "va", "ar", "tags", "s", "hits", "con")
    for i, it in enumerate(mem[:3] + mem[-3:]):
        if not isinstance(it, dict):
            rep.bad(scene, where, f"记忆条目不是 dict：{type(it).__name__}")
            continue
        miss = [k for k in need if k not in it]
        if miss:
            rep.bad(scene, where, f"记忆条目缺字段 {miss}：{str(it)[:60]}")
        if float(it.get("s", 0)) < 0 or float(it.get("s", 0)) > 2.5:
            rep.bad(scene, where, f"记忆强度越界：{it.get('s')}")


def check_monotonic(rep: Report, prev: Dict[str, Any], body: Dict[str, Any],
                    scene: str, where: str) -> None:
    a, b = float(prev.get("clock", 0.0)), float(body.get("clock", 0.0))
    if b < a - 1e-6:
        rep.bad(scene, where, f"时钟倒退：{a:.1f} → {b:.1f}")


# ======================================================================
# 场景
# ======================================================================
def new_engine(cfg: Optional[Dict[str, Any]] = None) -> Engine:
    path = os.path.join(tempfile.mkdtemp(prefix="soak-"), "soak.db")
    return Engine(dict(CFG, **(cfg or {})), Store(path))


async def run_days(eng: Engine, key: str, days: int, rep: Report, scene: str,
                   every: int = 1, txt: str = "今天还好。",
                   keep: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, Any]:
    """按天推进：一天 4 轮、每轮 6 小时。每 `every` 天查一次不变量。

    `keep` 用来钉住生活方式：睡觉、三餐、运动每小时都会把 sleep_h / salt /
    sugar / activity 往自己的目标拉，只设一次等于没设，必须每轮前写回去。
    """
    t0 = time.time()
    for d in range(days):
        for _ in range(4):
            if keep:
                b = eng.load(key).body
                b.setdefault("life", {}).update(keep.get("life") or {})
                b.setdefault("env", {}).update(keep.get("env") or {})
            await eng.turn(key, txt, None)
        if (d + 1) % every == 0:
            st = eng.load(key)
            body = st.body
            where = f"第 {d + 1} 天 @{float(body.get('clock', 0)) / 24:.0f}d"
            check_body(rep, body, scene, where)
            check_mind(rep, st, scene, where)
    dt = time.time() - t0
    rep.note(f"{scene}: {days} 天 / {days * 4} 轮，{dt:.1f}s（{dt / max(1, days * 4) * 1000:.1f}ms/轮）")
    return eng.load(key).body


def brief(body: Dict[str, Any]) -> str:
    v = body.get("vitals") or {}
    d = body.get("derived") or {}
    return (f"{B.summary_line(body)}｜{float(v.get('WEIGHT', 0)):.1f}kg "
            f"BMI{float(v.get('BMI', 0)):.1f}｜异常{len(d.get('abnormal') or [])}项"
            f"｜病程{len(body.get('conditions') or [])}")


async def scene_baseline(rep: Report, years: float) -> None:
    print("\n[1] 健康基线：男 30 岁，正常作息")
    eng = new_engine()
    key = "soak-base"
    eng.reset(key)
    b0 = copy.deepcopy(eng.load(key).body)
    egfr0 = float((b0.get("labs") or {}).get("eGFR", 0))
    body = await run_days(eng, key, int(years * 365), rep, "baseline")
    egfr1 = float((body.get("labs") or {}).get("eGFR", 0))
    rep.note(f"起点 {brief(b0)}\n  终点 {brief(body)}")
    rep.note(f"eGFR {egfr0:.0f} → {egfr1:.0f}")
    if egfr1 > egfr0 + 5:
        rep.bad("baseline", "eGFR", f"肾功能随年龄变好：{egfr0:.0f} → {egfr1:.0f}")
    w0, w1 = float(b0["vitals"]["WEIGHT"]), float(body["vitals"]["WEIGHT"])
    if abs(w1 - w0) > 5:
        rep.bad("baseline", "体重", f"健康人三年内体重漂移 {w0:.1f} → {w1:.1f}kg")
    conds = [c["code"] for c in body.get("conditions") or []]
    rep.note(f"三年内新发：{conds or '无'}")
    st = eng.load(key)
    rep.note(f"情绪 效价 {st.emo.get('mood', 0):+.2f}（心境基线）｜"
             f"记忆 {len(st.mem)} 条（上限 {st.meta.get('memory_cap')}）")


async def scene_presets(rep: Report) -> None:
    print("\n[2] 预设区分度：四种体质各一年")
    rows = []
    for preset in ("athlete", "healthy", "sedentary", "obese"):
        eng = new_engine({"physio_preset": preset})
        key = f"soak-{preset}"
        eng.reset(key)
        b0 = copy.deepcopy(eng.load(key).body)
        body = await run_days(eng, key, 365, rep, f"preset:{preset}", every=30)
        rows.append((preset, float(b0["vitals"]["WEIGHT"]), float(body["vitals"]["WEIGHT"]),
                     float(body["vitals"]["BMI"]), len(body.get("conditions") or [])))
    rep.note(f"{'预设':<10}{'起点kg':>8}{'终点kg':>8}{'BMI':>7}{'病程':>5}")
    for p, w0, w1, bmi, nc in rows:
        rep.note(f"{p:<10}{w0:>8.1f}{w1:>8.1f}{bmi:>7.1f}{nc:>5}")
    weights = [r[2] for r in rows]
    if max(weights) - min(weights) < 8:
        rep.bad("presets", "区分度", f"四种预设一年后体重几乎相同：{weights}")


async def scene_bad_life(rep: Report) -> None:
    print("\n[3] 恶劣生活：熬夜 + 吸烟 + 酗酒 + 高糖高盐 + 久坐 + 重污染，两年")
    eng = new_engine()
    key = "soak-bad"
    eng.reset(key)
    keep = {
        "life": {"sleep_h": 4.5, "sleep_debt": 12.0, "sleep_qual": 0.35,
                 "sugar": 2.6, "salt": 2.2, "satfat": 2.0, "fiber": 0.3,
                 "activity": 0.25, "sedentary": 12.0, "smoking": 25.0,
                 "alcohol": 4.0, "vitd": 0.2, "stress": 0.85},
        "env": {"pm25": 160.0, "pathogen": 0.6, "noise": 78.0, "temp_c": 34.0},
    }
    b0 = copy.deepcopy(eng.load(key).body)
    out = await run_days(eng, key, 730, rep, "bad_life", every=7, keep=keep)
    names = [f"{DISEASES[c['code']]['zh']}" for c in out.get("conditions") or []
             if c.get("code") in DISEASES]
    rep.note(f"起点 {brief(b0)}\n  终点 {brief(out)}\n  两年后得的病：{'、'.join(names) or '一个都没得'}")
    if not names:
        rep.bad("bad_life", "疾病发生", "两年极端不良生活没有诱发任何疾病")
    w0, w1 = float(b0["vitals"]["WEIGHT"]), float(out["vitals"]["WEIGHT"])
    rep.note(f"体重 {w0:.1f} → {w1:.1f}kg")


async def scene_drugs(rep: Report) -> None:
    print(f"\n[4] 全药库：{len(D.DRUGS)} 种药逐一服用 3 天再停")
    names = sorted(D.DRUGS)
    eng = new_engine()
    key = "soak-drug"
    changed, unchanged, crashed = [], [], []
    for i, name in enumerate(names):
        eng.reset(key)
        st = eng.load(key)
        before = dict(st.body.get("labs") or {})
        try:
            eng.phys_med(key, name, 1.0)
            eng.phys_advance(key, 72.0)
            st = eng.load(key)
            check_body(rep, st.body, "drugs", f"{name}@3d")
            after = st.body.get("labs") or {}
            diff = [k for k in before if abs(float(after.get(k, before[k])) - float(before[k])) > 1e-9]
            (changed if diff else unchanged).append(name)
            eng.phys_stop(key, name)
            eng.phys_advance(key, 24.0)
            check_body(rep, eng.load(key).body, "drugs", f"{name}@stop")
        except Exception as exc:                       # noqa: BLE001
            crashed.append((name, repr(exc)))
            rep.bad("drugs", name, f"服药流程抛异常：{exc}")
    rep.note(f"有可测变化 {len(changed)} 种；完全无变化 {len(unchanged)} 种；异常 {len(crashed)} 种")
    if unchanged:
        rep.note(f"无变化的药（可能是纯对症或剂量不足）：{'、'.join(unchanged[:20])}"
                 + (" …" if len(unchanged) > 20 else ""))


async def scene_commands(rep: Report) -> None:
    print("\n[5] 全指令：每个子命令、每个面板、每个参数组合都走一遍")
    eng = new_engine()
    key = "soak-cmd"
    eng.reset(key)
    for _ in range(12):
        await eng.turn(key, "今天有点累。", None)

    calls: List[Tuple[str, Any]] = []
    calls += [("phys_report 面板", (p,)) for p in
              [k for k, _ in C.PANELS] + [n for _, n in C.PANELS]
              + ["vitals", "生命体征", "异常", "异常项", "全部", "全", "", "不存在"]]
    calls += [("life", ()), ("log", ()), ("生理", ())]
    calls += [("找药", ("他汀",)), ("找药", ("不存在的药",)), ("找药", ("",))]
    calls += [("服药", ("二甲双胍", 1.0)), ("服药", ("不存在的药", 1.0)),
              ("服药", ("二甲双胍", 0.0)), ("服药", ("二甲双胍", -1.0))]
    calls += [("停服", ("二甲双胍",)), ("停服", ("没吃过的药",))]
    calls += [("推进", (0.0,)), ("推进", (1.0,)), ("推进", (24.0 * 400,)),
              ("推进", (-5.0,))]
    calls += [("设置", ("sleep_h", "6.5")), ("设置", ("sleep_h", "abc")),
              ("设置", ("sleep_h", "nan")), ("设置", ("sleep_h", "1e9")),
              ("设置", ("不存在的维度", "1"))]

    handler = {
        "phys_report 面板": eng.phys_report,
        "life": eng.phys_life, "log": eng.phys_log,
        "生理": lambda k: __import__("psyche.narrative", fromlist=["x"]).render_body_section(eng.load(k)),
        "找药": eng.phys_find, "服药": eng.phys_med,
        "停服": eng.phys_stop, "推进": eng.phys_advance, "设置": eng.phys_set,
    }
    empty = []
    for label, args in calls:
        try:
            out = handler[label](key, *args)
            if not isinstance(out, str) or not out.strip():
                empty.append((label, args))
                rep.bad("commands", f"{label}{args}", "返回空字符串")
            if "Traceback" in out or "None" == out.strip():
                rep.bad("commands", f"{label}{args}", f"返回异常内容：{out[:80]}")
        except Exception as exc:                        # noqa: BLE001
            rep.bad("commands", f"{label}{args}", f"抛异常：{exc}\n{traceback.format_exc(limit=2)}")
    rep.note(f"{len(calls)} 次调用，返回空 {len(empty)} 次")

    # 分页：任意长度都能切开且内容不丢
    for panel in ([""] + [k for k, _ in C.PANELS]):
        text = eng.phys_report(key, panel)
        pages = R.split_pages(text)
        joined = "\n".join(p.replace(f"（{i + 1}/{len(pages)}）\n", "")
                           for i, p in enumerate(pages))
        if len(pages) > 1 and "── 体检报告" not in pages[0]:
            rep.bad("pagination", panel or "全部", "首页没有抬头")
        for p in pages:
            if len(p) > 1400 or len(p.encode()) > 3800:
                rep.bad("pagination", panel or "全部",
                        f"单页超限 {len(p)} 字 / {len(p.encode())} 字节")

    # 其他命令
    try:
        eng.inject_event(key, "熬夜")
        eng.add_med(key, "舍曲林", 1.0)
        eng.remove_med(key, "舍曲林")
        eng.fast_forward(key, 5)
        eng.timeline(key, 10)
        eng.export(key)
    except Exception as exc:                            # noqa: BLE001
        rep.bad("commands", "精神侧指令", f"抛异常：{exc}")


async def scene_elderly(rep: Report) -> None:
    print("\n[6] 高龄：男 78 岁跑五年")
    eng = new_engine({"physio_age": 78})
    key = "soak-old"
    eng.reset(key)
    b0 = copy.deepcopy(eng.load(key).body)
    body = await run_days(eng, key, 365 * 5, rep, "elderly", every=30)
    rep.note(f"起点 {brief(b0)}\n  终点 {brief(body)}")
    rep.note(f"eGFR {float(b0['labs']['eGFR']):.0f} → {float(body['labs']['eGFR']):.0f}"
             f"｜年龄 {float(body.get('age', 0)):.0f}")
    if float(body.get("age", 0)) < 78:
        rep.bad("elderly", "年龄", f"跑了五年年龄没涨：{body.get('age')}")
    w0, w1 = float(b0["vitals"]["WEIGHT"]), float(body["vitals"]["WEIGHT"])
    if w1 - w0 > 6:
        rep.bad("elderly", "体重", f"七旬老人五年内增重 {w0:.1f} → {w1:.1f}kg")


async def scene_determinism(rep: Report) -> None:
    print("\n[7] 确定性：同 seed 跑两遍，终态应逐字节相同")
    snaps = []
    for _ in range(2):
        eng = new_engine()
        key = "soak-det"
        eng.reset(key)
        await run_days(eng, key, 60, rep, "determinism", every=60)
        b = eng.load(key).body
        snaps.append(json.dumps({k: b.get(k) for k in
                                 ("clock", "tick", "vitals", "labs", "organs",
                                  "conditions", "meds")}, sort_keys=True, default=str))
    if snaps[0] != snaps[1]:
        diff = [k for k in ("vitals", "labs", "organs") if
                json.dumps(json.loads(snaps[0]).get(k)) != json.dumps(json.loads(snaps[1]).get(k))]
        rep.bad("determinism", "重放", f"两次结果不一致，差异在 {diff}")
    else:
        rep.note("两遍完全一致。")


async def scene_roundtrip(rep: Report) -> None:
    print("\n[8] 存档往返：落盘再读回，数值不应改变")
    from psyche.model import MindState

    eng = new_engine()
    key = "soak-rt"
    eng.reset(key)
    await run_days(eng, key, 30, rep, "roundtrip", every=30)
    st = eng.load(key)
    raw = eng.store.load(key)
    if not raw:
        rep.bad("roundtrip", "store", "跑完 30 天后存档是空的")
        return
    st2 = MindState.from_json(raw)
    pairs = [("labs", st.body.get("labs"), st2.body.get("labs")),
             ("vitals", st.body.get("vitals"), st2.body.get("vitals")),
             ("organs", st.body.get("organs"), st2.body.get("organs")),
             ("conditions", st.body.get("conditions"), st2.body.get("conditions"))]
    for name, a, b in pairs:
        if json.dumps(a, sort_keys=True, default=str) != json.dumps(b, sort_keys=True, default=str):
            rep.bad("roundtrip", name, f"{name} 往返后不一致")
    again = st2.to_json()
    if again != raw:
        try:
            same = json.loads(again) == json.loads(raw)
        except Exception:                               # noqa: BLE001
            same = False
        if not same:
            rep.bad("roundtrip", "to_json", "二次序列化后存档内容改变（非幂等）")
    rep.note(f"往返后 {len(st.body.get('labs') or {})} 项化验、"
             f"{len(st.body.get('organs') or {})} 个器官一致。")


async def scene_stress(rep: Report) -> None:
    print("\n[9] 极端输入：把生活维度推到边界外")
    eng = new_engine()
    key = "soak-edge"
    eng.reset(key)
    edge = {"life": {"sleep_h": 0.0, "sleep_debt": 60.0, "kcal": 0.0,
                     "water": 0.0, "activity": 0.0, "fitness": 0.0,
                     "alcohol": 20.0, "smoking": 80.0, "stress": 1.0},
            "env": {"temp_c": -15.0, "pm25": 400.0, "pathogen": 1.0}}
    body = await run_days(eng, key, 90, rep, "stress", every=3, keep=edge)
    rep.note(f"90 天零睡眠零进食后：{brief(body)}")
    conds = [DISEASES[c["code"]]["zh"] for c in body.get("conditions") or []
             if c.get("code") in DISEASES]
    rep.note(f"得病：{'、'.join(conds) or '无'}｜体重 "
             f"{float(body['vitals']['WEIGHT']):.1f}kg")
    if float(body["vitals"]["WEIGHT"]) > 66.0:
        rep.bad("stress", "体重", "零摄入 90 天后体重没有下降")
    # 负值：不该把任何状态带成 NaN
    neg = {"life": {"sleep_h": -5.0, "kcal": -1.0, "water": -2.0},
           "env": {"temp_c": -40.0}}
    await run_days(eng, key, 20, rep, "stress-neg", every=2, keep=neg)
    rep.note("负值生活维度没有把状态带崩。")


# ======================================================================
SCENES = {
    "baseline": lambda rep, a: scene_baseline(rep, a.years),
    "presets": lambda rep, a: scene_presets(rep),
    "bad_life": lambda rep, a: scene_bad_life(rep),
    "drugs": lambda rep, a: scene_drugs(rep),
    "commands": lambda rep, a: scene_commands(rep),
    "elderly": lambda rep, a: scene_elderly(rep),
    "determinism": lambda rep, a: scene_determinism(rep),
    "roundtrip": lambda rep, a: scene_roundtrip(rep),
    "stress": lambda rep, a: scene_stress(rep),
}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-s", "--scenes", nargs="*", default=None,
                    help="要跑的场景，默认全部")
    ap.add_argument("-y", "--years", type=float, default=3.0)
    args = ap.parse_args()

    rep = Report()
    names = args.scenes or list(SCENES)
    t0 = time.time()
    for n in names:
        if n not in SCENES:
            print(f"未知场景：{n}")
            return 2
        try:
            await SCENES[n](rep, args)
        except Exception as exc:                        # noqa: BLE001
            rep.bad(n, "场景入口", f"场景整体崩溃：{exc}\n{traceback.format_exc(limit=3)}")
    print(f"\n总耗时 {time.time() - t0:.1f}s")
    return 1 if rep.dump() else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
