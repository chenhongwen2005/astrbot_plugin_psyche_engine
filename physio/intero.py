"""内感受：饿、渴、想上厕所、身上痒。

为什么缺这个
    在这之前，身体是一套「器官完好度 + 化验单 + 疾病」的系统。它知道
    你有没有贫血，但不知道你上一顿是什么时候吃的。于是角色可以一整天
    不吃饭、不喝水、不上厕所而毫无感觉——这不是一个身体，这是一张报告。

    饥饿、口渴、尿意、便意是人一天里出现频率最高的身体信号，比「累」
    高一个数量级。一个真实的人在聊天时突然说「等下，我去趟厕所」，
    靠的就是这几个量。

为什么不放进能量预算
    energy.py 算的是「还剩多少劲」，是预算。饿和渴不是预算，是**驱力**：
    它们不降低你的能力，它们要求你做点什么。混在一起会让「饿」永远
    只表现为「精力低」，而那正是上一版被吐槽的含糊。

为什么不直接写进注入块
    这四个量在一天里大半时间都处在「有一点但不必提」的区间。全都写
    出来会把注入块填满废话。所以这里只做两件事：算出 0~1 的值，以及
    只在越过阈值时给一句话。阈值定得偏高是有意的——正常人一天里真正
    「饿得慌」「憋不住」的时刻就那么几次。

自处理的边界
    尿意和便意到顶了必须自己解决，否则角色会永远憋着，越憋越不像人。
    所以 fill 超过 1.05 就自动排空并记一条日志。这不是替模型做决定，
    是这个人确实去了——注入段里会写「刚去过一趟」，模型知道发生了什么。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

DAY = 24.0

# 三餐时点（小时）。按这个推「上一顿是什么时候」，不需要额外状态。
MEALS = (7.5, 12.5, 19.0)


def ensure(body: Dict[str, Any]) -> Dict[str, Any]:
    """补齐内感受状态。旧存档没有这个键，进来就地补上。"""
    it = body.get("intero")
    if not isinstance(it, dict):
        it = {}
        body["intero"] = it
    it.setdefault("bladder", 0.30)
    it.setdefault("bowel", 0.20)
    it.setdefault("voids", 0)
    it.setdefault("stools", 0)
    it.setdefault("last_void_h", 0.0)
    return it


# ----------------------------------------------------------------------
# 推进：膀胱与肠道充盈
# ----------------------------------------------------------------------
def step(body: Dict[str, Any], hours: float) -> List[str]:
    """推进充盈。返回这一步发生的事（去了厕所之类）。"""
    if hours <= 0:
        return []
    it = ensure(body)
    life = body.get("life") or {}
    events: List[str] = []

    water = float(life.get("water", 0.85) or 0.85)
    fiber = float(life.get("fiber", 0.7) or 0.7)

    # 正常成人一天排尿 5~6 次，约 1.5L。喝得多就快，缺水时肾脏先省水，
    # 所以缺水的人反而尿得少——这一项让「渴」和「想上厕所」不同步，
    # 真实的人也是这样：越不喝水越不去厕所，越不去越不觉得渴。
    urine_rate = 0.115 + 0.060 * max(0.0, water - 0.60) - 0.045 * max(0.0, 0.55 - water)
    it["bladder"] = float(it["bladder"]) + hours * max(0.02, urine_rate)

    # 膀胱功能差的人存不住：容量小、残余多，稍有尿意就急
    bad_bladder = 1.0 - _organ(body, "bladder")
    if bad_bladder > 0.05:
        it["bladder"] = float(it["bladder"]) + hours * 0.06 * bad_bladder

    if it["bladder"] >= 1.05:
        it["bladder"] = 0.06
        it["voids"] = int(it.get("voids", 0)) + 1
        it["last_void_h"] = float(body.get("clock", 0.0) or 0.0)
        events.append("void")

    # 排便：膳食纤维决定速度。一天一次对应约 22 小时涨满。
    it["bowel"] = float(it["bowel"]) + hours * (0.020 + 0.026 * fiber)
    if it["bowel"] >= 1.05:
        it["bowel"] = 0.05
        it["stools"] = int(it.get("stools", 0)) + 1
        events.append("stool")

    return events


# ----------------------------------------------------------------------
# 计算
# ----------------------------------------------------------------------
def _organ(body: Dict[str, Any], key: str) -> float:
    return float((body.get("organs") or {}).get(key, 1.0) or 1.0)


def _since_meal(hour: float) -> float:
    """距上一顿的小时数。找不到饭点就按醒来的时间算。"""
    best = None
    for m in MEALS:
        d = (hour - m) % DAY
        if best is None or d < best:
            best = d
    # 还没吃过早饭（凌晨）时，从昨晚 19 点算起是对的
    if best is None:
        best = (hour - 19.0) % DAY
    return best


def _since_wake(hour: float) -> float:
    return hour - 7.0 if hour >= 7.0 else hour + 17.0


def compute(body: Dict[str, Any], labs: Dict[str, float],
            vitals: Dict[str, float], derived: Dict[str, Any]) -> Dict[str, Any]:
    it = ensure(body)
    life = body.get("life") or {}
    clock = float(body.get("clock", 0.0) or 0.0)
    hour = clock % DAY

    # ---- 饿 ----
    since = _since_meal(hour)
    kcal = float(life.get("kcal", 1.0) or 1.0)
    # 吃得少的人饿得快；血糖低会显著把饥饿推上来
    speed = 1.0 / max(0.55, min(1.5, kcal))
    # 3 小时起步、10 小时到顶：晚饭 19 点、早上 7 点醒，正好是「饿了」。
    # 原来用 (since-2.2)/4.6，三小时就顶格，于是整夜都是「饿得叫」。
    hunger = (since - 3.0) / 7.0 * speed
    glu = labs.get("GLU")
    if isinstance(glu, (int, float)) and float(glu) < 4.4:
        hunger += (4.4 - float(glu)) * 0.22
    hunger = _clip01(hunger)

    # ---- 渴 ----
    water = float(life.get("water", 0.85) or 0.85)
    # 阈值 0.92 而不是 0.78：喝水之后血浆渗透压会被压低一点，人并不觉得
    # 渴；真正口渴出现在一夜没喝之后（约 0.75）和出汗之后。
    thirst = (0.92 - water) / 0.34
    osm = labs.get("OSM")
    if isinstance(osm, (int, float)) and float(osm) > 292:
        thirst += (float(osm) - 292.0) / 22.0
    na = labs.get("NA") if "NA" in labs else labs.get("Na")
    if isinstance(na, (int, float)) and float(na) > 143:
        thirst += (float(na) - 143.0) / 9.0
    thirst = _clip01(thirst)

    # ---- 尿意 / 便意 ----
    # 尿意大致线性：攒到一半就开始有感觉。
    urg_b = _clip01((float(it["bladder"]) - 0.30) / 0.62)
    # 便意不是线性的。结肠把内容物存在降结肠里可以几个小时毫无感觉，
    # 一旦推进直肠就是「现在就得去」。用二次曲线才能表现这个陡升，
    # 线性会让角色连着六个小时都在「肚子发胀」。
    urg_s = _clip01(max(0.0, (float(it["bowel"]) - 0.55) / 0.50) ** 2.2)

    # ---- 困 ----
    debt = max(0.0, float(life.get("sleep_debt", 0.0) or 0.0))
    awake = _since_wake(hour)
    # 睡眠压力近似线性累积，到 16 小时清醒时接近满
    pressure = min(1.0, awake / 16.0) * 0.75 + min(1.0, debt / 20.0) * 0.35
    if 1.0 <= hour <= 5.0:
        pressure += 0.20          # 生物夜里的那一段，最难撑
    sleepiness = _clip01(pressure)

    # ---- 痒 ----
    skin = _organ(body, "skin")
    hum = float((body.get("env") or {}).get("humidity", 55.0) or 55.0)
    itch = (1.0 - skin) * 2.4 + max(0.0, (40.0 - hum) / 40.0) * 0.35
    itch = _clip01(itch)

    sig: List[Tuple[str, float]] = []
    if hunger >= 0.66:
        sig.append(("肚子饿得叫", hunger))
    if thirst >= 0.55:
        sig.append(("口干，想喝水", thirst))
    if urg_b >= 0.72:
        sig.append(("想去趟厕所", urg_b))
    if urg_s >= 0.72:
        sig.append(("肚子发胀，想上个大号", urg_s))
    if itch >= 0.60:
        sig.append(("身上发痒", itch))

    # 睡着的时候这些都感觉不到：饿、渴、痒都在睡梦里，不会变成
    # 「想去趟厕所」那样的念头。唯一能真的把人弄醒的是憋尿，
    # 而且要到很满才行——半夜憋醒是真实的，饿醒不是。
    if _sleeping(body):
        if urg_b >= 0.86:
            sig = [("憋得慌，可能要被憋醒", urg_b)]
        else:
            sig = []

    return {
        "hunger": round(hunger, 3),
        "thirst": round(thirst, 3),
        "urge_bladder": round(urg_b, 3),
        "urge_bowel": round(urg_s, 3),
        "sleepiness": round(sleepiness, 3),
        "itch": round(itch, 3),
        "since_meal_h": round(since, 1),
        "signals": sig,
    }


def _sleeping(body: Dict[str, Any]) -> bool:
    st = body.get("sleep")
    return bool(isinstance(st, dict) and st.get("sleeping"))


def _clip01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


# ----------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------
def line(body: Dict[str, Any]) -> str:
    """一句话，进注入段。没有越线的信号就返回空串。"""
    d = body.get("derived") or {}
    io = d.get("intero") or {}
    sig = io.get("signals") or []
    if not sig:
        return ""
    sig = sorted(sig, key=lambda kv: -kv[1])
    return "、".join(s for s, _ in sig[:2])


def symptoms(body: Dict[str, Any]) -> List[Tuple[str, float]]:
    """内感受不进「身上：」症状表。

    症状表描述的是「哪里不对劲」，而饿、渴、想上厕所是「需要做点什么」。
    两个都写会出现「身上：饿得发慌；肚子饿得叫」这种同一件事说两遍的
    注入块——注入块的篇幅是要抢的，重复一条就少一条。
    """
    return []


def summary(body: Dict[str, Any]) -> str:
    return line(body)
