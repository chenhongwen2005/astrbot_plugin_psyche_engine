"""性腺轴：一条随年龄、睡眠与压力缓慢起伏的内分泌线。

为什么要有这一层
    生殖模块原先只回答「能不能生」——周期、妊娠、分娩。可是下丘脑-
    垂体-性腺轴（HPG 轴）的活动水平每天都在变，它决定一个人的体力、
    肌肉与脂肪的分布、体毛生长速度、夜里起夜的次数，也影响他对亲近
    关系的意愿强弱。缺了它，成年角色在这几个维度上永远是同一条水平线。

怎么算
    不掷骰子，几条已知通路相加：
      性激素    女性看周期相位（排卵前最高，经期与产后最低），男性看睾酮
      睡眠债    一晚没睡好，第二天整体驱动就低——最强的单项
      压力      皮质醇与交感兴奋直接压下去
      情绪      低落、绝望、恐惧、羞耻压低；亲近、愉快抬高
      酒精      少量去抑制，过量反过来压
    0.5 是人群中间值，不是「零」。多数日子人就在这附近。

表述边界
    这一层只描述**内分泌活动水平**，不涉及任何行为，也不模拟过程。
    对外只给区间词（偏活跃 / 中位 / 偏淡），注入块里不出现，只在体检
    卡片里列出——玩家主动查看时才看得到。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from . import mind as MD
from . import traits as TR

KEY = "gonadal"

# 各相位的基线。排卵前是周期的最高点，经期与产后是低点。
PHASE_BASE = {
    "menstrual": 0.34,
    "follicular": 0.60,
    "ovulation": 0.74,
    "luteal": 0.44,
}


def new_state() -> Dict[str, Any]:
    return {
        "v": 1,
        "drive": 0.50,
        "beard_mm": 0.0,
        "nocturia": 0.0,
        "loh": 0.0,
    }


def ensure(body: Dict[str, Any]) -> Dict[str, Any]:
    st = body.get(KEY)
    if not isinstance(st, dict):
        st = new_state()
        body[KEY] = st
    for k, v in new_state().items():
        st.setdefault(k, v)
    return st


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def is_male(body: Dict[str, Any]) -> bool:
    r = body.get("repro") or {}
    return str(r.get("sex") or body.get("sex") or "m") == "m"


def compute(body: Dict[str, Any]) -> Dict[str, Any]:
    """算出当前的性腺轴活动水平。只读，不改状态。"""
    st = ensure(body)
    r = body.get("repro") or {}
    life = body.get("life") or {}
    emo = MD.current(body)
    sex = str(r.get("sex") or body.get("sex") or "m")
    phase = str(r.get("phase") or "")
    stage = str(r.get("stage") or "")
    age = _f(body.get("age"), 30.0)
    hour = _f(body.get("clock")) % 24.0

    if sex == "f":
        base = PHASE_BASE.get(phase, 0.50)
        if r.get("pregnant"):
            w = _f(r.get("gest_week"))
            base = 0.30 if w < 14 else (0.46 if w < 28 else 0.24)
        if stage == "postpartum" or str(r.get("phase")) in ("postpartum", "lactating"):
            # 哺乳期高泌乳素压制 GnRH，这是内分泌事实，不是心理解释
            base = 0.16 if r.get("lactating") else 0.22
        if stage in ("perimenopause", "postmenopause"):
            base *= 0.70
        if stage == "prepuberty" or age < 13.0:
            base = 0.04
        base += 0.04 * math.exp(-((hour - 20.0) ** 2) / 18.0)
    else:
        t = _f(r.get("t"), 0.60)
        base = 0.25 + 0.62 * t          # t 已含昼夜峰与年龄衰减
        if age < 13.0:
            base = 0.04

    # 迟发性性腺功能减退：45 岁后睾酮逐年下滑，这一轴跟着降。
    # 光靠睾酮数值不够——真实世界里低睾酮的乏力、腹部肥胖、兴趣减退
    # 是叠加在激素读数之上的，所以这里再单独扣一项。
    loh = _f(st.get("loh"))
    if loh <= 0.0 and age >= 45.0:
        # 还没跑过 step 的只读查询也要算对，否则体检卡片上六十岁的
        # 内分泌读数会和二十岁一模一样
        loh = min(1.0, (age - 45.0) / 25.0)
    base -= 0.10 * loh

    # 睡眠债：欠四小时以上就明显往下掉
    debt = max(0.0, _f(life.get("sleep_debt")))
    base -= min(0.32, debt * 0.018)

    # 压力：0.35 以下不算压力
    stress = _f(life.get("stress"), 0.3)
    base -= max(0.0, stress - 0.35) * 0.55

    # 情绪
    base -= 0.30 * _f(emo.get("sadness"))
    base -= 0.22 * _f(emo.get("despair"))
    base -= 0.12 * _f(emo.get("fear"))
    base -= 0.10 * _f(emo.get("shame"))
    base += 0.10 * _f(emo.get("love"))
    base += 0.05 * _f(emo.get("joy"))

    # 酒精：两杯以内去抑制，三杯以上反过来
    alc = _f(life.get("alcohol"))
    if 0.0 < alc <= 2.0:
        base += 0.05 * alc
    elif alc > 2.0:
        base -= 0.06 * (alc - 2.0)

    # 体能：长期不动的人，这一轴也会钝一点
    fit = _f(life.get("fitness"), 0.5)
    base += (fit - 0.5) * 0.08

    # 基线个体差异：乘性缩放，只改音量不改方向
    lb = TR.get(body, "libido_base", 0.54)
    base *= 0.72 + 0.60 * ((lb - 0.40) / 0.28)

    base = max(0.02, min(1.0, base))
    return {"drive": round(base, 3), "beard_mm": _f(st.get("beard_mm")),
            "nocturia": _f(st.get("nocturia")), "loh": _f(st.get("loh"))}


# ----------------------------------------------------------------------
# 推进
# ----------------------------------------------------------------------
def step(body: Dict[str, Any], hours: float, rng, events: List[str]) -> None:
    st = ensure(body)
    dh = max(0.0, float(hours)) / 24.0
    age = _f(body.get("age"), 30.0)
    r = body.get("repro") or {}

    # --- 体毛生长：每天约 0.3mm，长到 1.5mm 该处理了 ---
    if is_male(body) and age >= 16.0:
        rate = 0.30 * TR.get(body, "beard", 1.0)
        st["beard_mm"] = round(min(3.0, _f(st.get("beard_mm")) + rate * dh), 2)

    # --- 前列腺随年龄缓慢增大，最先出现的是夜尿 ---
    if is_male(body):
        st["nocturia"] = round(min(2.5, max(0.0, (age - 40.0) / 12.0)), 2) if age >= 40.0 else 0.0
        # 迟发性性腺功能减退：不是「中年危机」，是睾酮真的低了
        st["loh"] = round(min(1.0, (age - 45.0) / 25.0), 3) if age >= 45.0 else 0.0
    else:
        st["beard_mm"] = 0.0
        st["nocturia"] = 0.0
        st["loh"] = 0.0

    # 女性绝经后体毛会略微增多（雄激素相对占优），不写进摘要，只留数值
    if not is_male(body) and str(r.get("stage")) == "postmenopause" and age >= 55.0:
        st["beard_mm"] = round(min(0.6, _f(st.get("beard_mm")) + 0.02 * dh), 2)


# ----------------------------------------------------------------------
# 指标
# ----------------------------------------------------------------------
def modulate(body: Dict[str, Any], labs: Dict[str, float],
             vitals: Dict[str, float], derived: Dict[str, Any]) -> None:
    st = ensure(body)
    d = compute(body)
    derived["gonadal"] = round(d["drive"], 2)

    loh = _f(st.get("loh"))
    if loh > 0.1 and is_male(body):
        # 睾酮低：血红蛋白略低、肌肉少、腹部脂肪多，化验单上看得到
        if "HGB" in labs:
            labs["HGB"] = max(110.0, float(labs["HGB"]) - 6.0 * loh)
        derived["loh"] = round(loh, 2)

    if _f(st.get("nocturia")) > 0.5:
        derived["nocturia"] = round(_f(st.get("nocturia")), 1)
    if _f(st.get("beard_mm")) >= 1.4:
        derived["needs_grooming"] = 1


# ----------------------------------------------------------------------
# 症状与摘要
# ----------------------------------------------------------------------
def symptoms(body: Dict[str, Any]) -> List[Tuple[str, float]]:
    st = ensure(body)
    if not is_male(body):
        return []
    out: List[Tuple[str, float]] = []
    loh = _f(st.get("loh"))
    if loh > 0.35:
        out.append(("提不起劲，练也练不动", min(0.8, loh)))
        out.append(("腹部脂肪在增加", min(0.7, loh * 0.8)))
    return out


def summary(body: Dict[str, Any]) -> str:
    """体检卡片用。注入块不出现这一行。"""
    if _f(body.get("age"), 30.0) < 15.0:
        return ""
    d = compute(body)
    v = _f(d["drive"])
    if v >= 0.70:
        word = "偏高"
    elif v >= 0.52:
        word = "中上"
    elif v >= 0.40:
        word = "中位"
    elif v >= 0.22:
        word = "偏淡"
    else:
        word = "低平"
    bits = [f"性腺轴 {v:.2f}（{word}）"]
    if is_male(body):
        st = ensure(body)
        if _f(st.get("loh")) > 0.2:
            bits.append("性腺功能随年龄下降")
        if _f(st.get("nocturia")) > 0.5:
            bits.append("夜间需起夜")
        if _f(st.get("beard_mm")) >= 1.4:
            bits.append("该修整仪容了")
    return "，".join(bits)


def line(body: Dict[str, Any]) -> str:
    """注入块只保留完全中性的一条：仪容。其余不出现。"""
    st = ensure(body)
    if is_male(body) and _f(st.get("beard_mm")) >= 1.8:
        return "下巴一片扎手，该刮了"
    return ""
