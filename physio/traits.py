"""个体差异：两个人同岁、同性、同体型，也不该是同一台机器。

为什么要有这一层
    修完昼夜节律与生命周期之后还剩一个问题：所有健康人算出来的静息
    心率都是 72，所有人体温都是 36.55，所有人被同一个病缠上时喊的疼
    一样重。那不是「一个人」，那是「一份体检模板」。真实的人在同样的
    身高体重下，静息心率能差出二十次，睡眠需求能差出两小时，疼痛敏感
    度能差一倍。

    这些差异不是随机噪声，是一个人稳定的属性：他一直是那个心跳偏快、
    睡得少但够用、怕疼的人。所以必须由 seed 决定且永不变——每次重启
    都换一副身体的话，「这个人」就不成立了。

管什么，不管什么
    这里只管**基线**：心率偏移、体温偏移、疼痛敏感度、免疫强弱、睡眠
    需求、昼夜相位（早鸟/夜猫子）、基础代谢。当前状态（累了、发烧了、
    喝了两杯）不在这里，那是 energy / labs / substance 的活。

    也不碰疾病概率的绝对水平——那只受 onset_scale 控制，便于调参时
    一把改全。这里只给一个相对乘数：免疫弱的人更容易被传染，但不会
    因为免疫弱就让全世界的病都变多。
"""

from __future__ import annotations

import random
from typing import Any, Dict

KEY = "traits"

# 每个字段的取值区间。区间是照真实人群分布定的：
#   静息心率 ±7 次覆盖多数成年人（55~85）
#   口腔体温 ±0.18℃ 是一个人体温日间均值相对 36.55 的正常漂移
#   疼痛敏感度 0.72~1.32 大致对应「不太怕疼」到「很怕疼」
#   睡眠需求 6.6~8.9 小时，短睡者与长睡者的常见区间
#   昼夜相位 ±1.6 小时（乘以 1.6 后是 ±2.6 小时，覆盖极端夜猫子）
SPEC: Dict[str, tuple] = {
    "hr_off": (-7.0, 8.0),
    "temp_off": (-0.18, 0.18),
    "pain_sens": (0.72, 1.32),
    "immune": (0.70, 1.34),
    "sleep_need": (6.6, 8.9),
    "chronotype": (-1.6, 1.6),
    "bmr": (0.92, 1.10),
    # --- 生殖与性别差异 ---
    # 经前综合征的个体差异比周期长度还大：有人几乎没感觉，有人被拖垮
    # 半个月。这一项只对女性有意义，但不分性别地生成，省得再开一套。
    "pms_sens": (0.35, 0.95),
    # 胡须生长速率（男性）：决定多久需要刮一次，也决定早上起来扎不扎手
    "beard": (0.60, 1.40),
    # 性腺轴基线：两性共用，决定这个人的内分泌活动整体偏高还是偏低
    "libido_base": (0.40, 0.68),
}


def new_traits(seed: int = 20261030) -> Dict[str, float]:
    """由 seed 生成一份稳定的体质。同一 seed 永远给同一副身体。"""
    rng = random.Random(int(seed) * 7919 + 101)
    t: Dict[str, float] = {}
    for k, (lo, hi) in SPEC.items():
        if k == "chronotype":
            # 中间多两头少：多数人是中间型，极端夜猫子是少数。
            # 用两次均匀分布取均值近似钟形，比 gauss 更容易限幅。
            v = (rng.uniform(lo, hi) + rng.uniform(lo, hi)) / 2.0
        else:
            v = rng.uniform(lo, hi)
        t[k] = round(v, 3)
    return t


def ensure(body: Dict[str, Any]) -> Dict[str, float]:
    """老存档没有体质：按它的 seed 补一份，此后不再变。"""
    t = body.get(KEY)
    if isinstance(t, dict) and all(k in t for k in SPEC):
        return t  # type: ignore[return-value]
    seed = int(body.get("seed", 20261030) or 20261030)
    fresh = new_traits(seed)
    if isinstance(t, dict):
        fresh.update({k: v for k, v in t.items() if k in SPEC})
    body[KEY] = fresh
    return fresh


def drift_of(body: Dict[str, Any], key: str) -> float:
    """体质被经历改写的那一部分。与 seed 基线分开存，两者相加才是当前值。"""
    d = body.get("traits_drift")
    if not isinstance(d, dict):
        return 0.0
    try:
        return float(d.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def get(body: Dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(ensure(body).get(key, default)) + drift_of(body, key)
    except Exception:
        return float(default)


def step(body: Dict[str, Any], hours: float) -> None:
    """长期经历会把「底子」磨动一点。

    原来体质是一辈子不动的常数。这在两个月里看不出问题，但练了三年的人
    静息心率还是当初那个数，就说不通了：有氧训练压低静息心率是这一层
    最确定的一件事。同理，慢性疼痛会把痛觉敏感度往上调（中枢敏化）。

    改动很慢（以周计），幅度也有限（心率最多 -6，痛敏最多 +0.30），
    不会盖过 seed 带来的人格差异——「这个人」还是原来那个人，只是老了几岁、
    练了几年。
    """
    if hours <= 0:
        return
    weeks = float(hours) / (24.0 * 7.0)
    if weeks <= 0:
        return
    life = body.get("life") or {}
    d = body.setdefault("traits_drift", {})

    # 体能：0.55 是常态，练到 0.9 差不多是常年运动的人
    fit = float(life.get("fitness", 0.55) or 0.55)
    tgt_hr = -6.0 * max(0.0, min(1.0, (fit - 0.55) / 0.35))
    cur = float(d.get("hr_off", 0.0) or 0.0)
    d["hr_off"] = round(cur + (tgt_hr - cur) * (1.0 - _exp(-weeks / 26.0)), 3)

    # 慢性疼痛：有长期疼痛的病在身，痛敏往上走
    try:
        from .diseases import DISEASES as _DS

        chronic_pain = 0
        for c in body.get("conditions") or []:
            spec = _DS.get(c.get("code", "")) or {}
            # 只算「长期、以疼痛为主」的病。dur is None 在这一套目录里同时
            # 罩着心梗、主动脉夹层这类急症（它们也疼，也留着不回），把
            # 它们计入会让一次心梗变成三年的痛觉敏化。急性的一律排除。
            if spec.get("acute"):
                continue
            if spec.get("dur") is None and float(spec.get("pain", 0.0) or 0.0) >= 0.4:
                if float(c.get("sev", 0.0) or 0.0) > 0.1:
                    chronic_pain += 1
    except Exception:
        chronic_pain = 0
    tgt_pain = 0.30 * min(1.0, chronic_pain / 2.0)
    cur = float(d.get("pain_sens", 0.0) or 0.0)
    d["pain_sens"] = round(cur + (tgt_pain - cur) * (1.0 - _exp(-weeks / 40.0)), 3)

    # 枯了就清掉，别让 drift 字典无限长
    for k in list(d):
        if abs(float(d[k] or 0.0)) < 1e-4:
            d.pop(k, None)


def _exp(x: float) -> float:
    import math

    return math.exp(-abs(x))


def chronotype(body: Dict[str, Any]) -> float:
    """>0 夜猫子，<0 早鸟，0 中间型。"""
    return get(body, "chronotype", 0.0)


def sleep_need(body: Dict[str, Any]) -> float:
    return get(body, "sleep_need", 7.5)


def pain_sens(body: Dict[str, Any]) -> float:
    return get(body, "pain_sens", 1.0)


def immune(body: Dict[str, Any]) -> float:
    return get(body, "immune", 1.0)


# ----------------------------------------------------------------------
# 说人话
# ----------------------------------------------------------------------
def _chrono_word(c: float) -> str:
    if c <= -1.0:
        return "极早起型"
    if c <= -0.35:
        return "早起型"
    if c < 0.35:
        return "中间型"
    if c < 1.0:
        return "晚睡型"
    return "极晚睡型"


def _hr_word(off: float) -> str:
    if off >= 4.0:
        return "心率偏快"
    if off <= -4.0:
        return "心率偏慢"
    return "心率中等"


def _pain_word(s: float) -> str:
    if s >= 1.15:
        return "怕疼"
    if s <= 0.85:
        return "耐疼"
    return "对疼痛反应一般"


def _immune_word(v: float) -> str:
    if v >= 1.12:
        return "很少生病"
    if v <= 0.86:
        return "容易中招"
    return "抗病力中等"


def summary(body: Dict[str, Any]) -> str:
    """体检报告里的一行。不进注入块——体质是背景，不是每句话都要交代的事。"""
    t = ensure(body)
    return "、".join([
        _chrono_word(float(t["chronotype"])),
        _hr_word(float(t["hr_off"])),
        _pain_word(float(t["pain_sens"])),
        _immune_word(float(t["immune"])),
        f"每晚需要 {float(t['sleep_need']):.1f} 小时睡眠",
    ])
