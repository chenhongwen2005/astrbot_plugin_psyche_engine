"""精力预算：把「累」算成一个数。

为什么需要它
    「累」是角色扮演里最常被滥用的词。没有实体支撑时，模型只能凭语气；
    有了一个可算的精力值，「今天确实累」和「其实不累但想敷衍」才分得开。
    dysfunction 那个量是**失能**（器官坏了多少），不是**精力**：健康人
    失能为 0，但熬夜一夜之后精力确实掉一半，这两件事不能共用一个数。

输入输出
    进：睡眠时长 / 质量 / 债务、昼夜相位、炎症、贫血、甲状腺、脱水、
        疼痛、血糖、体力活动、环境温度与光照。
    出：energy（此刻还剩多少精力 0~1）、fatigue（主观疲劳）、
        alertness（警觉度）、以及一句能直接进注入段的话。

昼夜曲线
    10 点前后一个峰，14~15 点谷（午后困），21 点后快速下滑。这不是
    文学描写：体温、皮质醇、核心警觉都在这几个点上转向，午后低谷是
    真实存在的，所以能量低谷不该只在「熬夜之后」出现。

光照与维生素 D
    日照时长按纬度与年内日算。冬季日照短、户外少，维生素 D 掉下来，
    这条通路同时连着情绪（见 psyche/dynamics 的 5-HT 项）——季节性情
    绪低落不是「心情不好」，是有生理入口的。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

DAY = 24.0


# ----------------------------------------------------------------------
# 光照
# ----------------------------------------------------------------------
def daylight_hours(day_of_year: float, latitude: float = 30.0) -> float:
    """当天白昼小时数。纬度取 30°（成都/重庆一带）。"""
    doy = max(1.0, min(366.0, float(day_of_year or 180.0)))
    decl = math.radians(23.44 * math.sin(2 * math.pi * (doy - 81.0) / 365.0))
    lat = math.radians(max(-66.0, min(66.0, float(latitude))))
    cos_h = -math.tan(lat) * math.tan(decl)
    cos_h = max(-1.0, min(1.0, cos_h))
    return 24.0 * math.acos(cos_h) / math.pi


# ----------------------------------------------------------------------
# 昼夜警觉
# ----------------------------------------------------------------------
def circadian_alertness(hour: float, chronotype: float = 0.0) -> float:
    """0~1 的昼间警觉度。chronotype >0 是夜猫子，<0 是早鸟。

    用查表加线性插值，不用余弦。余弦只给一个峰一个谷，而人的警觉是两个峰
    两个谷：上午 10 点最高，午后 14 点明显塌一段，傍晚 17~18 点有个次峰，
    凌晨 2~4 点最低（核心体温也在那时最低）。用余弦拼这个形状要比直接
    写点更绕，而且拼出来往往是「凌晨 2 点比晚上 8 点清醒」这种反直觉结果。

    chronotype 是整体平移：夜猫子的整条曲线往后挪，不是把峰抬高。
    """
    h = (float(hour) - 1.6 * float(chronotype or 0.0)) % 24.0
    pts = ((0.0, 0.12), (2.0, 0.09), (4.0, 0.08), (5.5, 0.20), (7.0, 0.55),
           (9.0, 0.82), (10.5, 0.95), (12.0, 0.86), (14.0, 0.60), (15.5, 0.70),
           (17.5, 0.78), (19.0, 0.66), (21.0, 0.44), (22.5, 0.26), (24.0, 0.12))
    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        if x0 <= h <= x1:
            t = (h - x0) / (x1 - x0)
            return max(0.05, min(1.0, y0 + (y1 - y0) * t))
    return 0.12


# ----------------------------------------------------------------------
# 主计算
# ----------------------------------------------------------------------
def compute(body: Dict[str, Any], labs: Dict[str, float],
            vitals: Dict[str, float], derived: Dict[str, Any]) -> Dict[str, Any]:
    life = body.get("life") or {}
    clock = float(body.get("clock", 0.0) or 0.0)
    hour = clock % 24.0
    try:
        from . import traits as _TR
        chrono = _TR.chronotype(body)
        need_h = _TR.sleep_need(body)
    except Exception:
        chrono = float(body.get("chronotype", 0.0) or 0.0)
        need_h = 7.5

    # 负荷累加器必须先建好。之前它建在「宿醉」那段的下面，宿醉的
    # load += 0.06 抛的是 UnboundLocalError，被 except 吞掉——宿醉
    # 只在扣精力那一侧生效，在负荷那一侧从来没生效过。
    load = 0.0
    notes: List[Tuple[str, float]] = []

    sleep_h = float(life.get("sleep_h", 7.5) or 7.5)
    qual = max(0.1, min(1.0, float(life.get("sleep_qual", 0.8) or 0.8)))
    debt = max(0.0, float(life.get("sleep_debt", 0.0) or 0.0))

    alert = circadian_alertness(hour, chrono)
    # 睡眠恢复力按**这个人的需求**算：短睡者睡 7 小时是够的，长睡者
    # 睡 7 小时等于欠了一小时。统一除以 7.5 会让长睡者永远差一口气。
    rest = max(0.15, min(1.0, sleep_h / max(4.0, need_h))) * (0.55 + 0.45 * qual)
    debt_pen = min(0.40, debt / 45.0)

    # 宿醉是真实存在的负荷：它不是"还醉着"，而是血酒精归零之后的
    # 那几个小时——头痛、口渴、注意力抓不住，什么都做不动。
    # 情绪的内耗。烦躁不只是心里的事，它真的占掉一部分可用精力。
    try:
        from . import mind as _MD
        mv = _MD.load(body)
        if abs(mv) > 0.005:
            load += mv
    except Exception:
        pass

    try:
        from . import substance as _SUB
        hang = _SUB.hangover(body)
        if hang > 0.5:
            debt_pen = min(0.55, debt_pen + 0.10)
            load += 0.06
            notes.append(("昨夜喝多了，今天整个人发钝", 0.06))
    except Exception:
        pass

    crp = float(labs.get("CRP", 3.0) or 3.0)
    if crp > 10.0:
        v = min(0.16, (crp - 10.0) / 120.0)
        load += v
        notes.append(("身上在打仗", v))

    hgb = float(labs.get("HGB", 140.0 if body.get("sex") == "m" else 125.0) or 130.0)
    ref = 140.0 if str(body.get("sex", "m")) == "m" else 125.0
    if hgb < ref * 0.95:
        v = min(0.18, (ref - hgb) / ref * 1.2)
        load += v
        notes.append(("血不够用", v))

    ft3 = labs.get("FT3")
    if isinstance(ft3, (int, float)) and ft3 < 3.1:
        v = min(0.14, (3.1 - float(ft3)) * 0.12)
        load += v
        notes.append(("代谢压低", v))

    water = float(life.get("water", 0.85) or 0.85)
    if water < 0.7:
        v = min(0.12, (0.7 - water) * 0.5)
        load += v
        notes.append(("缺水", v))

    pain = float(vitals.get("PAIN", 0.0) or 0.0)
    if pain > 2.0:
        v = min(0.15, (pain - 2.0) * 0.025)
        load += v
        notes.append(("疼得耗神", v))

    glu = labs.get("GLU")
    if isinstance(glu, (int, float)) and float(glu) < 4.0:
        v = min(0.10, (4.0 - float(glu)) * 0.12)
        load += v
        notes.append(("血糖低", v))

    # 疾病活动度：发热本身就是大额消耗
    fever = max(0.0, float(derived.get("fever_drive", 0.0) or 0.0))
    if fever > 0.1:
        v = min(0.22, fever * 0.6)
        load += v
        notes.append(("在发烧", v))

    # 体力活动：一天里做过重活，下午之后余额就低
    act = float(life.get("activity", 1.0) or 1.0)
    if act > 1.6:
        v = min(0.12, (act - 1.6) * 0.08)
        load += v
        notes.append(("体力活做多了", v))

    # 恢复力要随「已清醒多久」衰减。只按当天睡了多久算的话，凌晨两点
    # 的精力会和早上八点一样高——那不是人，那是一块刚充满的电池。
    hour = clock % 24.0
    awake = hour - 7.0 if hour >= 7.0 else hour + 17.0
    rest_eff = rest * max(0.12, 1.0 - awake / 18.0)

    load = min(0.85, load)
    level = 0.40 * alert + 0.42 * rest_eff + 0.28 * (1.0 - load) - debt_pen
    level = max(0.02, min(1.0, level))

    # 主观疲劳不等同于精力低：焦虑的人精力不低但主观很累，这里只做近似
    fatigue = max(0.0, min(1.0, 1.0 - level * 0.9 + debt_pen * 0.5))

    out = {
        "level": round(level, 3),
        "fatigue": round(fatigue, 3),
        "alertness": round(alert, 3),
        "sleep_debt_h": round(debt, 1),
        "load": round(load, 3),
        "notes": [n for n, v in notes if v >= 0.02][:4],
        "note": _note(level, fatigue, debt, alert),
    }
    return out


def _note(level: float, fatigue: float, debt: float, alert: float) -> str:
    if level >= 0.72:
        base = "精力还够用"
    elif level >= 0.52:
        base = "有点乏，但撑得住"
    elif level >= 0.34:
        base = "注意力得主动拽回来"
    elif level >= 0.18:
        base = "撑着一口气，想找地方坐下"
    else:
        base = "几乎抬不起手"
    if alert < 0.2:
        base += "，这个点本来就困"
    if debt > 12:
        base += f"，欠着 {int(debt)} 小时睡眠"
    return base


# ----------------------------------------------------------------------
# 环境：光照、维生素 D、冷热应激
# ----------------------------------------------------------------------
def environment(body: Dict[str, Any], hours: float,
                day_of_year: float) -> Dict[str, Any]:
    """推进维生素 D 与冷热应激。返回这一轮的环境事件。"""
    life = body.get("life") or {}
    env = body.get("env") or {}
    events: List[str] = []
    dh = max(0.0, float(hours)) / DAY

    daylight = daylight_hours(day_of_year)
    env["daylight_h"] = round(daylight, 2)

    # 户外时间：活动量大的人晒得多，久坐的人几乎不晒
    act = float(life.get("activity", 1.0) or 1.0)
    sedentary = float(life.get("sedentary", 6.0) or 6.0)
    outdoor = max(0.0, min(1.0, 0.10 + 0.16 * act - 0.035 * max(0.0, sedentary - 6.0)))

    vitd = float(life.get("vitd", 0.6) or 0.6)
    # 合成靠 UVB，与日照时长和户外时间成正比；消耗恒定
    synth = 0.02 * (max(0.0, daylight - 8.0) / 6.0) * outdoor * min(1.0, dh * 4.0 + 0.2)
    vitd = max(0.05, min(1.0, vitd + synth - 0.004 * dh))
    life["vitd"] = vitd
    if vitd < 0.3 and dh > 0:
        events.append("low_vitd")

    temp = float(env.get("temp_c", 22.0) or 22.0)
    hum = float(env.get("humidity", 55.0) or 55.0)

    # 热：温度与湿度一起算，湿热比干热更压人
    heat = temp + 0.22 * max(0.0, hum - 50.0)
    if heat >= 34.0:
        water = float(life.get("water", 0.85) or 0.85)
        life["water"] = max(0.15, water - 0.010 * (heat - 33.0) * min(2.0, dh * 2 + 0.3))
        if heat >= 38.0:
            events.append("heat_stress")
    elif temp <= 4.0:
        events.append("cold_stress")

    return {"events": events, "daylight_h": daylight, "outdoor": round(outdoor, 2),
            "vitd": round(vitd, 3)}


def summary(body: Dict[str, Any]) -> str:
    """一行话，进注入段。"""
    e = body.get("energy") or {}
    if not e:
        return ""
    parts = [str(e.get("note") or "")]
    notes = e.get("notes") or []
    if notes:
        parts.append("、" .join(notes[:3]))
    return "，".join(p for p in parts if p)


def symptoms(body: Dict[str, Any]) -> List[Tuple[str, float]]:
    # 睡着的人不会觉得「浑身没劲」。那句话是醒着的人说的，人在梦里
    # 不评价自己的精力。
    st = body.get("sleep")
    if isinstance(st, dict) and st.get("sleeping"):
        return []
    out: List[Tuple[str, float]] = []
    e = body.get("energy") or {}
    if not e:
        return out
    if float(e.get("level", 1.0)) < 0.34:
        out.append(("浑身没劲、提不起精神", min(1.0, 1.0 - float(e.get("level", 1.0)))))
    life = body.get("life") or {}
    if float(life.get("vitd", 0.6) or 0.6) < 0.28:
        out.append(("骨头酸、容易累", 0.5))
    return out
