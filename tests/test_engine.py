"""自测脚本：不依赖 AstrBot，也不依赖 pytest。

直接运行：
    python tests/test_engine.py
或：
    pytest tests/test_engine.py -q
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psyche import narrative, presets  # noqa: E402
from psyche.appraisal import appraise_lexicon, parse_llm_output  # noqa: E402
from psyche.const import SYM  # noqa: E402
from psyche.criteria import BY_CODE, CORE, DISORDERS  # noqa: E402
from psyche.diagnose import diagnose  # noqa: E402
from psyche.engine import Engine  # noqa: E402
from psyche.store import Store  # noqa: E402

CFG = {
    "default_preset": "healthy",
    "chronic_turns": 120,
    "stochastic": False,
    "enable_circadian": False,
    "therapy_enabled": True,
    "appraisal_mode": "lexicon",
}

# 预设 → 期望主诊断（ICD-11 编码）
EXPECT = {
    "schizophrenia_paranoid": "6A20",
    "schizophrenia_disorganized": "6A20",
    "delusional": "6A24",
    "catatonia": "6A40",
    "mdd_severe": "6A70",
    "mdd_melancholic": "6A70",
    "dysthymia": "6A72",
    "mixed_anxiety_depression": "6A73",
    "bipolar_i_manic": "6A60",
    "bipolar_i_depressed": "6A60",
    "bipolar_ii": "6A61",
    "cyclothymia": "6A62",
    "gad": "6B00",
    "panic": "6B01",
    "social_anxiety": "6B04",
    "ocd": "6B20",
    "ptsd": "6B40",
    "cptsd": "6B41",
    "prolonged_grief": "6B42",
    "adjustment": "6B43",
    "borderline": "6D11.5",
    "aspd": "6D11.2",
    "ocpd": "6D11.4",
    "schizotypal": "6A22",
    "anorexia": "6B80",
    "bulimia": "6B81",
    "gambling": "6C50",
    "asd": "6A02",
    "adhd": "6A05",
    "insomnia": "7A00",
    "dissociative_identity": "6B64",
}


def _engine(tag: str) -> Engine:
    path = os.path.join(tempfile.gettempdir(), f"psyche_test_{tag}.db")
    if os.path.exists(path):
        os.remove(path)
    return Engine(CFG, Store(path))


def test_data_integrity() -> None:
    """所有诊断引用的症状键、核心症状键都必须存在。"""
    for d in DISORDERS:
        for k, w in d["crit"]:
            assert k in SYM, f"{d['code']} 引用了不存在的症状 {k}"
            assert 0 < w <= 1.0, f"{d['code']} 权重异常 {k}={w}"
        for k in CORE.get(d["code"], []):
            assert k in SYM, f"{d['code']} 核心症状 {k} 不存在"
        for k in (d.get("caps") or {}):
            assert k in SYM, f"{d['code']} 排除项 {k} 不存在"
        for c in (d.get("excludes") or []):
            assert c in BY_CODE, f"{d['code']} 互斥编码 {c} 不存在"
    print(f"[ok] 数据完整性：{len(DISORDERS)} 个诊断原型，{len(SYM)} 个症状条目")


def test_presets() -> None:
    bad = []
    for name, code in EXPECT.items():
        dx = diagnose(presets.get(name), CFG)
        got = dx.primary.code if dx.primary else None
        if got != code:
            bad.append(f"{name}: 期望 {code}，实际 {got}")
    assert not bad, "\n".join(bad)
    print(f"[ok] 预设诊断命中 {len(EXPECT)}/{len(EXPECT)}")


def test_healthy_stays_healthy() -> None:
    st = presets.get("healthy")
    dx = diagnose(st, CFG)
    assert dx.primary is None, f"健康基线不应有主诊断，实际 {dx.primary.code}"
    print("[ok] 健康基线未误诊")


def test_appraisal() -> None:
    st = presets.get("healthy")
    hostile = appraise_lexicon("你这个废物，滚开，我不想再看到你", st, CFG)
    support = appraise_lexicon("我在这，别怕，慢慢说，我陪着你", st, CFG)
    assert hostile["dims"]["threat"] > 0.3 and hostile["dims"]["rejection"] > 0.3
    assert support["dims"]["calm"] > 0.2 or support["dims"]["intimacy"] > 0.2
    assert hostile["valence"] < 0 < support["valence"]
    assert appraise_lexicon("我想自杀，已经想好了", st, CFG)["crisis"] is True
    assert appraise_lexicon("电影里有人自杀", st, CFG)["crisis"] is False
    print("[ok] 话语评估与危机识别")


def test_llm_json_parse() -> None:
    st = presets.get("healthy")
    raw = """```json
    {"keywords":["别走","你骗我"],"topic":"试探是否会被抛弃",
     "appraisal":{"rejection":0.8,"threat":0.4},"domains":{"tr":0.6,"pd":0.5},
     "intensity":0.7,"valence":-0.6,"crisis":false}
    ```"""
    ap = parse_llm_output(raw, "别走，你骗我", st)
    assert ap and ap["source"] == "llm"
    assert ap["domains"]["tr"] == 0.6
    assert "别走" in ap["keywords"]
    # 非法输入应安全返回 None，而不是抛异常
    assert parse_llm_output("not a json", "x", st) is None
    assert parse_llm_output("", "x", st) is None
    print("[ok] 模型 JSON 解析与容错")


def test_dynamics_direction() -> None:
    eng = _engine("dyn")
    eng.reset("a", "mdd_severe")
    st0 = eng.load("a")
    ser0, cort0 = st0.bio["serotonin"], st0.bio["cortisol"]

    for _ in range(8):
        asyncio.run(eng.turn("a", "你这个废物，滚，没人要你"))
    # 注意：引擎按 key 缓存同一个 MindState 对象，必须即时取出数值再比较
    ser1 = float(eng.load("a").bio["serotonin"])
    cort1 = float(eng.load("a").bio["cortisol"])
    assert ser1 < ser0, "敌意话语应降低 5-HT"
    assert cort1 > cort0, "敌意话语应抬高皮质醇"

    for _ in range(25):
        asyncio.run(eng.turn("a", "我在这，别怕，我陪着你，慢慢说"))
    ser2 = float(eng.load("a").bio["serotonin"])
    assert ser2 > ser1, f"支持性话语应回升 5-HT（{ser1:.3f} → {ser2:.3f}）"
    print("[ok] 生化方向：敌意→5HT↓/皮质醇↑，支持→5HT↑")


def test_chronic_floor() -> None:
    eng = _engine("chron")
    eng.reset("b", "borderline")   # 预设自带 900 轮病程 → 高度慢性化
    st = eng.load("b")
    for _ in range(5):
        asyncio.run(eng.turn("b", "我在这，别怕"))
    sev_after = diagnose(eng.load("b"), CFG).severity
    assert sev_after > 30, "慢性化后不应在几轮内痊愈"
    floors = eng.load("b").meta.get("floor") or {}
    assert floors, "慢性化应产生症状地板"
    print(f"[ok] 慢性化地板生效（{len(floors)} 条症状有下限，严重度 {sev_after:.0f}）")


def test_block_contract() -> None:
    st = presets.get("schizophrenia_paranoid")
    st.meta["hot"] = {"ps_hallucination_auditory": 0.8}
    dx = diagnose(st, CFG)
    block = narrative.render_block(st, dx, {"max_block_chars": 1800})
    for token in ("<psyche_runtime", "ICD-11", "表演要求", "绝对禁止", "输出形态", "</psyche_runtime>"):
        assert token in block, f"注入块缺少 {token}"
    assert len(block) <= 1800
    print(f"[ok] 注入块契约（{len(block)} 字）")


def test_crisis_override() -> None:
    st = presets.get("mdd_severe")
    st.meta["crisis"] = True
    dx = diagnose(st, CFG)
    block = narrative.render_block(st, dx, {})
    assert "安全覆盖" in block and "12356" in block
    print("[ok] 危机覆盖优先级最高")


def test_scales_integrity() -> None:
    """量表：条目键有效、满分自洽、因子划分完整。"""
    from psyche import scales as sc
    from psyche.const import SYM

    bad = [(c, sym) for c, s in sc.SCALES.items()
           for sym, _t, _w in s["items"] if sym and sym not in SYM]
    assert not bad, f"量表映射到不存在的症状键：{bad}"

    # 逐条满分之和必须等于标称总分（1~7 / 1~5 计分的按原始求和口径）
    for code, s in sc.SCALES.items():
        n = len(s["items"])
        full = [sc.item_max_of(code, i) for i in range(n)]
        got = sc.total_of(code, full)
        assert abs(got - s["max_total"]) < 1e-6, f"{code} 满分 {got} 与标称 {s['max_total']} 不符"

    # 归零性：最低分必须折算成 0 严重度（PANSS 全 1、SCL-90 全 1）
    for code in ("PANSS", "SCL-90"):
        s = sc.SCALES[code]
        n = len(s["items"])
        off = int(s.get("offset", 0))
        lows = [off] * n
        assert sc.normalize(code, sc.total_of(code, lows)) == 0.0, \
            f"{code} 最低分未归零（offset={off}）"
        # 最高分必须饱和到 1.0，且不能把 7 分裁成 6 分
        highs = [sc.item_max_of(code, i) for i in range(n)]
        assert sc.normalize(code, sc.total_of(code, highs)) == 1.0
        assert sc.parse_scores(code, {"items": highs}) == [float(x) for x in highs]

    # SCL-90：90 条、10 因子、无重无漏
    scl = sc.SCALES["SCL-90"]
    allidx = sorted(i for v in scl["factors"].values() for i in v)
    assert len(scl["items"]) == 90
    assert allidx == list(range(90)), "SCL-90 因子索引有重或有漏"
    assert len(scl["factors"]) == 10
    assert sum(len(v) for v in scl["factors"].values()) == 90

    # 完整版校验：不做简版裁剪
    expect = {"PANSS": 30, "DES-II": 28, "PCL-5": 20, "Y-BOCS": 10,
              "YMRS": 11, "EDE-Q": 28, "AUDIT": 10, "MDQ": 13,
              "PHQ-9": 9, "GAD-7": 7, "ISI": 7, "SCL-90": 90}
    for code, n in expect.items():
        assert len(sc.SCALES[code]["items"]) == n, f"{code} 条目数应为 {n}"

    print(f"[ok] 量表完整性：{len(sc.SCALES)} 份全量表，共 "
          f"{sum(len(s['items']) for s in sc.SCALES.values())} 条")


def test_scale_projection() -> None:
    """量表分数 → 症状投影：下限归零、满分饱和、因子分正确。"""
    from psyche import scales as sc

    # PANSS 全 1 分（= 无）→ 所有投影为 0
    tg = sc.to_symptom_targets("PANSS", [1] * 30)
    assert all(v == 0.0 for v in tg.values()), "PANSS 全 1 分应投影为 0"

    # PHQ-9 满分 → 关键症状饱和
    tg = sc.to_symptom_targets("PHQ-9", [3] * 9)
    assert tg["md_depressed_mood"] == 1.0 and tg["md_anhedonia"] == 1.0

    # SCL-90 全 3 分 → 10 个因子均分都是 3.0
    fac = sc.factor_scores("SCL-90", [3] * 90)
    assert len(fac) == 10 and all(abs(v - 3.0) < 1e-9 for v in fac.values())

    # DES-II 全 100% → 总分 100
    assert sc.total_of("DES-II", [10] * 28) == 100.0

    # 解析容错：条数不对 / 超界 / 非数字
    assert sc.parse_scores("PHQ-9", {"items": [1, 2]}) is None
    assert sc.parse_scores("PHQ-9", {"items": [9] * 9}) == [3.0] * 9   # 裁到满分
    assert sc.parse_scores("PHQ-9", {"items": [-2] * 9}) == [0.0] * 9  # 负数归零
    assert sc.parse_scores("PHQ-9", {"items": ["x"] * 9}) is None
    print("[ok] 量表投影与解析容错")


def test_scale_calibration_flow() -> None:
    """端到端：模型填 SCL-90 → 校验 → 投影 → 注入块带上锚点。"""
    import asyncio

    class _Store:
        def __init__(self):
            self.d = {}

        def save(self, k, js, preset=""):
            self.d[k] = js

        def load(self, k):
            return self.d.get(k)

        def log(self, *a, **k):
            pass

    class _Prov:
        def __init__(self, payload):
            self.payload = payload

        async def text_chat(self, prompt="", **kw):
            class R:
                pass
            r = R()
            import json as _j
            r.completion_text = _j.dumps(self.payload, ensure_ascii=False)
            return r

    eng = Engine(dict(CFG, compliance_guard=False), _Store())
    eng.save("t", presets.get("mdd_severe"))
    before = eng.load("t").sym["md_fatigue"]

    out = asyncio.run(eng.calibrate("t", _Prov({"items": [4] * 90}), ["SCL-90"]))
    r = out["scales"]["SCL-90"]
    assert r["ok"], r
    assert r["total"] == 360.0 and r["grade"] == "重度"
    assert out["applied"] > 0, "量表投影没有改动任何症状"
    assert abs(eng.load("t").sym["md_fatigue"] - before) > 1e-6

    st = eng.load("t")
    assert "SCL-90" in (st.meta.get("scale_anchor") or {})
    block = narrative.render_block(st, diagnose(st, CFG), CFG)
    assert "量表自评锚点" in block and "SCL-90" in block
    print(f"[ok] 量表校准链路（改 {out['applied']} 条症状，注入块 {len(block)} 字）")


def test_scale_resolve() -> None:
    """量表名解析：代码 / 中文别名 / 全名子串，且不认识时必须返回 None。"""
    from psyche import scales as sc

    cases = {
        "scl90": "SCL-90", "SCL-90": "SCL-90", "全面": "SCL-90",
        "抑郁": "PHQ-9", "phq9": "PHQ-9",
        "双相": "MDQ", "躁狂": "YMRS", "杨氏躁狂评定量表": "YMRS",
        "焦虑": "GAD-7", "失眠": "ISI", "强迫": "Y-BOCS", "创伤": "PCL-5",
        "精分": "PANSS", "解离": "DES-II", "进食": "EDE-Q", "酒精": "AUDIT",
    }
    for q, want in cases.items():
        got = sc.resolve(q)
        assert got == want, f"「{q}」解析成 {got}，期望 {want}"
    # 关键：不认识的输入不能静默退化成 SCL-90
    assert sc.resolve("乱写的") is None
    assert sc.resolve("") is None
    got, bad = sc.resolve_many(["抑郁", "scl90", "胡说", "失眠", "抑郁"])
    assert got == ["PHQ-9", "SCL-90", "ISI"] and bad == ["胡说"], (got, bad)
    print(f"[ok] 量表名解析（{len(cases)} 条别名，未知输入不静默兜底）")


def test_compact_keeps_anchor_and_safety() -> None:
    """压缩路径：量表锚点不能被砍掉，安全覆盖段必须完整保留。"""
    st = presets.get("schizophrenia_paranoid")
    st.meta["turn"] = 40
    st.meta["crisis"] = True
    st.meta["scale_anchor"] = {
        "SCL-90": {"code": "SCL-90", "zh": "症状自评量表", "total": 219.0,
                   "max_total": 450, "grade": "中度", "turn": 38,
                   "factors": {"抑郁": 3.69, "强迫症状": 2.40}},
    }
    dx = diagnose(st, CFG)

    # 正常长度：量表段存在
    full = narrative.render_block(st, dx, {"max_block_chars": 3000})
    assert "量表自评锚点" in full and "SCL-90" in full

    # 强压到必走压缩路径
    for limit in (700, 900, 1200):
        block = narrative.render_block(st, dx, {"max_block_chars": limit})
        assert "量表锚点" in block, f"max={limit} 压缩后丢了量表锚点"
        assert "219" in block, f"max={limit} 压缩后丢了量表分数"
        assert "安全覆盖" in block, f"max={limit} 压缩后丢了安全覆盖"
        assert "12356" in block, f"max={limit} 压缩后热线被截断"
        assert block.rstrip().endswith("</psyche_runtime>"), f"max={limit} 结尾标签被截断"
        assert len(block) <= limit, f"max={limit} 实际 {len(block)}"
    print("[ok] 压缩路径保留量表锚点与安全覆盖")


if __name__ == "__main__":
    test_data_integrity()
    test_presets()
    test_healthy_stays_healthy()
    test_appraisal()
    test_llm_json_parse()
    test_dynamics_direction()
    test_chronic_floor()
    test_block_contract()
    test_crisis_override()
    test_scales_integrity()
    test_scale_projection()
    test_scale_calibration_flow()
    test_scale_resolve()
    test_compact_keeps_anchor_and_safety()
    print("\n全部通过。")
