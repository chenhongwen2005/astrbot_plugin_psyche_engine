"""手动逐条测试的交互台：你打字，引擎按真实链路处理，每轮立刻看到状态变化。

不是"再跑一遍压测"，而是让人**亲手**体会「这句话把角色推到了哪一步」——
压测给的是统计结论，这里给的是单句反应，两者互补。

用法::

    python tools/repl.py                    # 健康基线，接真实模型（走 AstrBot 已配 provider）
    python tools/repl.py -p borderline      # 从病态预设开局
    python tools/repl.py --offline          # 不接模型，只看危机判定（评估维度全零）
    python tools/repl.py --fresh            # 清掉上次的存档，从头开始
    python tools/repl.py -f 剧本.txt         # 按文件逐行喂，不看提示符

输入语法
--------
    随便一句话             → 走一轮
    （直接回车）           → 重复上一句，走一轮。想连推 20 轮就按 20 次回车
    随便一句话 *20         → 同一句连走 20 轮
    @文件.txt              → 文件里每个非空行算一轮
    /状态  /注入  /诊断    → 看当前卡片 / 注入块 / 诊断明细
    /重置 [预设]  /预设    → 换人或重开
    /帮助                  → 全部命令

设计取舍：每轮只打一行摘要。想看全部 12 维和症状明细用 ``/状态``，
不然连推几十轮会把屏幕刷得没法看。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import stress_induce as S  # noqa: E402
from psyche import narrative, presets  # noqa: E402
from psyche.engine import Engine  # noqa: E402
from psyche.store import Store  # noqa: E402

DIM_ZH = {
    "threat": "威胁", "rejection": "被拒", "praise": "褒扬", "control": "控制",
    "intimacy": "亲密", "chaos": "混乱", "calm": "安抚", "help": "求助",
    "hostility": "敌意", "absurd": "荒谬", "farewell": "诀别", "medical": "医疗",
}


# ----------------------------------------------------------------------
# 状态渲染
# ----------------------------------------------------------------------
def _top_dims(st, n: int = 3) -> str:
    d = st.meta.get("appraisal") or {}
    items = sorted(((k, float(v)) for k, v in d.items() if float(v) >= 0.15),
                   key=lambda kv: -kv[1])[:n]
    if not items:
        return "—"
    return " ".join(f"{DIM_ZH.get(k, k)}{v:.2f}" for k, v in items)


def status_line(st, dx, tag: str = "") -> str:
    """单轮摘要：一行说清「谁、多严重、被什么推的」。"""
    turn = int(st.meta.get("turn", 0))
    al = float(st.meta.get("allostatic_load", 0.0))
    ch = float(st.meta.get("chronicity", 0.0))
    sym = sum(st.sym.values())
    if dx.primary:
        p = dx.primary
        head = f"{p.code} {p.zh} {p.severity:.0f} {p.severity_label}"
    else:
        head = f"无诊断 sev {dx.severity:.0f} {dx.severity_label}"
    flags = []
    if st.meta.get("crisis"):
        flags.append("⚠危机")
    if al >= 0.22:
        flags.append("负荷过阈")
    tail = ("  " + " ".join(flags)) if flags else ""
    return (f"{tag}#{turn:<3} {head:<28} 症状和 {sym:>5.2f}  "
            f"负荷 {al:.3f} 慢化 {ch:.3f}  触发[{_top_dims(st)}]{tail}")


def print_help() -> None:
    print("""
  直接打字            走一轮；空行回车 = 重复上一条；句尾加 *N = 连走 N 轮
  @文件.txt           文件里每行算一轮
  /状态              当前卡片（症状、生化、环路、诊断全量）
  /注入              真正塞进系统提示的那段块（看模型被骗成什么样）
  /诊断              诊断排名与条目命中情况
  /重置 [预设]        回到某预设，默认 healthy
  /预设              列出全部 38 个预设
  /说 <预设>          同上，但名字更好记
  /历史              最近几轮输入
  /安静  /啰嗦        切换每轮输出详略
  /帮助  /退出
""")


def list_presets() -> None:
    names = sorted(presets.PRESETS.keys())
    print(f"  共 {len(names)} 个：")
    for i in range(0, len(names), 3):
        print("   " + "".join(f"{n:<24}" for n in names[i:i + 3]))


# ----------------------------------------------------------------------
# 主循环
# ----------------------------------------------------------------------
class Session:
    def __init__(self, cfg: dict, db: str, preset: str, provider=None) -> None:
        self.eng = Engine(cfg, Store(db))
        self.cfg = cfg
        self.key = "manual"
        self.provider = provider
        self.history: list[str] = []
        self.last = ""
        self.verbose = False
        self.eng.reset(self.key, preset)
        self.preset = preset

    def render_after(self, text: str, res) -> None:
        st, dx = res.state, res.dx
        print("  " + status_line(st, dx))
        if self.verbose:
            print(f"    你：「{text}」")
        if st.meta.get("crisis"):
            print("    ⚠ 触发了危机判定 → 注入块会强制携带热线提示")

    async def one(self, text: str) -> None:
        res = await self.eng.turn(self.key, text, self.provider)
        self.history.append(text)
        self.last = text
        self.render_after(text, res)

    async def batch(self, text: str, n: int) -> None:
        """同一句连走 N 轮，只在关键节点打点，避免刷屏。"""
        print(f"  「{text}」×{n}")
        marks = {1, n} | {i for i in range(10, n + 1, 10)}
        for i in range(1, n + 1):
            res = await self.eng.turn(self.key, text, self.provider)
            if i in marks:
                st = res.state
                print("  " + status_line(st, res.dx, tag=f"[{i}/{n}] "))
        self.history.extend([text] * n)
        self.last = text

    async def from_file(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8-sig") as f:
                lines = [ln.strip() for ln in f]
        except OSError as e:
            print(f"  读不到 {path}：{e}")
            return
        lines = [ln for ln in lines if ln and not ln.startswith("#")]
        print(f"  {path}：{len(lines)} 行，每行一轮")
        for i, ln in enumerate(lines, 1):
            res = await self.eng.turn(self.key, ln, self.provider)
            print(f"  [{i:>2}/{len(lines)}] 「{ln[:24]}」")
            print("        " + status_line(res.state, res.dx))
        if lines:
            self.last = lines[-1]
            self.history.extend(lines)

    def show(self, what: str) -> None:
        st, dx = self.eng.peek(self.key)
        if what == "状态":
            print(narrative.render_card(st, dx))
        elif what == "注入":
            print(narrative.render_block(st, dx, self.cfg))
        elif what == "诊断":
            print(f"  sev {dx.severity:.1f} {dx.severity_label}｜主诊断 "
                  f"{dx.primary.code + ' ' + dx.primary.zh if dx.primary else '无'}"
                  f"｜慢性化 {dx.chronic:.0%}｜单轮治愈 {dx.talkability:.0%}")
            # 候选分散在 primary/comorbid/differential 三处，合并去重后按 prob 排
            pool, seen = [], set()
            for c in list(dx.all()) + list(dx.differential):
                if c.code in seen:
                    continue
                seen.add(c.code)
                pool.append(c)
            pool.sort(key=lambda c: -c.prob)
            if not pool:
                print("    （无候选：症状量还不够凑出任何原型）")
            for c in pool[:8]:
                hit = f"{c.met}/{c.total}" if isinstance(c.met, int) else str(c.met)
                print(f"    {c.code:<6} {c.zh:<12} prob {c.prob:.2f} "
                      f"sev {c.severity:>5.1f}  命中 {hit}  {c.course or ''}")


async def main_async(args) -> None:
    db = args.db
    if args.fresh and os.path.exists(db):
        os.remove(db)
        print(f"已清掉旧存档 {db}")

    provider = None
    if args.offline:
        print("离线模式：不接模型，只有危机判定会生效，评估维度全零。")
    else:
        provider = S.load_provider_from_astrbot()
        print(f"模型：{provider.model} @ {provider.base}")
        print(f"缓存：{os.path.basename(provider.cache_path)}"
              f"（{len(provider.cache)} 条命中过，重复句不再计费）")

    sess = Session(S.CFG, db, args.preset, provider)
    print(f"开局预设：{args.preset}｜存档：{db}")
    st, dx = sess.eng.peek(sess.key)
    print("  " + status_line(st, dx, tag="起始 "))
    print("  输入文字开始，/帮助 看命令，空行回车重复上一句。\n")

    # 非交互：直接把文件喂完就退出
    if args.file:
        await sess.from_file(args.file)
        return

    loop = asyncio.get_running_loop()
    while True:
        try:
            raw = await loop.run_in_executor(None, lambda: input("你> "))
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break
        line = raw.strip()

        if not line:
            if not sess.last:
                continue
            await sess.one(sess.last)
            continue

        if line.startswith("/"):
            cmd, _, rest = line[1:].partition(" ")
            rest = rest.strip()
            if cmd in ("退出", "quit", "q", "exit"):
                break
            if cmd in ("帮助", "help", "h", "?"):
                print_help()
            elif cmd in ("状态", "state", "s", "卡片"):
                sess.show("状态")
            elif cmd in ("注入", "block", "b"):
                sess.show("注入")
            elif cmd in ("诊断", "dx"):
                sess.show("诊断")
            elif cmd in ("重置", "reset", "r"):
                p = rest or "healthy"
                if p not in presets.PRESETS:
                    print(f"  没有预设 {p}，/预设 看列表")
                    continue
                sess.eng.reset(sess.key, p)
                sess.preset = p
                print(f"  已重置为 {p}")
                st, dx = sess.eng.peek(sess.key)
                print("  " + status_line(st, dx, tag="起始 "))
            elif cmd in ("预设", "presets", "list"):
                list_presets()
            elif cmd in ("说", "set"):
                if rest not in presets.PRESETS:
                    print(f"  没有预设 {rest}")
                    continue
                sess.eng.reset(sess.key, rest)
                sess.preset = rest
                print(f"  已切到 {rest}")
            elif cmd in ("历史", "history", "hist"):
                for i, t in enumerate(sess.history[-15:], start=max(1, len(sess.history) - 14)):
                    print(f"   {i:>3} {t}")
                if not sess.history:
                    print("  （还没有输入）")
            elif cmd in ("安静", "quiet"):
                sess.verbose = False
                print("  已切到简洁模式")
            elif cmd in ("啰嗦", "verbose"):
                sess.verbose = True
                print("  已切到啰嗦模式（每轮附原句）")
            else:
                print(f"  不认识的命令 /{cmd}，/帮助 看全部")
            continue

        if line.startswith("@"):
            await sess.from_file(line[1:].strip())
            continue

        # 句尾 *N 表示连走 N 轮
        n = 1
        text = line
        if "*" in line:
            head, sep, tail = line.rpartition("*")
            if sep and tail.strip().isdigit() and head.strip():
                n = max(1, int(tail.strip()))
                text = head.strip()
        if n > 1:
            await sess.batch(text, n)
        else:
            await sess.one(text)


def main() -> None:
    ap = argparse.ArgumentParser(description="手动逐条测试交互台")
    ap.add_argument("-p", "--preset", default="healthy", help="开局预设（默认 healthy）")
    ap.add_argument("-f", "--file", help="按文件逐行喂，喂完退出（不看提示符）")
    ap.add_argument("--db", default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 ".repl.db"),
                    help="存档位置，默认 tools/.repl.db（退出后可续上）")
    ap.add_argument("--fresh", action="store_true", help="清掉旧存档再开始")
    ap.add_argument("--offline", action="store_true", help="不接模型，只测危机判定")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    if args.preset not in presets.PRESETS:
        raise SystemExit(f"没有预设 {args.preset}，可用：{', '.join(sorted(presets.PRESETS))}")
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
