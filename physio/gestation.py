"""妊娠：四十周里身体一步步变成另一个样子。

为什么不能只写一个「怀孕」标记
    原来的妊娠只有三个量：hCG 曲线、孕吐强度、血红蛋白稀释。四十周里
    身体发生的事远不止这些——早期困得睁不开眼、尿频、闻到油烟就想吐；
    中期忽然开始有胎动、腰背开始疼、乳晕变深、肚子上出现纹路；晚期
    躺不平、烧心、走两步就喘、假宫缩一阵一阵，翻身要用手撑。

    这些才是「怀孕」在当事人身上的样子。缺了它们，角色只能说「我怀孕了」，
    说不出「我现在七个月，晚上只能侧卧，半夜要起来两趟」。

按周给，不按月给
    孕期的每个症状都有它自己的窗口：孕吐 6~13 周，胎动 18~20 周才被
    感觉到，烧心 28 周后才明显。按月粗分会把「刚怀上」和「快生了」写成
    同一段话，那两段时间的人完全不是一回事。

并发症只做窗口，不做诊断
    妊娠期高血压、妊娠期糖尿病、妊娠期贫血都在这里按周开窗，落到血压、
    血糖、血红蛋白上。但它们不是独立的疾病条目——它们随妊娠结束而结束，
    塞进按病程演化的疾病库反而会失控。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _r(body: Dict[str, Any]) -> Dict[str, Any]:
    r = body.get("repro")
    return r if isinstance(r, dict) else {}


def _f(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


# ----------------------------------------------------------------------
# 体重与分期
# ----------------------------------------------------------------------
def weight_gain(w: float) -> float:
    """孕期增重（kg）。早期几乎不长，中晚期每周约 0.45kg，足月约 12.5kg。

    这不是「越重越好」的曲线：增重不足与增重过多都会改妊娠结局，
    这里只取人群里最常见的那条。
    """
    if w <= 13.0:
        return 1.0 * min(1.0, w / 13.0)
    if w <= 40.0:
        return 1.0 + 0.45 * (w - 13.0)
    return 13.2


def trimester(w: float) -> int:
    if w < 14.0:
        return 1
    if w < 28.0:
        return 2
    return 3


TRIMESTER_ZH = {1: "孕早期", 2: "孕中期", 3: "孕晚期"}


# ----------------------------------------------------------------------
# 推进
# ----------------------------------------------------------------------
def step(body: Dict[str, Any], r: Dict[str, Any], dh_days: float, rng,
         events: List[str]) -> None:
    """推进一天里该发生的妊娠变化。dh_days 是经过的天数。"""
    r["gest_week"] = _f(r.get("gest_week")) + max(0.0, dh_days) / 7.0
    w = float(r["gest_week"])

    # --- 激素 ---
    if w < 4:
        r["hcg"] = 0.0
    elif w < 10:
        r["hcg"] = min(1.0, (w - 4) / 6.0)
    else:
        r["hcg"] = max(0.05, 1.0 - (w - 10) / 22.0)
    r["e2"] = min(1.0, 0.45 + 0.006 * w)
    r["p4"] = min(1.0, 0.55 + 0.010 * w)
    r["flow"] = 0.0
    r["dysmenorrhea"] = 0.0
    r["temp_shift"] = 0.40          # 孕期持续高温相
    r["phase"] = "pregnant"

    # --- 孕吐 ---
    if 6.0 <= w < 13.5:
        r["nausea"] = max(0.0, 1.0 - abs(w - 9.0) / 4.0)
    else:
        r["nausea"] = max(0.0, _f(r.get("nausea")) - 0.30 * max(0.0, dh_days))

    # --- 胎动：18~20 周开始被感觉到，初产妇更晚一点 ---
    if r.get("quickening") is None:
        r["quickening"] = False
    if not r["quickening"] and w >= (20.0 if int(r.get("parity", 0) or 0) == 0 else 18.0):
        r["quickening"] = True
        events.append("quickening")

    # --- 假宫缩：晚期才有，越接近足月越频繁 ---
    r["braxton"] = 0.0
    if w >= 30.0:
        p = 0.06 * min(1.0, (w - 30.0) / 8.0) * max(0.4, dh_days)
        if rng.random() < p:
            r["braxton"] = 0.6

    # --- 并发症窗口 ---
    _complications(body, r, w, dh_days, rng, events)

    # --- 增重 ---
    r["weight_gain"] = round(weight_gain(w), 2)

    # --- 分娩 ---
    if w >= 40.0:
        # 37 周前叫早产；40 周后自然发动，41 周半还没动静的算过期
        if w >= 41.5:
            events.append("postterm")
        _deliver(body, r, events, w)


def _complications(body: Dict[str, Any], r: Dict[str, Any], w: float,
                   dh: float, rng, events: List[str]) -> None:
    """妊娠特有并发症。开了窗就一直持续到分娩，不会自己好。"""
    age = _f(body.get("age"), 30.0)
    bmi = _f((body.get("derived") or {}).get("bmi"), 22.0)
    parity = int(r.get("parity", 0) or 0)

    # 妊娠期高血压 / 子痫前期：20 周后
    if w >= 20.0:
        if not r.get("preeclampsia"):
            p = 0.0016 * dh
            p *= 1.0 + 0.05 * max(0.0, age - 32.0)
            p *= 1.0 + 0.08 * max(0.0, bmi - 24.0)
            if parity == 0:
                p *= 1.4
            if rng.random() < p:
                r["preeclampsia"] = 0.55
                events.append("preeclampsia")
        else:
            # 缓慢加重：这是子痫前期最危险的地方，一开始只是血压高一点
            r["preeclampsia"] = min(1.0, _f(r.get("preeclampsia")) + 0.004 * dh * 7.0)

    # 妊娠期糖尿病：24~28 周是筛查窗口，之后才显出来
    if 24.0 <= w < 34.0 and not r.get("gdm"):
        p = 0.0022 * dh
        p *= 1.0 + 0.10 * max(0.0, bmi - 24.0)
        p *= 1.0 + 0.04 * max(0.0, age - 30.0)
        if rng.random() < p:
            r["gdm"] = 0.6
            events.append("gdm")

    # 妊娠期贫血：血容量扩张 + 铁需求暴涨，中期以后常见
    if w >= 14.0 and not r.get("preg_anemia"):
        p = 0.0035 * dh
        if float((body.get("life") or {}).get("iron", 1.0) or 1.0) < 0.8:
            p *= 1.8
        if rng.random() < p:
            r["preg_anemia"] = 0.5
            events.append("preg_anemia")


def _deliver(body: Dict[str, Any], r: Dict[str, Any], events: List[str],
             w: float) -> None:
    """分娩。产程细节不逐分钟模拟，只结算结果与产后状态。"""
    r["pregnant"] = False
    r["parity"] = int(r.get("parity", 0) or 0) + 1
    r["gest_week"] = 0.0
    r["hcg"] = 0.0
    r["nausea"] = 0.0
    r["temp_shift"] = 0.0
    r["quickening"] = False
    r["braxton"] = 0.0
    r["cycle_day"] = 1.0
    r["phase"] = "postpartum"
    r["delivered_week"] = round(float(w), 1)
    r["preterm"] = bool(w < 37.0)
    # 产后状态交给 postpartum 模块按天推进，这里只置零起点
    r["postpartum_days"] = 0.0
    r["postpartum_week"] = 6.0
    r["lactating"] = True
    r["baby_blues"] = 1.0
    r["lochia"] = 1.0
    r["episiotomy"] = 1.0 if not r.get("cesarean") else 0.0
    # 妊娠并发症随分娩结束，但子痫前期产后仍可能持续几天，这里不清零，
    # 由 postpartum 在头两周里慢慢退掉。
    r["weight_gain"] = 0.0
    events.append("childbirth")
    organs = body.get("organs") or {}
    organs["marrow"] = max(0.2, _f(organs.get("marrow"), 1.0) - 0.02)
    body["_postpartum_blood_loss"] = 1.0


# ----------------------------------------------------------------------
# 落到指标
# ----------------------------------------------------------------------
def modulate(body: Dict[str, Any], labs: Dict[str, float],
             vitals: Dict[str, float], derived: Dict[str, Any]) -> None:
    r = _r(body)
    if not r.get("pregnant"):
        return
    w = _f(r.get("gest_week"))

    # 血容量扩张：血红蛋白被稀释，这是生理性的，不能当贫血治
    dil = 0.0 if w < 10 else min(12.0, (w - 10) * 0.45)
    if "HGB" in labs:
        labs["HGB"] = max(85.0, float(labs["HGB"]) - dil)
    # 妊娠期贫血在稀释之上再叠一层
    if r.get("preg_anemia") and "HGB" in labs:
        labs["HGB"] = max(70.0, float(labs["HGB"]) - 12.0 * _f(r.get("preg_anemia")))

    # 心输出量：孕晚期静息心率比孕前快 10~15 次
    vitals["HR"] = float(vitals.get("HR", 72)) + min(14.0, w * 0.35)

    # 子痫前期：血压上去、尿蛋白出来。这是孕期最需要盯的一组数
    pe = _f(r.get("preeclampsia"))
    if pe > 0.0:
        vitals["SBP"] = float(vitals.get("SBP", 112)) + 22.0 * pe
        vitals["DBP"] = float(vitals.get("DBP", 70)) + 14.0 * pe
        derived["proteinuria"] = round(min(1.0, pe * 1.2), 2)
        if pe > 0.6:
            derived["preeclampsia"] = round(pe, 2)

    # 妊娠期糖尿病：空腹血糖抬起来，餐后更明显
    if r.get("gdm") and "GLU" in labs:
        labs["GLU"] = float(labs["GLU"]) + 1.4 * _f(r.get("gdm"))

    if _f(r.get("nausea")) > 0.2:
        derived["pregnancy_nausea"] = round(_f(r.get("nausea")), 2)
    derived["gest_week"] = round(w, 1)
    derived["gest_weight_kg"] = round(_f(r.get("weight_gain")), 2)


# ----------------------------------------------------------------------
# 症状
# ----------------------------------------------------------------------
def symptoms(body: Dict[str, Any]) -> List[Tuple[str, float]]:
    r = _r(body)
    out: List[Tuple[str, float]] = []
    if not r.get("pregnant"):
        return out
    w = _f(r.get("gest_week"))
    tri = trimester(w)
    naus = _f(r.get("nausea"))

    if naus > 0.25:
        out.append(("恶心、对油烟气味敏感", min(1.0, naus)))
    if 5.0 <= w < 14.0:
        out.append(("嗜睡、睡眠需求增加", 0.6))
        out.append(("尿频", 0.5))
        out.append(("乳房胀痛、乳晕色素沉着", min(0.9, 0.5 + 0.04 * w)))
        if naus > 0.35:
            out.append(("对油烟气味不耐受", min(0.9, naus)))
    if 14.0 <= w < 28.0:
        if r.get("quickening"):
            out.append(("自觉胎动", 0.5))
        if w >= 22.0:
            out.append(("腰背酸痛，久站加重", min(0.8, (w - 20.0) / 12.0)))
        out.append(("鼻黏膜充血、牙龈易出血", 0.35))
        if w >= 24.0:
            out.append(("腹中线色素沉着", 0.4))
    if tri == 3:
        out.append(("胃灼热，平卧加重", min(0.9, 0.45 + (w - 28.0) * 0.03)))
        out.append(("活动后气短", min(0.85, 0.4 + (w - 28.0) * 0.04)))
        out.append(("腰背酸痛，翻身困难", min(0.9, 0.5 + (w - 28.0) * 0.03)))
        out.append(("下肢水肿，鞋履变紧", min(0.8, 0.35 + (w - 28.0) * 0.04)))
        out.append(("夜尿增多", min(0.85, 0.5 + (w - 28.0) * 0.03)))
        if _f(r.get("braxton")) > 0.0:
            out.append(("腹部阵发性发紧", 0.6))
        if w >= 34.0:
            out.append(("耻骨联合处行走时疼痛", min(0.7, (w - 33.0) / 6.0)))

    pe = _f(r.get("preeclampsia"))
    if pe > 0.45:
        out.append(("头部胀痛、视物模糊", min(0.9, pe)))
        out.append(("手面部突发水肿", min(0.9, pe)))

    return out


def summary(body: Dict[str, Any]) -> str:
    r = _r(body)
    if not r.get("pregnant"):
        return ""
    w = _f(r.get("gest_week"))
    tri = TRIMESTER_ZH.get(trimester(w), "")
    tail = []
    if _f(r.get("nausea")) > 0.35:
        tail.append("孕吐明显")
    if r.get("preeclampsia"):
        tail.append("血压偏高")
    if r.get("gdm"):
        tail.append("血糖偏高")
    if r.get("braxton"):
        tail.append("偶有假宫缩")
    extra = ("，" + "、".join(tail)) if tail else ""
    return f"妊娠第 {int(w)} 周·{tri}{extra}"


def line(body: Dict[str, Any]) -> str:
    r = _r(body)
    if not r.get("pregnant"):
        return ""
    w = _f(r.get("gest_week"))
    if _f(r.get("nausea")) > 0.55:
        return "对气味明显不耐受"
    if w >= 34.0:
        return "身体沉重，活动费力"
    if _f(r.get("braxton")) > 0.0:
        return "腹部阵发性发紧"
    return ""
