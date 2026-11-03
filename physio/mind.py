"""情绪落到身体上：心里的事不会只写在脸上。

为什么需要这一层
    原来只有「身体 -> 精神」一条通路（physio.couple 写炎症、皮质醇进
    bio）。反过来没有：一个角色刚被骂完，情绪模块里 anger 已经 0.8 了，
    心率还是 72、血压还是 112/70、体检单上写着「状态还行」。这在真实
    的人身上不可能——生气的时候太阳穴跳、手发凉、说话变冲，是有生理
    基础的反应，不是修辞。

    插件叫「身心状态」，缺了这一半，等于只有身没有心。

怎么算
    每种情绪有自己的生理签名：愤怒推心率与收缩压、恐惧推心率与呼吸、
    悲伤压低体温并抬高痛觉、愉悦降低痛觉。强度按情绪强度线性叠加，
    总量再做饱和——同时怕又气时心率不会叠加到 130。

    衰减按小时算，半衰期约 1.8 小时。真实情绪的身体反应就是这个量级：
    气头上心跳快半小时，一两个小时后只剩一点余温。用「每轮乘个系数」
    的话，两轮之间隔了三小时和隔了三秒会得到同样的衰减，那是假的。

    这只管**急性**反应。长期的低落、焦虑对免疫和内分泌的影响走的是
    psyche 的生化通路，不在这里重复实现。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

KEY = "mind"

# 情绪 -> 生理签名。数值是「该情绪强度 1.0 时」的满额效应，
# 实际按当前强度线性缩放。
SIG: Dict[str, Dict[str, float]] = {
    # 恐惧：交感激活最典型的一套——心率快、呼吸浅快、手脚发凉
    "fear":     {"hr": 13.0, "rr": 3.2, "sbp": 8.0, "dbp": 4.0,
                 "temp": -0.05, "pain": 0.12, "load": 0.07},
    # 愤怒：心率与收缩压一起上，痛觉反而钝一点（激越时的真实现象）
    "anger":    {"hr": 14.0, "rr": 1.8, "sbp": 13.0, "dbp": 8.0,
                 "temp": 0.12, "pain": -0.06, "load": 0.06},
    # 悲伤：副交感占优，体温略低，痛觉阈值下降
    "sadness":  {"hr": 2.5, "rr": 0.0, "sbp": 1.5, "dbp": 0.0,
                 "temp": -0.09, "pain": 0.18, "load": 0.10},
    "despair":  {"hr": 1.0, "rr": -0.6, "sbp": -1.0, "dbp": 0.0,
                 "temp": -0.12, "pain": 0.22, "load": 0.14},
    "shame":    {"hr": 6.0, "rr": 0.4, "sbp": 3.0, "dbp": 1.0,
                 "temp": 0.10, "pain": 0.08, "load": 0.05},
    "guilt":    {"hr": 3.0, "rr": 0.0, "sbp": 1.0, "dbp": 0.0,
                 "temp": 0.03, "pain": 0.06, "load": 0.05},
    "disgust":  {"hr": 3.5, "rr": 0.6, "sbp": 2.0, "dbp": 1.0,
                 "temp": 0.02, "pain": 0.05, "load": 0.03},
    "jealousy": {"hr": 6.0, "rr": 0.5, "sbp": 5.0, "dbp": 3.0,
                 "temp": 0.04, "pain": 0.05, "load": 0.05},
    "surprise": {"hr": 7.0, "rr": 1.4, "sbp": 4.0, "dbp": 2.0,
                 "temp": 0.0, "pain": -0.03, "load": 0.03},
    # 愉快与亲近：心率略升（兴奋），痛觉明显钝化，负荷反而下降
    "joy":      {"hr": 4.0, "rr": 0.3, "sbp": 1.5, "dbp": 0.0,
                 "temp": 0.02, "pain": -0.14, "load": -0.06},
    "hope":     {"hr": 2.0, "rr": 0.0, "sbp": 0.5, "dbp": 0.0,
                 "temp": 0.0, "pain": -0.08, "load": -0.04},
    "love":     {"hr": 3.0, "rr": 0.2, "sbp": 0.5, "dbp": 0.0,
                 "temp": 0.03, "pain": -0.12, "load": -0.05},
    "pride":    {"hr": 3.0, "rr": 0.2, "sbp": 2.0, "dbp": 1.0,
                 "temp": 0.02, "pain": -0.06, "load": -0.03},
}

# 饱和度：三种情绪同时在场时不能把心率叠到 130。
CAP = {"hr": 22.0, "rr": 6.0, "sbp": 18.0, "dbp": 12.0, "temp": 0.25, "pain": 0.35}

HALF_LIFE_H = 1.8


def new_state() -> Dict[str, Any]:
    return {"emo": {}, "at": 0.0}


def ensure(body: Dict[str, Any]) -> Dict[str, Any]:
    st = body.get(KEY)
    if not isinstance(st, dict):
        st = new_state()
        body[KEY] = st
    st.setdefault("emo", {})
    st.setdefault("at", 0.0)
    return st


def set_state(body: Dict[str, Any], emo: Dict[str, float]) -> None:
    """把这一刻的情绪存下来，记上时间。之后按小时衰减。"""
    st = ensure(body)
    st["emo"] = {k: float(v) for k, v in (emo or {}).items()
                 if k in SIG and float(v or 0.0) > 0.01}
    st["at"] = float(body.get("clock", 0.0) or 0.0)


def current(body: Dict[str, Any]) -> Dict[str, float]:
    """当前的（已衰减的）情绪强度。"""
    st = ensure(body)
    clock = float(body.get("clock", 0.0) or 0.0)
    dt = max(0.0, clock - float(st.get("at", clock) or clock))
    if dt <= 0.0:
        return dict(st.get("emo") or {})
    k = 0.5 ** (dt / HALF_LIFE_H)
    return {e: v * k for e, v in (st.get("emo") or {}).items() if v * k > 0.01}


# ----------------------------------------------------------------------
# 效应
# ----------------------------------------------------------------------
def effects(body: Dict[str, Any]) -> Dict[str, float]:
    """情绪对体征、痛觉、精力负荷的增量。"""
    cur = current(body)
    out = {k: 0.0 for k in ("hr", "rr", "sbp", "dbp", "temp", "pain", "load")}
    for e, v in cur.items():
        sig = SIG.get(e)
        if not sig:
            continue
        for k in out:
            out[k] += float(sig.get(k, 0.0)) * v
    for k, cap in CAP.items():
        out[k] = max(-cap, min(cap, out[k]))
    return out


def pain_gain(body: Dict[str, Any]) -> float:
    """痛觉倍率。1.0 是平时，怕/低落时更高，高兴时更低。"""
    return max(0.75, min(1.45, 1.0 + effects(body)["pain"]))


def load(body: Dict[str, Any]) -> float:
    """情绪对精力的消耗。负面情绪是真实的内耗，正面情绪是真实的回血。"""
    return max(-0.10, min(0.20, effects(body)["load"]))


def symptoms(body: Dict[str, Any]) -> List[Tuple[str, float]]:
    """给症状表用的版本。"""
    e = effects(body)
    out: List[Tuple[str, float]] = []
    # 门槛不能定在「暴怒」那么高：平时被顶一句，心率涨六七次、
    # 收缩压涨七八毫米汞柱，当事人是能感觉到的。定太高就只有吵架
    # 才写身体，日常的那种不痛快全丢了。
    if e["hr"] >= 7.0:
        out.append(("心跳比平时快", min(0.7, e["hr"] / 26.0)))
    if e["sbp"] >= 7.0:
        out.append(("太阳穴一跳一跳的", min(0.6, e["sbp"] / 28.0)))
    if e["rr"] >= 2.5:
        out.append(("胸口发闷，得深吸一口气", min(0.5, e["rr"] / 9.0)))
    if e["temp"] <= -0.06:
        out.append(("手脚发凉", min(0.4, -e["temp"] * 3.0)))
    elif e["temp"] >= 0.09:
        out.append(("脸上发烫", min(0.4, e["temp"] * 3.0)))
    return out


def summary(body: Dict[str, Any]) -> str:
    cur = current(body)
    if not cur:
        return "情绪已经平下来了"
    top = sorted(cur.items(), key=lambda kv: -kv[1])[:2]
    names = {"fear": "不安", "anger": "烦躁", "sadness": "低落", "despair": "绝望",
             "shame": "羞愧", "guilt": "愧疚", "disgust": "反感", "jealousy": "吃味",
             "surprise": "惊", "joy": "愉快", "hope": "期待", "love": "亲近",
             "pride": "得意"}
    return "、".join(f"{names.get(k, k)} {v:.1f}" for k, v in top)
