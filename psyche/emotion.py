"""情感层：把类脑生化与本轮社会刺激合成为「此刻的情绪」。

与 dynamics 的分工
    dynamics 演化的是生化与环路（多巴胺、皮质醇、杏仁核……）。这一层
    把那些数字与本轮对话造成的冲击合成情绪水平，注入时用自然语言描述，
    而不是让模型自己去读 0.61 这样的数——模型读到数会复述数。

三条约束
    1. 只走虚拟时钟。衰减按每轮推进的小时数算，不看墙钟。几十秒内
       连续几轮时，真实经过时间约为 0，衰减系数约为 1，情绪会钉死在
       峰值上再也不落。
    2. 状态全是标量。13 个情感分量加一条心境基线，直接进存档。
    3. 底色与尖峰分离。生化给慢变底色（按 z 分数、权重小），刺激给
       快变尖峰（按评估维度与强度）。两者混在一起，一次争吵就能改变
       人格底色。

半衰期取的是量级而非精确值：惊讶分钟级、愤怒小时级、悲伤与绝望
以天计。目的是让「隔了六小时还在气头上」不可能，「低落一整天」
可能。
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Tuple

# 键 -> (中文, 极性, 半衰期/小时)
EMOTIONS: Dict[str, Tuple[str, str, float]] = {
    "joy": ("快乐", "pos", 5.0),
    "hope": ("期待", "pos", 26.0),
    "love": ("亲近", "pos", 72.0),
    "pride": ("得意", "pos", 9.0),
    "sadness": ("低落", "neg", 30.0),
    "anger": ("烦躁", "neg", 1.8),
    "fear": ("不安", "neg", 1.2),
    "disgust": ("厌恶", "neg", 3.0),
    "shame": ("羞愧", "neg", 11.0),
    "guilt": ("愧疚", "neg", 20.0),
    "jealousy": ("嫉妒", "neg", 34.0),
    "despair": ("绝望", "neg", 90.0),
    "surprise": ("惊讶", "neu", 0.35),
}

HIGH_AROUSAL = {"anger": 1.0, "fear": 1.0, "surprise": 0.85, "joy": 0.55,
                "jealousy": 0.5, "pride": 0.4}
LOW_AROUSAL = {"sadness": 1.0, "disgust": 0.5, "shame": 0.7, "guilt": 0.6,
               "despair": 0.8}

# 分量词本身就重（「绝望」「羞愧」「嫉妒」）。数值低的时候念出来会过火，
# 0.13 的绝望写进注入段，模型会演成 0.8。低于门槛就不作为主导、也不列出。
HEAVY = {"despair", "jealousy", "shame", "guilt", "disgust"}
HEAVY_FLOOR = 0.20

# 评估维度 -> 情感增量。维度定义见 appraisal.EXTRACT_PROMPT。
DIM_TO_EMOTION: Dict[str, Dict[str, float]] = {
    "threat":    {"fear": 0.85, "anger": 0.25},
    "rejection": {"sadness": 0.70, "shame": 0.40, "anger": 0.22},
    "praise":    {"joy": 0.62, "pride": 0.55, "love": 0.16},
    "control":   {"anger": 0.45, "fear": 0.30, "shame": 0.26},
    "intimacy":  {"love": 0.80, "joy": 0.42},
    "chaos":     {"surprise": 0.45, "fear": 0.30},
    "calm":      {"joy": 0.22},
    "help":      {"hope": 0.52, "joy": 0.26},
    "hostility": {"anger": 0.80, "fear": 0.28},
    "absurd":    {"surprise": 0.52, "disgust": 0.32},
    "farewell":  {"sadness": 0.58, "despair": 0.26},
    "medical":   {"fear": 0.34, "sadness": 0.22, "hope": 0.16},
}

# 有些维度是「压下去」而不是「顶上来」：安抚不会凭空生出快乐，
# 它降低的是恐惧与敌意。单靠正向增量做不出这个效果。
DIM_TO_DAMP: Dict[str, Dict[str, float]] = {
    "calm": {"fear": 0.50, "anger": 0.45, "sadness": 0.15, "surprise": 0.30},
    "help": {"despair": 0.35, "fear": 0.18},
    "intimacy": {"fear": 0.20, "shame": 0.15},
}

# 生化 -> 情感底色。权重乘 z 分数，再乘 BASE_GAIN，每轮加一点。
BIO_TO_EMOTION: Dict[str, Dict[str, float]] = {
    "serotonin":      {"sadness": -0.45, "anger": -0.30, "joy": 0.20},
    "norepinephrine": {"fear": 0.40, "anger": 0.20, "surprise": 0.10},
    "cortisol":       {"fear": 0.30, "despair": 0.12, "joy": -0.20},
    "crh":            {"fear": 0.16, "despair": 0.06},
    "da_tonic":       {"joy": 0.35, "hope": 0.22},
    "da_phasic":      {"surprise": 0.18, "joy": 0.15},
    "oxytocin":       {"love": 0.40, "joy": 0.12},
    "gaba":           {"fear": -0.35, "anger": -0.22},
    "bdnf":           {"hope": 0.20, "despair": -0.14},
    "il6":            {"sadness": 0.18, "joy": -0.16},
    "adenosine":      {"sadness": 0.10, "joy": -0.10},
    "melatonin":      {"joy": -0.10, "sadness": 0.08},
    "t3":             {"joy": 0.14, "sadness": -0.12},
}

BASE_GAIN = 0.12        # 生化底色的每轮增益
SPIKE_GAIN = 0.85       # 刺激尖峰的增益
MOOD_FOLLOW = 0.04      # 心境基线跟随当前效价的速度

# 词表兜底。只在评估拿不到维度时使用（没配模型、超时、解析失败）。
# 它只影响情绪，不改症状、不参与诊断——猜错情绪只是这一轮语气偏一点，
# 猜错病名会污染整条病程。两者代价不同，所以这里可以猜。
LEXICON: Dict[str, List[Tuple[str, float]]] = {
    "anger": [("骂", 0.9), ("生气", 0.9), ("愤怒", 1.0), ("火大", 0.9), ("委屈", 0.7),
              ("不公平", 0.9), ("欺负", 0.9), ("讨厌", 0.6), ("烦", 0.45), ("吵", 0.5),
              ("滚开", 0.9), ("滚蛋", 0.9), ("闭嘴", 0.8), ("废物", 0.7), ("没用", 0.55)],
    "sadness": [("难过", 0.9), ("伤心", 0.9), ("失落", 0.8), ("想哭", 0.9), ("哭", 0.7),
                ("失去", 0.8), ("去世", 1.0), ("分手", 0.9), ("孤独", 0.7), ("没意思", 0.6)],
    "fear": [("害怕", 0.9), ("恐惧", 1.0), ("焦虑", 0.7), ("不安", 0.6), ("吓", 0.6),
             ("担心", 0.6), ("危险", 0.8), ("威胁", 0.9)],
    "joy": [("开心", 0.9), ("高兴", 0.9), ("太好了", 0.8), ("顺利", 0.6),
            ("成功", 0.8), ("完成", 0.6), ("赢了", 0.7), ("谢谢", 0.4),
            ("放心", 0.4)],
    "love": [("爱你", 0.9), ("喜欢你", 0.8), ("想你", 0.7), ("抱抱", 0.8), ("亲爱", 0.7)],
    "shame": [("丢人", 0.8), ("羞愧", 0.9), ("没脸", 0.9), ("不好意思", 0.5)],
    "guilt": [("对不起", 0.7), ("抱歉", 0.7), ("是我的错", 0.9), ("后悔", 0.8)],
    "despair": [("撑不住", 0.9), ("没希望", 1.0), ("熬不下去", 0.9), ("活不下去", 1.0)],
    "hope": [("会好的", 0.7), ("期待", 0.6), ("有希望", 0.8)],
}
_RELIEF = [("好些了", 0.7), ("好多了", 0.7), ("松了口气", 0.8), ("没事了", 0.6),
           ("轻松", 0.6)]

STYLES = {
    "balanced": {"decay": 1.0, "volatility": 0.020},
    "labile":   {"decay": 0.75, "volatility": 0.042},
    "stable":   {"decay": 1.35, "volatility": 0.008},
}


def _clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def blank() -> Dict[str, float]:
    e = {k: 0.0 for k in EMOTIONS}
    e["mood"] = 0.0
    return e


def ensure(st) -> Dict[str, float]:
    """取出（必要时补建）情感状态。旧存档没有这个字段。"""
    e = getattr(st, "emo", None)
    if not isinstance(e, dict):
        e = blank()
        st.emo = e
    for k in EMOTIONS:
        e[k] = _clip(e.get(k, 0.0) or 0.0)
    e["mood"] = max(-1.0, min(1.0, float(e.get("mood", 0.0) or 0.0)))
    return e


# ---------------------------------------------------------------------------
# 派生量
# ---------------------------------------------------------------------------
def dimensions(e: Dict[str, float]) -> Dict[str, Any]:
    pos = sum(e.get(k, 0.0) for k, (_, pol, _) in EMOTIONS.items() if pol == "pos")
    neg = sum(e.get(k, 0.0) for k, (_, pol, _) in EMOTIONS.items() if pol == "neg")

    # 饱和映射而不是比例除法。比例除法在多个分量同时在场时会失控：
    # 「烦 0.3 + 累 0.3 + 怕 0.3」算出来是 −0.6，读起来像崩溃；实际只是
    # 一个普通的不顺下午。tanh 让方向单调、幅度有界，小值近似线性。
    valence = math.tanh((pos - neg) / 1.1)

    high = sum(e.get(k, 0.0) * w for k, w in HIGH_AROUSAL.items())
    low = sum(e.get(k, 0.0) * w for k, w in LOW_AROUSAL.items())
    arousal = _clip(0.5 + 0.5 * (high - 0.55 * low))

    dominance = _clip(0.5 + 0.30 * e.get("anger", 0.0) + 0.35 * e.get("pride", 0.0)
                      - 0.30 * e.get("fear", 0.0) - 0.22 * e.get("shame", 0.0)
                      - 0.18 * e.get("despair", 0.0))

    arousal_dev = arousal * 2.0 - 1.0
    intensity = min(1.0, math.sqrt(valence ** 2 + arousal_dev ** 2) / math.sqrt(2.0))

    dom_key, dom_val = "neutral", 0.0
    for k in EMOTIONS:
        v = e.get(k, 0.0)
        if k in HEAVY and v < HEAVY_FLOOR:
            continue
        if v > dom_val:
            dom_key, dom_val = k, v
    if dom_val < 0.10:
        dom_key = "neutral"

    return {
        "valence": max(-1.0, min(1.0, valence)),
        "arousal": arousal,
        "dominance": dominance,
        "intensity": intensity,
        "dominant": dom_key,
        "dominant_zh": EMOTIONS[dom_key][0] if dom_key in EMOTIONS else "平静",
        "dominant_value": dom_val,
        "positive": pos,
        "negative": neg,
    }


def top_emotions(e: Dict[str, float], n: int = 3, floor: float = 0.05) -> List[Tuple[str, str, float]]:
    rows = [(k, EMOTIONS[k][0], e.get(k, 0.0)) for k in EMOTIONS
            if not (k in HEAVY and e.get(k, 0.0) < HEAVY_FLOOR)]
    rows = [r for r in rows if r[2] >= floor]
    rows.sort(key=lambda r: r[2], reverse=True)
    return rows[:n]


def level(intensity: float) -> str:
    if intensity < 0.12:
        return "平"
    if intensity < 0.30:
        return "轻微"
    if intensity < 0.55:
        return "明确"
    if intensity < 0.78:
        return "强"
    return "极强"


# ---------------------------------------------------------------------------
# 演化
# ---------------------------------------------------------------------------
def _lexicon_spike(e: Dict[str, float], text: str) -> List[str]:
    """词表兜底：命中哪类就算哪类，不给复合。返回命中的情感键。"""
    s = text or ""
    if not s:
        return []
    best_key, best = None, 0.0
    for emo, words in LEXICON.items():
        score = sum(w for kw, w in words if kw in s)
        if score > best:
            best_key, best = emo, score
    relief = sum(w for kw, w in _RELIEF if kw in s)

    if relief > 0 and relief >= best:
        amp = min(1.0, relief)
        for k, w in (("fear", 0.45), ("anger", 0.40), ("sadness", 0.20),
                     ("despair", 0.25)):
            e[k] = _clip(e[k] * (1.0 - w * amp))
        e["joy"] = _clip(e["joy"] + 0.30 * amp * (1.0 - e["joy"]))
        return ["relief"]

    if not best_key:
        return []
    # 词表只能给个方向，不该顶到极端：同一个人每天说一句「累」，
    # 渐近累积会把它推到满，于是三天就演成重度抑郁。封在 0.55。
    amp = min(1.0, 0.15 + 0.22 * best)
    cap = 0.55
    if e[best_key] < cap:
        e[best_key] = _clip(e[best_key] + amp * (1.0 - e[best_key] / cap))
    # 高分事件会带出邻接情绪：被骂不只是愤怒，也有一点受伤
    if best >= 0.9:
        near = {"anger": "sadness", "sadness": "anger", "fear": "anger",
                "despair": "sadness", "shame": "sadness"}.get(best_key)
        if near and e[near] < cap:
            e[near] = _clip(e[near] + 0.12 * (1.0 - e[near] / cap))
    return [best_key]


def step(st, ap: Dict[str, Any] | None, hours: float,
         cfg: Dict[str, Any] | None = None, text: str = "") -> Dict[str, Any]:
    """推进一轮情感。返回本轮的变化摘要（供日志与调试）。"""
    cfg = cfg or {}
    e = ensure(st)
    hours = max(0.02, min(72.0, float(hours or 1.0)))
    style = STYLES.get(str(cfg.get("emotion_style", "balanced")), STYLES["balanced"])
    scale = float(cfg.get("emotion_persistence", 1.5))
    before = dimensions(e)

    # 1. 按虚拟时间衰减
    for k, (_zh, _pol, half) in EMOTIONS.items():
        e[k] *= 0.5 ** (hours * style["decay"] / max(0.05, half * scale))

    # 2. 生化底色：只吃 z 分数的尾部，基线附近不动
    gains: Dict[str, float] = {}
    for bio, mapping in BIO_TO_EMOTION.items():
        try:
            z = st.z_bio(bio)
        except KeyError:
            continue
        if abs(z) < 0.5:
            continue
        w = (abs(z) - 0.5) * (1 if z > 0 else -1)
        for emo, weight in mapping.items():
            gains[emo] = gains.get(emo, 0.0) + weight * w * BASE_GAIN

    # 底色只推最重的两个分量，其余打三折。皮质醇、5-HT、炎症往往同时
    # 把「低落 / 烦躁 / 不安」一起抬起来，全量叠加会把效价压到 −0.7，
    # 于是长期压力被演成重度抑郁。底色是背景，一个主调加一点余味就够。
    if gains:
        top2 = sorted(gains, key=lambda k: -abs(gains[k]))[:2]
        for emo, inc in gains.items():
            if emo not in top2:
                inc *= 0.3
            if inc > 0:
                inc *= max(0.0, 0.15 - e[emo]) / 0.15
            e[emo] = _clip(e[emo] + inc)

    # 3. 刺激尖峰
    ap = ap or {}
    inten = max(0.0, min(1.0, float(ap.get("intensity") or 0.0)))
    dims = ap.get("dims") or {}
    fired = []
    for dim, val in dims.items():
        val = max(0.0, min(1.0, float(val or 0.0)))
        if val < 0.06:
            continue
        amp = val * (0.35 + 0.75 * inten) * SPIKE_GAIN
        for emo, weight in DIM_TO_EMOTION.get(dim, {}).items():
            inc = weight * amp
            # 渐近累积：同一刺激反复出现时向 1 收敛，不线性叠到满
            e[emo] = _clip(e[emo] + inc * (1.0 - e[emo]))
        for emo, weight in DIM_TO_DAMP.get(dim, {}).items():
            e[emo] = _clip(e[emo] * (1.0 - weight * amp))
        if val >= 0.25:
            fired.append(dim)

    # 模型只给了效价没给维度时，用它兜底，别让一句话什么都没发生；
    # 连效价都没有（没配模型 / 超时 / 解析失败）才退到词表。
    if not fired:
        v = float(ap.get("valence") or 0.0)
        if abs(v) >= 0.15:
            gain = abs(v) * (0.30 + 0.60 * inten)
            if v > 0:
                e["joy"] = _clip(e["joy"] + 0.35 * gain * (1.0 - e["joy"]))
                e["hope"] = _clip(e["hope"] + 0.18 * gain * (1.0 - e["hope"]))
            else:
                e["sadness"] = _clip(e["sadness"] + 0.34 * gain * (1.0 - e["sadness"]))
                e["anger"] = _clip(e["anger"] + 0.14 * gain * (1.0 - e["anger"]))
        else:
            fired.extend(_lexicon_spike(e, text))

    # 危机把恐惧与绝望直接顶上去：这是安全阈值，不参与风格缩放
    if ap.get("crisis"):
        e["fear"] = _clip(e["fear"] + 0.35 * (1.0 - e["fear"]))
        e["despair"] = _clip(e["despair"] + 0.28 * (1.0 - e["despair"]))
        e["sadness"] = _clip(e["sadness"] + 0.25 * (1.0 - e["sadness"]))

    # 4. 心境基线：被近期效价拖动，同时被异稳态负荷压向一个下限。
    #    负荷项必须写成「向目标回归」而不是「每轮累减」：累减在长程里
    #    会把健康人的心境一路拖到 −0.7，注入段于是天天写「长期偏暗」，
    #    模型就演成慢性抑郁了。
    d = dimensions(e)
    load = float(st.meta.get("allostatic_load", 0.0))
    mood_floor = -0.20 * min(1.0, load / 0.45)      # 负荷 0.45 以上封顶
    step_h = hours / 6.0
    e["mood"] += (d["valence"] - e["mood"]) * MOOD_FOLLOW * step_h
    e["mood"] += (mood_floor - e["mood"]) * 0.035 * step_h
    e["mood"] = max(-1.0, min(1.0, e["mood"]))

    # 5. 随机涨落（个体差异，也避免曲线过于工整）
    if cfg.get("stochastic", True) and style["volatility"] > 0:
        seed = (int(st.meta.get("turn", 0)) * 7919
                + sum(ord(c) for c in str(st.meta.get("last_user", ""))[:24]))
        rng = random.Random(seed)
        for k in ("joy", "sadness", "anger", "fear", "surprise", "hope"):
            if rng.random() < 0.35:
                e[k] = _clip(e[k] + (rng.random() - 0.5) * style["volatility"] * 2.0)

    after = dimensions(e)
    return {
        "before": before,
        "after": after,
        "mood": e["mood"],
        "dims_fired": fired,
    }


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------
_LEVER = {
    "anger": "说话变短、语气变冲，对善意先怀疑；不主动解释自己为什么这样",
    "fear": "回避、反复确认、把注意力收窄到威胁上；不逞强说没事",
    "sadness": "语速慢、答非所问、把话题往回拉；不做戏剧化的哭诉",
    "despair": "不再设想以后，对任何承诺都不接；连反驳的力气都没有",
    "shame": "回避目光、自我贬低、把错往自己身上揽",
    "guilt": "补偿性示好，或反复道歉；不索取安慰",
    "disgust": "拉开距离，评价变得刻薄而简短",
    "surprise": "反应慢半拍，重复对方的话，随即回到原来的情绪",
    "joy": "愿意多说一点，愿意接对方的话头",
    "hope": "开始设想下一步，语气里有一点点余地",
    "love": "主动靠近、记住细节、愿意示弱",
    "pride": "把功劳接住，但不炫耀",
    "jealousy": "话里带刺的试探，追问对方和别人的关系",
}


def render_block(st, limit: int = 3) -> str:
    """注入段：此刻的情绪底色。写给模型，不是给人看的报表。"""
    e = ensure(st)
    d = dimensions(e)
    tops = top_emotions(e, limit)

    if d["intensity"] < 0.10:
        return ("- 此刻情绪平着，没有哪一股压过其他。不要凭空制造情绪起伏，"
                "也不要为了显得「有情感」而加戏。")

    lines = []
    if tops:
        parts = "、".join(f"{zh} {v:.2f}" for _k, zh, v in tops)
        lines.append(f"- 此刻压在最上面的是：{parts}。")
    lines.append(
        f"- 底色：{'偏负' if d['valence'] < -0.12 else ('偏正' if d['valence'] > 0.12 else '中性')}"
        f"（效价 {d['valence']:+.2f}），"
        f"{'没被激起' if d['arousal'] < 0.40 else ('绷得紧' if d['arousal'] > 0.65 else '有起伏')}"
        f"（唤醒 {d['arousal']:.2f}），整体强度 {d['intensity']:.2f}（{level(d['intensity'])}）。"
    )
    if d["dominant"] in _LEVER:
        lines.append(f"- 它落到行为上是：{_LEVER[d['dominant']]}。")
    if abs(e["mood"]) >= 0.15:
        lines.append(
            f"- 心境基线 {'偏暗' if e['mood'] < 0 else '偏亮'}（{e['mood']:+.2f}）："
            "这不是这一句话造成的，是这些天一直这样。同样的消息，落在这种底色上会比平时更重或更轻。"
        )
    lines.append(
        "- 情绪是底色，不是台词。不要报出上面这些数，也不要直接说「我现在很"
        f"{d['dominant_zh']}」；让它渗进措辞、句长、以及你不愿意接的那半句话里。"
    )
    return "\n".join(lines)


def render_report(st) -> str:
    """用户可见：/心理 情感"""
    e = ensure(st)
    d = dimensions(e)
    lines = [f"── 情绪 · 第 {int(st.meta.get('turn', 0))} 轮 ──"]
    if d["intensity"] < 0.10:
        lines.append("主调  平静 · 接近中性（强度 %.2f）" % d["intensity"])
    else:
        lines.append(f"主调  {d['dominant_zh']} · {level(d['intensity'])}"
                     f"（强度 {d['intensity']:.2f}）")
    lines.append(f"维度  效价 {d['valence']:+.2f}｜唤醒 {d['arousal']:.2f}｜支配 {d['dominance']:.2f}")
    rows = top_emotions(e, 6, floor=0.02)
    if rows:
        lines.append("分量  " + "｜".join(f"{zh} {v:.2f}" for _k, zh, v in rows))
    else:
        lines.append("分量  各维均低于 0.02")
    lines.append(f"心境基线 {e['mood']:+.2f}"
                 + ("（长期偏低，同样的刺激会更沉）" if e["mood"] < -0.15
                    else ("（长期偏亮）" if e["mood"] > 0.15 else "（接近中性）")))
    if d["dominant"] in _LEVER:
        lines.append(f"行为  {_LEVER[d['dominant']]}")
    return "\n".join(lines)
