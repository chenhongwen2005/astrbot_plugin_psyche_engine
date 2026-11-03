"""月事：周期里那些每天不一样、却很少被写进模型的部分。

为什么还要再拆一层
    lifecycle 已经有了周期骨架——四相位、雌激素孕酮曲线、基础体温、经量、
    痛经。但它只描述「周期走到第几天」，不描述**这个人今天具体怎么难受**：
    黄体末期乳房胀、肚子发胀、看谁都不顺眼、忽然想吃甜的；经期第二天
    拉肚子、恶心得吃不下；排卵那天单侧下腹抽一下。

    这些不是可有可无的装饰。它们决定角色在这一天里是「撑得住」还是
    「不想说话」，也是经前综合征（PMS）这个真实存在的诊断所依赖的素材。

三个相位各有一包东西
    黄体末期  PMS：乳房胀痛、腹胀、易激惹、嗜甜、头痛、痤疮、水肿
    月经期    经期综合征：下腹坠痛、腰酸、腹泻、恶心、乏力、情绪低落
    排卵期    排卵信号：单侧下腹隐痛、乳房敏感、基础体温抬升

    三包都只在越过阈值时输出，不越过就什么都不说——正常的一天没有台词。

失血与紊乱
    经量大的周期会累积缺铁的底子，长期下来化验单上的血红蛋白才掉得下去；
    一两个月的量大多半看不出什么，这正是缺铁性贫血在真实世界里被漏掉的
    原因。压力大、体重过低、运动过量会让周期停掉排卵（功能性下丘脑性
    闭经），这条在这里只作为「这个月没排卵」处理，不写成诊断。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

DAY = 24.0


# ----------------------------------------------------------------------
# 相位判定
# ----------------------------------------------------------------------
def _r(body: Dict[str, Any]) -> Dict[str, Any]:
    r = body.get("repro")
    return r if isinstance(r, dict) else {}


def _is_female(body: Dict[str, Any]) -> bool:
    r = _r(body)
    return str(r.get("sex") or body.get("sex") or "m") == "f"


def _reproductive(body: Dict[str, Any]) -> bool:
    r = _r(body)
    return (not r.get("pregnant")
            and str(r.get("stage") or "") in ("reproductive", "perimenopause"))


def _days_left(r: Dict[str, Any]) -> float:
    """距下次月经还有几天。黄体期固定约 14 天，所以这个数很稳。"""
    L = float(r.get("cycle_len", 28) or 28)
    d = float(r.get("cycle_day", 1.0) or 1.0)
    return L - d


# ----------------------------------------------------------------------
# 黄体末期：PMS
# ----------------------------------------------------------------------
def pms(body: Dict[str, Any]) -> Dict[str, float]:
    """经前综合征的强度。0 表示不在黄体末期或没感觉。"""
    out = {k: 0.0 for k in ("level", "breast", "bloat", "mood", "head",
                            "appetite", "acne", "constipation", "edema")}
    if not _is_female(body) or not _reproductive(body):
        return out
    r = _r(body)
    if str(r.get("phase") or "") != "luteal":
        return out
    left = _days_left(r)
    if left > 7.0 or left < 0.0:
        return out
    # 越接近月经越重，到最后一天最难受
    x = min(1.0, (7.0 - left) / 7.0)
    lvl = x ** 1.15
    # 个体差异：有人几乎没感觉，有人被 PMS 拖垮半个月。用 seed 定一个
    # 0.5~1.3 的敏感度，同一个人每个周期都一样。
    sens = 0.5 + 0.8 * float((body.get("traits") or {}).get("pms_sens", 0.55) or 0.55)
    lvl = min(1.0, lvl * sens)
    out["level"] = lvl
    out["breast"] = min(1.0, 0.70 * lvl)
    out["bloat"] = min(1.0, 0.60 * lvl)
    out["mood"] = min(1.0, 0.65 * lvl)
    out["head"] = min(1.0, 0.40 * lvl)
    out["appetite"] = min(1.0, 0.58 * lvl)
    out["acne"] = min(1.0, 0.32 * lvl)
    out["constipation"] = min(1.0, 0.30 * lvl)
    out["edema"] = min(1.0, 0.55 * lvl)
    return out


# ----------------------------------------------------------------------
# 排卵期：能自己察觉到的几个信号
# ----------------------------------------------------------------------
def ovulation_signs(body: Dict[str, Any]) -> Dict[str, float]:
    out = {"mucus": 0.0, "mittelschmerz": 0.0, "breast": 0.0}
    if not _is_female(body) or not _reproductive(body):
        return out
    r = _r(body)
    if str(r.get("phase") or "") != "ovulation":
        return out
    # 排卵是一个短窗口，最多两天。越靠近中点越明显
    L = float(r.get("cycle_len", 28) or 28)
    ov = max(10.0, L - 14.0)
    d = float(r.get("cycle_day", 1.0) or 1.0)
    close = max(0.0, 1.0 - abs(d - ov) / 1.5)
    out["mucus"] = min(1.0, 0.80 * close)
    out["mittelschmerz"] = min(1.0, 0.55 * close)
    out["breast"] = min(1.0, 0.35 * close)
    return out


# ----------------------------------------------------------------------
# 推进
# ----------------------------------------------------------------------
def step(body: Dict[str, Any], hours: float, rng, events: List[str]) -> None:
    r = _r(body)
    if not r:
        return
    r.setdefault("blood_debt", 0.0)
    r.setdefault("anovulatory", False)
    r.setdefault("lochia", 0.0)
    dh = max(0.0, float(hours)) / DAY

    if not _is_female(body):
        return

    # 失血债：经量大的人慢慢攒，攒到一定程度化验单才看得出来
    flow = float(r.get("flow", 0.0) or 0.0)
    debt = float(r.get("blood_debt", 0.0) or 0.0)
    if _reproductive(body) and flow > 0.65:
        debt += dh * 0.34 * (flow - 0.65) / 0.35
    else:
        debt -= dh * 0.05           # 造血与铁储备慢慢补回来
    r["blood_debt"] = round(max(0.0, min(1.4, debt)), 3)

    # 功能性无排卵：压力、低体重、过度运动。这三条合起来就是真实世界里
    # 年轻女性继发性闭经最常见的成因，不做成诊断，只改当月有没有排卵。
    if _reproductive(body) and str(r.get("stage")) == "reproductive":
        life = body.get("life") or {}
        stress = float(life.get("stress", 0.3) or 0.3)
        bmi = float((body.get("derived") or {}).get("bmi", 22.0) or 22.0)
        drive = 0.0
        drive += max(0.0, stress - 0.65) * 0.9
        drive += max(0.0, 18.5 - bmi) * 0.10
        drive += max(0.0, float(life.get("activity", 1.0) or 1.0) - 2.4) * 0.10
        if dh > 0 and rng.random() < min(0.5, drive) * dh / 28.0 * 6.0:
            r["anovulatory"] = True
        # 换周期时清掉
        if float(r.get("cycle_day", 1.0) or 1.0) < 1.5:
            r["anovulatory"] = False


# ----------------------------------------------------------------------
# 落到指标与症状
# ----------------------------------------------------------------------
def modulate(body: Dict[str, Any], labs: Dict[str, float],
             vitals: Dict[str, float], derived: Dict[str, Any]) -> None:
    if not _is_female(body):
        return
    r = _r(body)

    # 长期失血债：这才是缺铁性贫血慢慢成立的地方
    debt = float(r.get("blood_debt", 0.0) or 0.0)
    if debt > 0.10 and "HGB" in labs:
        labs["HGB"] = max(70.0, float(labs["HGB"]) - 9.0 * min(1.0, debt))
        if "MCV" in labs and debt > 0.45:
            labs["MCV"] = max(60.0, float(labs["MCV"]) - 6.0 * min(1.0, debt))
    if debt > 0.25:
        derived["iron_debt"] = round(debt, 2)

    # 经前水肿：体重能涨一到两公斤，这不是胖了
    p = pms(body)
    if p["edema"] > 0.15:
        derived["pms_edema_kg"] = round(1.3 * p["edema"], 2)
    if p["level"] > 0.20:
        derived["pms"] = round(p["level"], 2)


def symptoms(body: Dict[str, Any]) -> List[Tuple[str, float]]:
    out: List[Tuple[str, float]] = []
    if not _is_female(body):
        return out
    r = _r(body)

    # --- 经期 ---
    dys = float(r.get("dysmenorrhea", 0.0) or 0.0)
    flow = float(r.get("flow", 0.0) or 0.0)
    if dys > 0.20:
        out.append(("下腹坠痛、腰酸", min(1.0, dys)))
    if flow > 0.30:
        # 经期腹泻由前列腺素引起，和痛经同源，所以两者常常一起来
        out.append(("经期腹泻", min(0.8, 0.55 * flow)))
    if dys > 0.45:
        out.append(("恶心", min(0.7, 0.5 * dys)))
        out.append(("乏力、活动减少", min(0.8, 0.6 * dys)))

    # --- 排卵 ---
    ov = ovulation_signs(body)
    if ov["mittelschmerz"] > 0.30:
        out.append(("小腹一侧抽着疼", min(0.7, ov["mittelschmerz"])))
    # --- 经前 ---
    p = pms(body)
    if p["breast"] > 0.25:
        out.append(("乳房胀痛", min(0.9, p["breast"])))
    if p["bloat"] > 0.25:
        out.append(("腹胀、身体发沉", min(0.8, p["bloat"])))
    if p["head"] > 0.30:
        out.append(("经前头痛", min(0.7, p["head"])))
    if p["acne"] > 0.25:
        out.append(("面部痤疮", min(0.6, p["acne"])))
    if p["mood"] > 0.30:
        out.append(("情绪不稳、易烦躁", min(0.9, p["mood"])))
    if p["appetite"] > 0.35:
        out.append(("食欲增加、偏好甜食", min(0.7, p["appetite"])))

    return out


def line(body: Dict[str, Any]) -> str:
    """注入块用的一句。没有就越过。"""
    if not _is_female(body):
        return ""
    r = _r(body)
    if r.get("pregnant"):
        return ""
    p = pms(body)
    # 只在「有感觉但还没到症状阈值」这一段说话。越过去之后症状表里已经
    # 有乳房胀痛、腹胀、情绪不稳，这里再说一遍就是重复。
    if 0.28 <= p["level"] < 0.45:
        return "这两天身上有点发胀"
    return ""
