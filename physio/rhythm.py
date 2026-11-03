"""昼夜节律：体温、血压、心率在一天里都不是常数。

为什么值得单独写
    人的核心体温在凌晨四五点最低、傍晚最高，差 0.5℃ 以上；血压在睡着
    之后掉一成多，清晨醒来又冲上去（晨峰），心梗与脑出血偏偏爱挑这个
    时候。这些不是细节：一个人下午说自己「有点低烧」和清晨说同一句话，
    意思完全不同。把 TEMP 写死成 36.55，等于取消了时间。

    之前精力模块已经有一条警觉度曲线，但那条曲线只影响「困不困」，
    不影响化验单上的数字。体格检查里体温正常、血压正常，与实际读数
    对不上，医生那一段就成了摆设。

相位怎么算
    所有曲线共用一条相位：以 4:30 为体温最低点。夜猫子整条曲线往后
    平移，不是把峰值抬高——晚睡型的人不是「更能扛」，是「什么都晚」。

睡着这件事
    血压与心率的夜间下降属于「睡着了」而不是「到点了」。一个人凌晨
    两点还醒着，他的血压不该摆出夜间的样子。所以这两条曲线读
    body["sleep"]["sleeping"]，体温不读——体温跟着生物钟走，跟睡没睡
    关系不大（这也是为什么熬夜的人凌晨照样发冷）。
"""

from __future__ import annotations

import math
from typing import Any, Dict, Tuple

# 体温最低点（小时）。人的核心体温在凌晨 4~5 点触底。
TEMP_NADIR = 4.5


def _chrono(body: Dict[str, Any]) -> float:
    try:
        from . import traits as TR
        return float(TR.chronotype(body))
    except Exception:
        return float(body.get("chronotype", 0.0) or 0.0)


def shift(body: Dict[str, Any]) -> float:
    """时差 / 倒班造成的相位偏移（小时）。正数表示生物钟落后于当地时间。"""
    try:
        return float(body.get("circadian_shift", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def phase_hour(hour: float, chrono: float = 0.0, jetlag: float = 0.0) -> float:
    """把钟点换算成「这个人的生物钟几点」。

    夜猫子整条曲线后移；跨时区或倒班再叠一个临时偏移。两者性质不同：
    前者是一辈子的，后者会在一两周内被拉回来（见 engine 的衰减）。
    """
    return (float(hour) - 1.6 * float(chrono or 0.0) - float(jetlag or 0.0)) % 24.0


def asleep(body: Dict[str, Any]) -> bool:
    st = body.get("sleep")
    if isinstance(st, dict) and st.get("sleeping"):
        return True
    return False


# ----------------------------------------------------------------------
# 三条曲线
# ----------------------------------------------------------------------
def temp_off(body_or_hour: Any, chrono: float = 0.0) -> float:
    """相对 36.55 的体温偏移（℃）。振幅 ±0.28，凌晨最低、傍晚最高。"""
    if isinstance(body_or_hour, dict):
        body = body_or_hour
        hour = float(body.get("clock", 0.0) or 0.0) % 24.0
        ph = phase_hour(hour, _chrono(body), shift(body))
    else:
        ph = phase_hour(float(body_or_hour), chrono)
    # 余弦：最低点在 TEMP_NADIR，最高点在它对面。
    return -0.28 * math.cos(2.0 * math.pi * (ph - TEMP_NADIR) / 24.0)


def hr_off(body: Dict[str, Any]) -> float:
    """心率偏移。睡着时低 9 次，白天在 ±3 之间随生物钟摆动。"""
    hour = float(body.get("clock", 0.0) or 0.0) % 24.0
    ph = phase_hour(hour, _chrono(body), shift(body))
    # 白天部分：午后略高、后半夜略低，振幅小
    base = 2.6 * math.cos(2.0 * math.pi * (ph - 16.0) / 24.0)
    if asleep(body):
        return base - 9.0
    return base


def bp_off(body: Dict[str, Any]) -> Tuple[float, float]:
    """(收缩压偏移, 舒张压偏移)。

    睡着时收缩压降约 12、舒张压降约 7（正常人的夜间下降）；
    醒来后的 6~9 点有一段晨峰，收缩压再抬 6。
    """
    hour = float(body.get("clock", 0.0) or 0.0) % 24.0
    ph = phase_hour(hour, _chrono(body), shift(body))
    if asleep(body):
        # 睡到后半夜最低（深睡最多），刚躺下那阵还没降下去
        return -12.0, -7.0
    sbp = 2.0 * math.cos(2.0 * math.pi * (ph - 15.0) / 24.0)
    dbp = 1.2 * math.cos(2.0 * math.pi * (ph - 15.0) / 24.0)
    if 5.5 <= ph <= 9.5:
        # 晨峰：醒来后两三小时内的陡升
        peak = math.exp(-((ph - 7.5) ** 2) / 2.2)
        sbp += 6.0 * peak
        dbp += 3.0 * peak
    return sbp, dbp


def summary(body: Dict[str, Any]) -> str:
    """一行，给「一天里什么时候最容易出事」这类问句用。"""
    hour = float(body.get("clock", 0.0) or 0.0) % 24.0
    if asleep(body):
        return "夜间，血压与心率都在低点"
    ph = phase_hour(hour, _chrono(body))
    if 5.5 <= ph <= 9.5:
        return "清晨，血压正在往上冲"
    if 13.0 <= ph <= 15.0:
        return "午后低谷，反应比上午慢"
    if ph >= 22.0 or ph <= 1.0:
        return "已经过了平时睡觉的点"
    return ""
