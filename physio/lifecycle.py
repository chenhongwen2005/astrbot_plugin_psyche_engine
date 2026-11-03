"""生殖与生命周期：月经周期、妊娠、产后、围绝经、男性性腺轴。

为什么单独一层
    疾病库里有围绝经期综合征、多囊、子宫内膜异位症，但没有「正常的月经
    周期」——因为疾病库只装异常。而一个女性角色有一半时间处在某个周期
    相位里，这个相位每时每刻都在改她的基础体温、食欲、痛阈、血红蛋白和
    情绪底色。缺了它，角色在生理上永远是「一个没有周期的人」：不会在
    经期腹痛，不会在黄体期烦躁，也不会在孕早期恶心。

设计原则
    1. 周期是**连续函数**，不是查表。任意周期日都能算出激素水平，所以
       虚拟时钟一次推进 6 小时还是 6 分钟，结果都对得上。
    2. 只做生理，不做决定。「是否怀孕」是一个显式状态，不会自己发生；
       推进到 40 周才分娩。这类事不该由随机数替用户决定。
    3. 效应落在已有通路上：基础体温进 TEMP、痛经进 PAIN、血液稀释进 HGB、
       孕晚期心输出量进 HR。不新开一套与化验单平行的数据。

女性一生：
    初潮（约 12.5 岁）→ 育龄期（周期 28 天，21~35 都算正常）
    → 围绝经（45~55 岁，周期先乱后停）→ 绝经后（雌激素低位，骨量加速流失）
    中间可以有妊娠（40 周）与产后（6 周恢复，哺乳可继续）
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple

DAY = 24.0


# ----------------------------------------------------------------------
# 初始状态
# ----------------------------------------------------------------------
def _stage_for(sex: str, age: float, menarche: float, menopause: float) -> str:
    if sex != "f":
        return "adult"
    if age < menarche:
        return "prepuberty"
    if age < menopause:
        return "reproductive"
    if age < menopause + 5.0:
        return "perimenopause"
    return "postmenopause"


def new_state(body: Dict[str, Any]) -> Dict[str, Any]:
    sex = str(body.get("sex", "m") or "m")
    age = float(body.get("age", 30.0) or 30.0)
    seed = int(body.get("seed", 20261030) or 20261030)
    rng = random.Random(seed ^ 0x52455052)
    menarche = round(12.0 + rng.uniform(0.0, 2.5), 1)
    menopause = round(48.5 + rng.uniform(0.0, 6.0), 1)
    # 周期长度个体差异很大，21~35 天都算正常。默认给一个 28±3 的
    cycle_len = 28 + rng.choice([-3, -2, -1, 0, 0, 1, 2, 3])
    stage = _stage_for(sex, age, menarche, menopause)
    day = rng.uniform(1.0, float(cycle_len)) if stage in ("reproductive", "perimenopause") else 0.0
    return {
        "v": 1,
        "sex": sex,
        "stage": stage,
        "menarche_age": menarche,
        "menopause_age": menopause,
        "cycle_len": cycle_len,
        "cycle_day": round(day, 2),
        "phase": "",
        "e2": 0.30,        # 雌激素（相对水平 0~1）
        "p4": 0.05,        # 孕激素
        "lh": 0.15,
        "fsh": 0.25,
        "t": 0.60,         # 睾酮
        "hcg": 0.0,
        "pregnant": False,
        "gest_week": 0.0,
        "parity": 0,
        "postpartum_week": 0.0,
        "lactating": False,
        "hot_flash": 0.0,
        "flow": 0.0,         # 经量 0~1
        "dysmenorrhea": 0.0,  # 痛经强度 0~1
        "temp_shift": 0.0,    # 基础体温偏移（℃）
        "events": [],
    }


def ensure(body: Dict[str, Any]) -> Dict[str, Any]:
    r = body.get("repro")
    if not isinstance(r, dict) or not r:
        r = new_state(body)
        body["repro"] = r
    else:
        base = new_state(body)
        for k, v in base.items():
            r.setdefault(k, v)
        body["repro"] = r
    # 相位要在这里算一次：hours=0 的 step（首次初始化、只读查询）不会走
    # _advance_hour，phase 会一直是空串，摘要那行就成了「月经周期第 5 天·」。
    if not r.get("pregnant") and r.get("stage") in ("reproductive", "perimenopause"):
        L = float(r.get("cycle_len", 28) or 28)
        d = float(r.get("cycle_day", 1.0) or 1.0)
        e2, p4, lh, fsh = _hormones(d, L)
        r["e2"], r["p4"], r["lh"], r["fsh"] = e2, p4, lh, fsh
        r["phase"] = _phase_name(d, L)
        if r["phase"] == "menstrual":
            r["flow"] = max(0.0, 1.0 - (d - 1.0) / 5.0)
            r["dysmenorrhea"] = max(0.0, 1.0 - (d - 1.0) / 3.0)
        r["temp_shift"] = round(0.32 * (p4 / 0.75) if p4 > 0.2 else 0.0, 3)
    return r


# ----------------------------------------------------------------------
# 激素曲线
# ----------------------------------------------------------------------
def _hormones(d: float, L: float) -> Tuple[float, float, float, float]:
    """返回 (雌二醇, 孕酮, LH, FSH)，均为 0~1 相对水平。

    取连续式而不是 28 天查表：周期长度因人而异（21~35），查表就得为每个
    长度重写一遍；而且虚拟时钟一次可能推进 6 小时，落在两天之间时插值
    比取整更接近真实。
    """
    L = max(21.0, min(40.0, float(L)))
    ov = max(10.0, L - 14.0)          # 黄体期固定约 14 天，所以排卵日在 L-14
    d = ((float(d) - 1.0) % L) + 1.0

    if d <= 5.0:                       # 月经期：两者都低
        e2 = 0.14 + 0.04 * (d / 5.0)
        p4 = 0.05
        lh = 0.12
        fsh = 0.35
    elif d < ov:                       # 卵泡期：雌激素爬升
        x = (d - 5.0) / max(1.0, ov - 5.0)
        e2 = 0.18 + 0.62 * (x ** 1.5)
        p4 = 0.05 + 0.05 * x
        lh = 0.12 + 0.12 * x
        fsh = 0.35 - 0.10 * x
    elif d < ov + 1.5:                 # 排卵峰
        e2 = 0.80
        p4 = 0.10
        lh = 0.95
        fsh = 0.45
    else:                              # 黄体期：孕酮主导，末期双双回落
        x = (d - ov - 1.5) / max(1.0, L - ov - 1.5)
        p4 = 0.12 + 0.62 * math.sin(math.pi * min(1.0, x * 1.05))
        e2 = 0.72 - 0.28 * x
        lh = 0.15
        fsh = 0.25
    return (max(0.0, min(1.0, e2)), max(0.0, min(1.0, p4)),
            max(0.0, min(1.0, lh)), max(0.0, min(1.0, fsh)))


def _phase_name(d: float, L: float) -> str:
    ov = max(10.0, L - 14.0)
    d = ((float(d) - 1.0) % L) + 1.0
    if d <= 5.0:
        return "menstrual"
    if d < ov:
        return "follicular"
    if d < ov + 1.5:
        return "ovulation"
    return "luteal"


PHASE_ZH = {
    "menstrual": "月经期",
    "follicular": "卵泡期",
    "ovulation": "排卵期",
    "luteal": "黄体期",
    "pregnant": "妊娠期",
    "postpartum": "产后期",
    "perimenopause": "围绝经期",
    "postmenopause": "绝经后",
    "prepuberty": "青春期前",
    "adult": "成年",
}


# ----------------------------------------------------------------------
# 推进
# ----------------------------------------------------------------------
def step(body: Dict[str, Any], hours: float, rng: random.Random,
         events: Optional[List[str]] = None) -> None:
    """按经过小时推进。周期以天为粒度，所以只在跨日时重算激素。"""
    r = ensure(body)
    events = events if events is not None else []
    dh = max(0.0, float(hours)) / DAY
    age = float(body.get("age", 30.0) or 30.0)

    # 年龄会在长程里推着 stage 走
    new_stage = _stage_for(str(r.get("sex", "m")), age,
                           float(r["menarche_age"]), float(r["menopause_age"]))
    if new_stage != r.get("stage"):
        old = r.get("stage")
        r["stage"] = new_stage
        if new_stage == "reproductive" and old == "prepuberty":
            events.append("menarche")
            r["cycle_day"] = 1.0
        if new_stage in ("perimenopause", "postmenopause") and old not in (
                "perimenopause", "postmenopause"):
            events.append("menopause")
            r["pregnant"] = False

    if r.get("pregnant"):
        _step_pregnancy(body, r, dh, events)
        return

    if float(r.get("postpartum_week", 0.0)) > 0.0:
        r["postpartum_week"] = max(0.0, float(r["postpartum_week"]) + dh / 7.0)
        if r["postpartum_week"] <= 0.0:
            r["lactating"] = False

    if r.get("sex") != "f":
        _step_male(body, r, dh)
        return

    stage = r.get("stage")
    if stage in ("prepuberty", "postmenopause"):
        r["e2"] = 0.10 if stage == "postmenopause" else 0.06
        r["p4"] = 0.04
        r["lh"] = 0.30 if stage == "postmenopause" else 0.10
        r["fsh"] = 0.70 if stage == "postmenopause" else 0.12
        r["flow"] = 0.0
        r["dysmenorrhea"] = 0.0
        r["temp_shift"] = 0.0
        r["phase"] = stage
        _step_bone_loss(body, r, dh)
        return

    # 围绝经期：周期先变短再变长、有些不排卵，这是它最典型的特征
    if stage == "perimenopause":
        if rng.random() < 0.004 * max(1.0, dh):
            r["cycle_len"] = max(21, min(45, int(r["cycle_len"]) + rng.choice([-2, -1, 1, 2])))

    r["cycle_day"] = float(r.get("cycle_day", 1.0)) + dh
    L = float(r.get("cycle_len", 28))
    if r["cycle_day"] > L:
        r["cycle_day"] = r["cycle_day"] - L
        if stage == "perimenopause":
            r["cycle_len"] = max(21, min(45, int(L) + rng.choice([-2, -1, 0, 1, 2])))

    d = float(r["cycle_day"])
    e2, p4, lh, fsh = _hormones(d, L)
    if stage == "perimenopause":
        e2 *= 0.75
        lh *= 1.15
        fsh = min(1.0, fsh * 1.25)
    r["e2"], r["p4"], r["lh"], r["fsh"] = e2, p4, lh, fsh
    r["phase"] = _phase_name(d, L)

    # 经期：经量与痛经都在头两天最重
    if r["phase"] == "menstrual":
        r["flow"] = max(0.0, 1.0 - (d - 1.0) / 5.0)
        r["dysmenorrhea"] = max(0.0, 1.0 - (d - 1.0) / 3.0)
    else:
        r["flow"] = max(0.0, float(r.get("flow", 0.0)) - 0.4 * dh)
        r["dysmenorrhea"] = max(0.0, float(r.get("dysmenorrhea", 0.0)) - 0.5 * dh)

    # 基础体温：排卵后孕酮把体温抬高 0.3℃ 左右，这是唯一能被自己量到的相位信号
    r["temp_shift"] = round(0.32 * (p4 / 0.75) if p4 > 0.2 else 0.0, 3)

    # 围绝经潮热：雌激素撤退导致的体温调节不稳，每次持续几分钟到半小时
    if stage == "perimenopause":
        p_flash = 0.10 * max(0.0, 1.0 - e2 / 0.5) * min(1.0, dh * 4.0)
        if rng.random() < p_flash:
            r["hot_flash"] = 1.0
            events.append("hot_flash")
        else:
            r["hot_flash"] = max(0.0, float(r.get("hot_flash", 0.0)) - 1.5 * dh)
    else:
        r["hot_flash"] = max(0.0, float(r.get("hot_flash", 0.0)) - 1.5 * dh)



def _step_male(body: Dict[str, Any], r: Dict[str, Any], dh: float) -> None:
    """男性没有周期，只有昼夜节律与缓慢下降。"""
    h = float(body.get("clock", 0.0) or 0.0) % 24.0
    circ = 0.5 + 0.5 * math.cos(2 * math.pi * (h - 8.0) / 24.0)
    age = float(body.get("age", 30.0) or 30.0)
    decay = max(0.55, 1.0 - 0.006 * max(0.0, age - 30.0))
    r["t"] = max(0.1, min(1.0, (0.62 + 0.30 * circ) * decay))
    r["e2"] = 0.12
    r["p4"] = 0.03
    r["lh"] = 0.25
    r["fsh"] = 0.25
    r["phase"] = "adult"
    r["temp_shift"] = 0.0
    r["flow"] = 0.0
    r["dysmenorrhea"] = 0.0


def _step_pregnancy(body: Dict[str, Any], r: Dict[str, Any], dh: float,
                    events: List[str]) -> None:
    r["gest_week"] = float(r.get("gest_week", 0.0)) + dh / 7.0
    w = r["gest_week"]
    # hCG：5 周起升，8~10 周峰值，之后回落
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
    r["temp_shift"] = 0.4          # 孕期持续高温相
    r["phase"] = "pregnant"
    if 6 <= w < 13:
        r["nausea"] = 1.0 - abs(w - 9.0) / 4.0
    else:
        r["nausea"] = max(0.0, float(r.get("nausea", 0.0)) - 0.3 * dh)
    if w >= 40.0:
        _deliver(body, r, events)


def _deliver(body: Dict[str, Any], r: Dict[str, Any], events: List[str]) -> None:
    """到 40 周就分娩。不做主动终止，也不做并发症随机。"""
    r["pregnant"] = False
    r["parity"] = int(r.get("parity", 0)) + 1
    r["gest_week"] = 0.0
    r["hcg"] = 0.0
    r["postpartum_week"] = 6.0
    r["lactating"] = True
    r["nausea"] = 0.0
    r["temp_shift"] = 0.0
    r["cycle_day"] = 1.0
    r["phase"] = "postpartum"
    r["baby_blues"] = 1.0          # 产后两周内的情绪低落，多数人会有
    events.append("childbirth")
    # 分娩失血：血红蛋白掉一截，靠后续造血慢慢补
    organs = body.get("organs") or {}
    organs["marrow"] = max(0.2, float(organs.get("marrow", 1.0)) - 0.02)
    body["_postpartum_blood_loss"] = 1.0


def _step_bone_loss(body: Dict[str, Any], r: Dict[str, Any], dh: float) -> None:
    """绝经后雌激素撤退，骨量每年掉 2% 左右，比同龄男性快得多。"""
    if r.get("stage") != "postmenopause":
        return
    organs = body.get("organs") or {}
    bone = float(organs.get("bone", 1.0))
    organs["bone"] = max(0.20, bone - 0.0006 * dh / 365.0 * 365.0 * 0.02)


# ----------------------------------------------------------------------
# 对化验与体征的修正
# ----------------------------------------------------------------------
def modulate(body: Dict[str, Any], labs: Dict[str, float],
             vitals: Dict[str, float], derived: Dict[str, Any]) -> None:
    """把周期相位、妊娠、产后落到已有指标上。"""
    r = body.get("repro")
    if not isinstance(r, dict) or not r:
        return

    # 基础体温
    shift = float(r.get("temp_shift", 0.0) or 0.0)
    if shift:
        vitals["TEMP"] = float(vitals.get("TEMP", 36.6)) + shift

    # 痛经：经期头两天是真的疼，不是「有点不舒服」
    dys = float(r.get("dysmenorrhea", 0.0) or 0.0)
    if dys > 0.05:
        vitals["PAIN"] = min(10.0, float(vitals.get("PAIN", 0.0)) + 3.2 * dys)

    # 经期失血：经量大的那几天血红蛋白会掉，长期量大则是缺铁性贫血的入口
    flow = float(r.get("flow", 0.0) or 0.0)
    if flow > 0.05 and "HGB" in labs:
        labs["HGB"] = max(70.0, float(labs["HGB"]) - 4.0 * flow)

    # 妊娠：血容量扩张把血红蛋白稀释下去，这是生理性的，不是贫血
    if r.get("pregnant"):
        w = float(r.get("gest_week", 0.0) or 0.0)
        dil = 0.0 if w < 10 else min(12.0, (w - 10) * 0.45)
        if "HGB" in labs:
            labs["HGB"] = max(85.0, float(labs["HGB"]) - dil)
        vitals["HR"] = float(vitals.get("HR", 72)) + min(14.0, w * 0.35)
        naus = float(r.get("nausea", 0.0) or 0.0)
        if naus > 0.2:
            derived["pregnancy_nausea"] = round(naus, 2)

    # 产后失血与哺乳消耗
    if float(r.get("postpartum_week", 0.0) or 0.0) > 0.0:
        if body.pop("_postpartum_blood_loss", 0):
            if "HGB" in labs:
                labs["HGB"] = max(75.0, float(labs["HGB"]) - 12.0)
        if r.get("lactating") and "HGB" in labs:
            pass


# ----------------------------------------------------------------------
# 摘要
# ----------------------------------------------------------------------
def summary(body: Dict[str, Any]) -> str:
    """一行话，给注入段与体检抬头用。没有周期的人返回空串。"""
    r = body.get("repro")
    if not isinstance(r, dict) or not r:
        return ""
    if r.get("sex") != "f":
        age = float(body.get("age", 30.0) or 30.0)
        if age >= 45:
            return "性腺功能随年龄缓慢下降"
        return ""
    stage = r.get("stage")
    if r.get("pregnant"):
        w = int(float(r.get("gest_week", 0.0)))
        naus = float(r.get("nausea", 0.0) or 0.0)
        extra = "，孕吐明显" if naus > 0.35 else ""
        return f"妊娠第 {w} 周{extra}"
    if stage == "postpartum":
        return "产后恢复期" + ("，哺乳中" if r.get("lactating") else "")
    if stage == "prepuberty":
        return "青春期前"
    if stage == "postmenopause":
        return "绝经后"
    if stage == "perimenopause":
        flash = float(r.get("hot_flash", 0.0) or 0.0)
        return "围绝经期" + ("，正在潮热" if flash > 0.4 else "")
    phase = PHASE_ZH.get(str(r.get("phase")), "")
    day = int(round(float(r.get("cycle_day", 0.0) or 0.0)))
    if not phase:
        return ""
    tail = ""
    if r.get("phase") == "menstrual":
        tail = "，有经量" if float(r.get("flow", 0)) > 0.1 else ""
    return f"月经周期第 {day} 天·{phase}{tail}"


def symptoms(body: Dict[str, Any]) -> List[Tuple[str, float]]:
    """周期相关的非特异不适，供 symptoms() 合并。"""
    r = body.get("repro")
    out: List[Tuple[str, float]] = []
    if not isinstance(r, dict) or not r:
        return out
    dys = float(r.get("dysmenorrhea", 0.0) or 0.0)
    if dys > 0.25:
        out.append(("下腹坠痛、腰酸", min(1.0, dys)))
    naus = float(r.get("nausea", 0.0) or 0.0)
    if naus > 0.25:
        out.append(("恶心、闻不得油烟", min(1.0, naus)))
    if float(r.get("hot_flash", 0.0) or 0.0) > 0.4:
        out.append(("突然一阵发热出汗", 0.7))
    if float(r.get("baby_blues", 0.0) or 0.0) > 0.3:
        out.append(("情绪低落、容易哭", 0.6))
    return out
