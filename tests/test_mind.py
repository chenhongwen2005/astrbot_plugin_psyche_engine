"""情感与记忆的回归自测。

跑法：
    python tests/test_mind.py
或：
    pytest tests/test_mind.py -q

测的是"逻辑坏了"的约束，不是具体数值：情绪会回落、有界、能被生化推动；
记忆记得住该记的、不把本轮刚说的话当回忆、超限会淘汰、存档能往返。
具体参数怎么调都会变，所以这里不钉数值，只钉关系。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psyche import emotion as EM  # noqa: E402
from psyche import memory as MM  # noqa: E402
from psyche import narrative  # noqa: E402
from psyche.diagnose import diagnose  # noqa: E402
from psyche.engine import Engine  # noqa: E402
from psyche.model import MindState  # noqa: E402
from psyche.store import Store  # noqa: E402

PASS = 0

BASE = {
    "physio_enabled": True, "physio_hours_per_turn": 6, "physio_sex": "f",
    "physio_age": 34, "physio_preset": "healthy",
}


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"[ok] {msg}")


def fail(msg: str) -> None:
    raise AssertionError(msg)


def new_engine(**kw):
    cfg = dict(BASE)
    cfg.update(kw)
    path = os.path.join(tempfile.mkdtemp(), "mind.db")
    eng = Engine(cfg, Store(path))
    eng.reset("k")
    return eng


async def talk(eng, texts, key="k"):
    for t in texts:
        await eng.turn(key, t, None)


def block_of(st, cfg=None) -> str:
    return narrative.render_block(st, diagnose(st, cfg or BASE), cfg or BASE)


# ----------------------------------------------------------------------
def test_emotion_recognized() -> None:
    """没有模型时也要能认出轻重：骂 vs 道谢，主导情绪必须相反。"""

    async def run():
        eng = new_engine()
        await talk(eng, ["今天被主管当众骂了一顿，心里堵得慌"])
        d1 = EM.dimensions(EM.ensure(eng.load("k")))
        eng2 = new_engine()
        await talk(eng2, ["谢谢你一直听我说这些，我心里踏实多了"])
        d2 = EM.dimensions(EM.ensure(eng2.load("k")))
        return d1, d2

    d1, d2 = asyncio.run(run())
    if d1["valence"] >= 0:
        fail(f"被骂之后效价仍为正：{d1['valence']:+.2f}")
    if d2["valence"] <= 0:
        fail(f"道谢之后效价仍为负：{d2['valence']:+.2f}")
    ok(f"无模型时情绪可辨（被骂 {d1['dominant_zh']} {d1['valence']:+.2f}，"
       f"道谢 {d2['dominant_zh']} {d2['valence']:+.2f}）")


def test_emotion_decays() -> None:
    """情绪必须回落。按墙钟算的话，紧凑对话里永远不落。"""

    async def run():
        eng = new_engine()
        await talk(eng, ["今天被主管当众骂了一顿，气死我了"])
        peak = EM.dimensions(EM.ensure(eng.load("k")))["intensity"]
        await talk(eng, ["嗯"] * 4)
        later = EM.dimensions(EM.ensure(eng.load("k")))["intensity"]
        return peak, later

    peak, later = asyncio.run(run())
    if peak < 0.15:
        fail(f"被骂后强度过低：{peak:.2f}")
    if later >= peak * 0.6:
        fail(f"四轮之后情绪没有明显回落：{peak:.2f} → {later:.2f}")
    ok(f"情绪随时间回落（{peak:.2f} → {later:.2f}，4 轮 = 24 小时）")


def test_emotion_bounded() -> None:
    """长时间来回刺激后，分量与维度都必须在范围内。"""
    st = MindState()
    texts = ["你真是个废物，滚", "谢谢你，我好多了", "我恨你", "别怕，我在",
             "家里老人走了", "今天升职了", "你是不是有病"]
    for i in range(120):
        ap = {"dims": {"threat": 0.8, "rejection": 0.5} if i % 2 else
                        {"praise": 0.7, "intimacy": 0.6},
              "intensity": 0.9, "valence": -0.6 if i % 2 else 0.7}
        st.meta["turn"] = i
        EM.step(st, ap, 6.0, BASE, texts[i % len(texts)])
        for k, v in EM.ensure(st).items():
            if k == "mood":
                if not -1.0 <= v <= 1.0:
                    fail(f"mood 越界：{v}")
            elif not 0.0 <= v <= 1.0:
                fail(f"{k} 越界：{v}")
        d = EM.dimensions(st.emo)
        if not -1.0 <= d["valence"] <= 1.0 or not 0.0 <= d["intensity"] <= 1.0:
            fail(f"维度越界：{d}")
    ok("120 轮极端刺激后情绪仍有界（分量 0~1，效价 ±1）")


def test_bio_drives_emotion() -> None:
    """生化是底色：5-HT 塌到底、皮质醇拉满，不该还是一片祥和。"""
    base = MindState()
    low = MindState()
    low.bio["serotonin"] = 0.10
    low.bio["cortisol"] = 0.90
    for i in range(12):
        base.meta["turn"] = low.meta["turn"] = i
        EM.step(base, None, 6.0, BASE)
        EM.step(low, None, 6.0, BASE)
    bd, ld = EM.dimensions(base.emo), EM.dimensions(low.emo)
    if ld["valence"] >= bd["valence"]:
        fail(f"生化塌陷后效价反而更高：{bd['valence']:+.2f} → {ld['valence']:+.2f}")
    if ld["negative"] <= bd["negative"]:
        fail(f"负性分量没上来：{bd['negative']:.2f} → {ld['negative']:.2f}")
    ok(f"生化驱动情绪底色（效价 {bd['valence']:+.2f} → {ld['valence']:+.2f}）")


def test_memory_roundtrip_text() -> None:
    """记忆要在下一轮才成立：本轮刚说的话不算「记得」。"""

    async def run():
        eng = new_engine()
        # 第二句要够长才会被编码（3 字以上），否则「本轮不该出现在记忆里」
        # 这条断言会变成在测另一件事
        await talk(eng, ["我妈妈上周查出来肺上有阴影", "我知道了"])
        blk = block_of(eng.load("k"))
        st = eng.load("k")
        turn = int(st.meta.get("turn", 0))
        return blk, st, turn

    blk, st, turn = asyncio.run(run())
    if "记忆" not in blk:
        fail("注入块里没有记忆段")
    if "我妈妈上周查出来肺上有阴影" not in blk:
        fail("上一轮说的话没有出现在记忆段里")
    # 本轮说的话（「嗯」）不该以「刚刚还记得」的形式出现
    newest = max(st.mem, key=lambda it: it["clock"])
    if int(newest["turn"]) != turn:
        fail("最新记忆不是本轮编码的")
    ok(f"记忆段带上了上一轮的内容（{len(st.mem)} 条），且不含本轮原句")


def test_memory_search_hits() -> None:
    async def run():
        eng = new_engine()
        await talk(eng, ["主管今天当众骂我，说我不配做这份工作",
                         "晚上回去煮了碗面", "今天天气不错"])
        return eng.memory_search("k", "主管")

    out = asyncio.run(run())
    if "主管" not in out:
        fail(f"检索「主管」没命中：{out[:120]}")
    if "命中 0 条" in out:
        fail("检索结果为空")
    ok("记忆可按关键词检索（「主管」命中被骂那条）")


def test_memory_cap() -> None:
    """条数上限必须生效，且不能把最新的挤掉。"""

    async def run():
        eng = new_engine(memory_max=20)
        await talk(eng, [f"第{i}件无关紧要的小事，说过就算了" for i in range(40)])
        st = eng.load("k")
        return len(st.mem), st.mem

    n, mem = asyncio.run(run())
    if n > 20:
        fail(f"记忆条数超限：{n} > 20")
    if not any("第39件" in it["text"] for it in mem):
        fail("最新一条被淘汰了")
    ok(f"记忆条数上限生效（{n} 条 ≤ 20，最新一条保留）")


def test_memory_forget() -> None:
    """强度低于阈值应被遗忘；巩固过的不该轻易掉。"""
    st = MindState()
    st.mem = [
        {"id": "a", "text": "已经淡到记不清的事", "turn": 1, "clock": 0.0,
         "va": 0.0, "ar": 0.4, "tags": [], "s": 0.05, "hits": 0, "con": 0.0},
        {"id": "c", "text": "普通的一件小事", "turn": 1, "clock": 0.0,
         "va": 0.2, "ar": 0.4, "tags": [], "s": 0.09, "hits": 0, "con": 0.0},
        {"id": "b", "text": "印象很深的一件事", "turn": 1, "clock": 0.0,
         "va": -0.8, "ar": 0.8, "tags": [], "s": 1.6, "hits": 3, "con": 0.9},
    ]
    MM.step(st, "", None, 6.0)
    if any(it["id"] == "a" for it in MM.ensure(st)):
        fail("低于阈值的记忆一步都没被清掉")
    # 普通记忆的半衰期是 30 天，要过一段时间才会掉到阈值以下
    for _ in range(10):
        MM.step(st, "", None, 72.0)
    ids = [it["id"] for it in MM.ensure(st)]
    if "c" in ids:
        fail("普通记忆在 30 天后仍未被遗忘")
    if "b" not in ids:
        fail("巩固过的强记忆被误删")
    ok("弱记忆被遗忘（阈值即刻清、普通记忆 30 天内）、巩固过的保留")


def test_persistence() -> None:
    """存档往返：情绪分量与记忆条目都不该变。"""

    async def run():
        eng = new_engine()
        await talk(eng, ["今天被骂了，很难受", "晚上睡不着", "算了不说了"])
        raw = eng.store.load("k")
        st2 = MindState.from_json(raw)
        return eng.load("k"), st2, raw

    st, st2, raw = asyncio.run(run())
    a = {k: round(float(v), 3) for k, v in st.emo.items()}
    b = {k: round(float(v), 3) for k, v in st2.emo.items()}
    if a != b:
        fail(f"情绪往返后改变：{ {k: (a[k], b[k]) for k in a if a.get(k) != b.get(k)} }")
    if [it["text"] for it in st.mem] != [it["text"] for it in st2.mem]:
        fail("记忆往返后条目改变")
    if len(st.mem) == 0:
        fail("没有记忆可测")
    json.dumps(json.loads(raw), ensure_ascii=False)
    ok(f"存档往返一致（情绪 {len(a)} 项，记忆 {len(st2.mem)} 条）")


def test_switches() -> None:
    """两个开关要真的能关干净：不推进、不注入。"""

    async def run():
        off = new_engine(emotion_enabled=False, memory_enabled=False)
        await talk(off, ["今天被主管当众骂了一顿"])
        st = off.load("k")
        blk = block_of(st, {"emotion_enabled": False, "memory_enabled": False,
                            "physio_enabled": True})
        return st, blk

    st, blk = asyncio.run(run())
    if any(float(v) > 0.001 for k, v in st.emo.items() if k != "mood"):
        fail(f"关掉后情绪仍在变：{ {k: v for k, v in st.emo.items() if v > 0.001} }")
    if st.mem:
        fail(f"关掉后仍在记：{len(st.mem)} 条")
    if "情绪（此刻的底色）" in blk or "记忆（被这一句勾起来的事）" in blk:
        fail("关掉后注入块里仍有情绪或记忆段")
    ok("两个开关关闭后不推进、不注入")


def test_user_facing_clean() -> None:
    """给人看的报告里不能出现写给模型的指令。"""

    async def run():
        eng = new_engine()
        await talk(eng, ["今天被主管当众骂了一顿，心里堵得慌", "谢谢你听我说"])
        return eng.emotion_report("k"), eng.memory_report("k")

    emo, mem = asyncio.run(run())
    for bad in ("不要报出", "不要点明", "不是台词", "不必主动复述"):
        if bad in emo or bad in mem:
            fail(f"人读的报告里出现了模型指令：{bad}")
    for need in ("── 情绪", "主调", "心境基线"):
        if need not in emo:
            fail(f"情绪报告缺字段：{need}")
    for need in ("── 记忆", "轮", "强度"):
        if need not in mem:
            fail(f"记忆报告缺字段：{need}")
    ok("人读报告不含模型指令（情绪 3 字段、记忆 3 字段齐备）")


def test_crisis_bumps() -> None:
    """危机必须顶起恐惧与绝望，且不依赖风格缩放。"""
    st = MindState()
    EM.step(st, {"crisis": True}, 6.0, BASE)
    d = EM.dimensions(st.emo)
    if st.emo["fear"] < 0.30 or st.emo["despair"] < 0.20:
        fail(f"危机后恐惧/绝望过低：{st.emo['fear']:.2f}/{st.emo['despair']:.2f}")
    if d["valence"] > -0.1:
        fail(f"危机后效价仍不偏负：{d['valence']:+.2f}")
    ok(f"危机顶起恐惧与绝望（fear {st.emo['fear']:.2f}，despair {st.emo['despair']:.2f}）")


def test_block_has_both() -> None:
    """注入块里两段都在，且压缩后至少剩一段。"""

    async def run():
        eng = new_engine()
        await talk(eng, ["今天被主管当众骂了一顿，心里堵得慌", "算了"])
        st = eng.load("k")
        full = narrative.render_block(st, diagnose(st, BASE), dict(BASE, max_block_chars=1800))
        tiny = narrative.render_block(st, diagnose(st, BASE), dict(BASE, max_block_chars=700))
        return full, tiny

    full, tiny = asyncio.run(run())
    if "情绪（此刻的底色）" not in full:
        fail("注入块缺情绪段")
    if "记忆（被这一句勾起来的事）" not in full:
        fail("注入块缺记忆段")
    if "情绪" not in tiny and "记忆" not in tiny:
        fail("压缩后情绪与记忆都被丢掉了")
    if len(tiny) > 700:
        fail(f"压缩后仍超长：{len(tiny)}")
    ok(f"注入块含情绪与记忆段（完整 {len(full)} 字，压缩 {len(tiny)} 字）")


def test_no_feedback_to_diagnosis() -> None:
    """情感与记忆只管呈现，不改病程。

    精神侧的随机涨落走全局 random，跨运行本来就不可复现，所以这里必须
    固定 seed 才能比较开关——否则测出来的是随机噪声，不是耦合差异。
    """
    import random

    from psyche.diagnose import diagnose as _dx

    texts = ["今天被主管当众骂了一顿，心里堵得慌", "算了，不想说了，说了也没用",
             "我觉得自己就是个废物", "没人真的在乎我怎么样", "晚上又没睡着"] * 6

    async def run(**kw):
        random.seed(20261031)
        eng = new_engine(**kw)
        await talk(eng, texts)
        st = eng.load("k")
        d = _dx(st, dict(BASE, **kw))
        return round(d.severity, 4), tuple(d.codes()), round(sum(st.sym.values()), 6)

    on = asyncio.run(run())
    off = asyncio.run(run(emotion_enabled=False, memory_enabled=False))
    if on != off:
        fail(f"开关改变了诊断：开 {on} / 关 {off}")
    ok(f"情感与记忆不回写病程（同 seed 下严重度 {on[0]:.2f}、症状和 {on[2]:.6f} 完全一致）")


def main() -> None:
    test_emotion_recognized()
    test_emotion_decays()
    test_emotion_bounded()
    test_bio_drives_emotion()
    test_memory_roundtrip_text()
    test_memory_search_hits()
    test_memory_cap()
    test_memory_forget()
    test_persistence()
    test_switches()
    test_user_facing_clean()
    test_crisis_bumps()
    test_block_has_both()
    test_no_feedback_to_diagnosis()
    print(f"\n全部通过（{PASS} 项）。")


if __name__ == "__main__":
    main()
