"""物质代谢：酒和咖啡在体内是有曲线的。

为什么需要这个
    原来 life["alcohol"] 是一个「每天几杯」的习惯值，直接拿去扣肝脏健康。
    问题是它永不衰减：设成两杯就是一辈子两杯，晚上扣一次肝、白天还在扣，
    而且这个人永远不会有醉意，也永远不会有宿醉的第二天早上。

    真实的酒精是零级消除：每小时固定掉 0.15 g/L 左右，与浓度无关。所以
    「喝了三杯」是一个持续四五个小时的过程，不是一个瞬时状态。宿醉出现
    在血酒精归零之后，不是「还在醉」的时候——这一点很多模拟都写反了。

咖啡因
    一级消除，半衰期五小时左右。它的意义主要在两处：一是推迟入睡（下午
    三点的那杯咖啡，到晚上十一点还剩四分之一），二是心率与夜尿。深度
    睡眠不受它影响，受影响的是「能不能睡着」。

一条不做的事
    不做「摄入量→永久伤害」的直接映射。肝损伤仍然由疾病与器官那套管线
    负责，这里只提供浓度，器官损伤读浓度自己算。两套规则分开，改一边
    不会悄悄改坏另一边。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from . import body as B

ETOH_ELIM = 0.15          # g/L/h，零级消除
CAFF_HALF = 5.0           # 小时
CUP_ETOH_BAC = 0.20       # 一杯标准酒对 70kg 成人约 0.02% BAC = 0.20 g/L
CUP_CAFF_MG = 85.0        # 一杯咖啡


def new_state() -> Dict[str, float]:
    return {
        "etoh": 0.0,        # 当前血酒精 g/L
        "caff": 0.0,        # 体内咖啡因 mg
        "peak": 0.0,        # 本轮的峰值，用来判断会不会宿醉
        "hang": 0.0,        # 宿醉剩余小时
        "since": -1.0,      # 上次喝酒的时刻（小时），-1 表示没喝过
    }


def ensure(body: Dict[str, Any]) -> Dict[str, Any]:
    st = body.get("subs")
    if not isinstance(st, dict):
        st = new_state()
        body["subs"] = st
    for k, v in new_state().items():
        st.setdefault(k, v)
    return st


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


# ----------------------------------------------------------------------
# 摄入
# ----------------------------------------------------------------------
def tick(body: Dict[str, Any], hour: float, dt: float, rng,
         events: List[str]) -> None:
    st = ensure(body)
    life = body.get("life") or {}
    weight = max(35.0, float(B.bmi(body) or 22.5) * 0.0 + 70.0)
    try:
        h_m = float(body.get("height", 172.0)) / 100.0
        weight = max(35.0, 22.5 * h_m * h_m * (0.55 + 0.45 * float(
            (body.get("organs") or {}).get("fat", 1.0))))
    except Exception:
        pass

    # ---- 喝 ----
    habit = max(0.0, float(life.get("alcohol", 0.0) or 0.0))
    # 习惯是「每天几杯」，摊在晚饭到睡前这四个小时里。一晚两杯的人在
    # 19~22 点之间大概每两小时喝一杯。
    if habit > 0 and 19.0 <= hour < 22.5:
        # 「每天四杯」不是每小时一杯慢慢抿到半夜，而是晚饭这两三个小时
        # 里喝完。所以按每小时的杯数抽，一小时内可以不止一杯——不然
        # 摄入永远追不上 0.15 g/L·h 的消除速度，喝一斤白酒都不上头。
        rate = habit / 3.5 * dt
        n = int(rate)
        if rng.random() < rate - n:
            n += 1
        for _ in range(n):
            st["etoh"] = _clip(st["etoh"] + CUP_ETOH_BAC * (70.0 / weight), 0.0, 4.0)
            st["peak"] = max(float(st["peak"]), float(st["etoh"]))
        if n:
            st["since"] = float(body.get("clock", 0.0))
            events.append("drink")

    # ---- 咖啡 ----
    cups = max(0.0, float(life.get("caffeine", 0.0) or 0.0))
    if cups > 0 and 7.0 <= hour < 11.0:
        p = min(0.9, cups / 4.0 * dt)
        if rng.random() < p:
            st["caff"] = _clip(st["caff"] + CUP_CAFF_MG, 0.0, 900.0)
            events.append("coffee")

    # ---- 代谢 ----
    if st["etoh"] > 0:
        st["etoh"] = max(0.0, float(st["etoh"]) - ETOH_ELIM * dt)
    if st["caff"] > 0:
        st["caff"] = float(st["caff"]) * (0.5 ** (dt / CAFF_HALF))

    # ---- 宿醉 ----
    # 血酒精掉到接近零之后才开始难受。酒精还在血里的时候人是「晕」，
    # 不是「宿醉」——这两件事的感受完全不同，混在一起就写不出早上的戏。
    if st["hang"] > 0:
        st["hang"] = max(0.0, float(st["hang"]) - dt)
    elif st["etoh"] < 0.02 and float(st["peak"]) >= 0.55:
        st["hang"] = 6.0
        st["peak"] = 0.0
        B.push_log(body, "第二天起来头昏沉沉的", "subs")
        events.append("hangover")
    elif st["etoh"] < 0.02:
        st["peak"] = 0.0


# ----------------------------------------------------------------------
# 读取
# ----------------------------------------------------------------------
def etoh(body: Dict[str, Any]) -> float:
    return float((body.get("subs") or {}).get("etoh", 0.0) or 0.0)


def caff(body: Dict[str, Any]) -> float:
    return float((body.get("subs") or {}).get("caff", 0.0) or 0.0)


def hangover(body: Dict[str, Any]) -> float:
    return float((body.get("subs") or {}).get("hang", 0.0) or 0.0)


def etoh_word(v: float) -> str:
    """按血酒精浓度说话。

    参照的是法定与临床常用的那几个点：0.20 g/L（0.02%）开始有感觉，
    0.50 话变多，0.80 是国家标准里的醉驾线、也是"舌头开始不听话"的位置，
    1.50 走路需要扶。数字对不上这些点，写出来的醉态就是假的。
    """
    if v >= 1.50:
        return "站不太稳，说话含糊"
    if v >= 0.80:
        return "舌头有点打结"
    if v >= 0.50:
        return "脸上发热，话比平时多"
    if v >= 0.20:
        return "身上微微发暖"
    if v > 0.0:
        return "刚喝了一点"
    return ""


def line(body: Dict[str, Any]) -> str:
    """注入块里的一行。只在真的有内容时出现。"""
    bits = []
    v = etoh(body)
    w = etoh_word(v)
    if w:
        bits.append(w)
    h = hangover(body)
    if h > 0.5:
        bits.append("宿醉没散，头一跳一跳地疼" if h > 2.0 else "宿醉快过去了，还有点发虚")
    c = caff(body)
    if c >= 260.0:
        bits.append("咖啡劲还没过，心跳偏快")
    elif c >= 120.0:
        bits.append("还有点咖啡的劲")
    return "；".join(bits)


def summary(body: Dict[str, Any]) -> str:
    v = etoh(body)
    h = hangover(body)
    c = caff(body)
    parts = [f"血酒精 {v:.2f} g/L"]
    if h > 0.5:
        parts.append(f"宿醉还剩 {h:.0f} 小时")
    if c >= 50:
        parts.append(f"咖啡因 {c:.0f} mg")
    return "，".join(parts)
