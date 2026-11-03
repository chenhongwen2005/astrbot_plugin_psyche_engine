"""睡眠：把「睡了一觉」拆成一整夜的结构。

为什么要把睡眠拆开
    原来 sleep_h 是一个数字，每晚按概率往目标值滑一点。这样能算出精力，
    但算不出「昨晚睡得浅」。而人描述自己状态时说得最多的恰恰是后者：
    「睡了八小时还是跟没睡一样」「三点醒了一次就再没睡实」。这两种情况
    的 sleep_h 一样，睡眠质量天差地别。

    所以这里真的排一遍夜里的结构：几点睡着、入睡花了多久、深睡占多少、
    REM 占多少、中间醒了几次、醒了多久。效率由这些推出来，而不是先定
    效率再倒推。

一夜是怎么走的
    bed_h 之后开始尝试入睡，抽样得到入睡潜伏 lat；睡着之后按小时累计。
    累计到 duration 就醒，落定 sleep_h / sleep_qual / sleep_debt。
    中间每小时的 sleep_h 就是已睡时长——所以凌晨三点的角色确实只睡了
    三小时，精力低得有理由，不是又一个凭空的「有点累」。

    这套状态机取代了原来「夜里每小时抽一次『今晚睡不睡』的签」。那时候
    一小时判定一次，同一夜要抽八次，偶尔还会先睡着了再被判成没睡着。

深睡与 REM 的取向
    深睡（N3）主要受睡眠压力驱动：欠得越多，前半夜压得越狠。年龄、酒精
    都会削它。REM 相对稳定，年龄略降、压力略升。这两个比例不做成随机数
    乱抽——它们是可指认的生理量，喝了两杯之后深睡变浅是有据可查的。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

DAY = 24.0


def new_state() -> Dict[str, Any]:
    return {
        "bed_h": 23.0,        # 今晚打算几点睡
        "sleeping": False,
        "done_night": -999,   # 已完成的那一夜的编号
        "elapsed": 0.0,
        "plan": None,         # 整夜结构（入睡后落定）
        "last": None,         # 昨夜记录，供注入块与报告用
    }


def ensure(body: Dict[str, Any]) -> Dict[str, Any]:
    st = body.get("sleep")
    if not isinstance(st, dict):
        st = new_state()
        body["sleep"] = st
    for k, v in new_state().items():
        st.setdefault(k, v)
    # 就寝点由昼夜相位决定：早鸟九十点就困，夜猫子过了午夜才躺下。
    # 只定一次（bed_pinned），之后按实际躺下的时刻记，否则每晚都被
    # 体质改回去，前一夜挪动的作息就白挪了。
    if not st.get("bed_pinned"):
        try:
            from . import traits as _TR
            st["bed_h"] = round((23.0 + 1.6 * _TR.chronotype(body)) % DAY, 2)
            st["bed_pinned"] = True
        except Exception:
            pass
    return st


def _need_hours(body: Dict[str, Any]) -> float:
    """这个人每晚需要睡多久。短睡者 6.6、长睡者 8.9，不是人人都 7.5。"""
    try:
        from . import traits as _TR
        return float(_TR.sleep_need(body))
    except Exception:
        return 7.5


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


# ----------------------------------------------------------------------
# 排一夜
# ----------------------------------------------------------------------
def plan_night(body: Dict[str, Any], rng, hour: float) -> Dict[str, Any]:
    """在真正躺下那一刻排定整夜结构。"""
    life = body.get("life") or {}
    env = body.get("env") or {}
    age = float(body.get("age", 30.0) or 30.0)
    debt = max(0.0, float(life.get("sleep_debt", 0.0) or 0.0))
    stress = _clip(life.get("stress", 0.3), 0.0, 1.0)
    alc = max(0.0, float(life.get("alcohol", 0.0) or 0.0))
    noise = float(env.get("noise", 45.0) or 45.0)
    temp = float(env.get("temp_c", 22.0) or 22.0)
    qual0 = _clip(life.get("sleep_qual", 0.8), 0.1, 1.0)

    # 睡眠需求：欠债越多越想睡，但压力大的人反而睡不长久
    need = _need_hours(body) + 0.30 * min(10.0, debt) - 1.3 * max(0.0, stress - 0.55)
    need -= 0.5 * max(0.0, alc - 1.0)      # 酒精让人早醒
    duration = _clip(need + rng.uniform(-0.9, 0.9), 3.5, 10.5)

    # 入睡潜伏（分钟）。焦虑的人躺在床上清醒很久，这是失眠的主诉之一。
    lat = 9.0 + 95.0 * max(0.0, stress - 0.30) + 25.0 * max(0.0, 0.75 - qual0) * 10.0
    lat -= 0.9 * min(10.0, debt)
    # 咖啡因按「睡前还剩多少」推迟入睡：下午三点那杯，到半夜还剩四分之一，
    # 而这四分之一足够让一个本来十分钟睡着的人翻四十分钟。
    try:
        from . import substance as _SUB
        mg = _SUB.caff(body)
        if mg > 20.0:
            lat += 55.0 * min(1.0, mg / 200.0)
        # 酒精帮人入睡、毁后半夜：这里只算「更快倒下」，深睡与夜醒另有去处
        lat -= 12.0 * min(1.0, _SUB.etoh(body) / 0.8)
    except Exception:
        pass
    lat += 6.0 * max(0.0, noise - 40.0) / 20.0
    lat += 4.0 * max(0.0, temp - 27.0) + 3.0 * max(0.0, 16.0 - temp)
    lat = _clip(lat + rng.uniform(0.0, 14.0), 3.0, 200.0)

    # 深睡（N3）：睡眠压力驱动，年龄与酒精削弱。
    # 0.155 的基线对应成人正常区间（13%~23%）的中段，健康人一夜
    # 应该读作「睡得还算实」，而不是一上来就「偏浅」。
    n3 = 0.155 + 0.080 * min(1.0, debt / 8.0) + 0.020 * _clip(
        float(life.get("activity", 1.0) or 1.0) - 1.0, 0.0, 1.5)
    n3 -= 0.0016 * max(0.0, age - 30.0) + 0.030 * min(2.0, alc)
    n3 = _clip(n3, 0.04, 0.28)

    # REM：年龄略降，情绪负荷略升
    rem = 0.225 - 0.0009 * max(0.0, age - 25.0) + 0.030 * max(0.0, stress - 0.55)
    rem = _clip(rem, 0.12, 0.30)

    # 夜醒：噪声、酒精、年龄、睡眠呼吸暂停、憋尿
    aw = 0.5 + 2.2 * max(0.0, noise - 42.0) / 30.0 + 2.6 * min(2.0, alc)
    aw += max(0.0, age - 40.0) / 45.0
    if _has(body, "阻塞性睡眠呼吸暂停") or _has(body, "单纯打鼾"):
        aw += 1.4
    aw += 1.0 if _has(body, "良性前列腺增生") or _has(body, "膀胱过度活动症") else 0.0
    aw = int(max(0, round(aw + rng.uniform(-0.6, 0.9))))

    # 醒着躺在床上的时间（分钟/次）
    waso = aw * (5.0 + 9.0 * max(0.0, noise - 40.0) / 25.0 + 3.0 * max(0.0, temp - 28.0))
    awake_min = lat + waso
    eff = _clip((duration * 60.0 - awake_min) / max(1.0, duration * 60.0), 0.40, 1.0)

    # 质量由效率与深睡共同决定：浅睡八小时不如沉睡六小时
    qual = _clip(eff * (0.78 + 1.05 * n3), 0.12, 1.0)
    return {
        "hours": round(duration, 2),
        "lat_min": round(lat, 0),
        "n3": round(n3, 3),
        "rem": round(rem, 3),
        "awakenings": aw,
        "waso_min": round(waso, 0),
        "eff": round(eff, 3),
        "qual": round(qual, 3),
        "bed_h": round(hour % DAY, 2),
    }


def _has(body: Dict[str, Any], zh: str) -> bool:
    for c in body.get("conditions") or []:
        if c.get("zh") == zh:
            return True
    return False


# ----------------------------------------------------------------------
# 每夜推进
# ----------------------------------------------------------------------
def tick(body: Dict[str, Any], hour: float, dt: float, rng,
         events: List[str]) -> None:
    st = ensure(body)
    life = body.get("life") or {}
    day = int(float(body.get("clock", 0.0)) // DAY)
    # 一夜的编号取「这个傍晚属于哪天」：23:00 躺下、次日 06:48 醒，
    # 两端都要算同一夜。用 clock//24 会在跨零点时把一夜劈成两半，
    # 结果是第二天傍晚判成「昨晚已经睡过」，整夜不睡。
    nid = day if hour >= 12.0 else day - 1

    # 已经睡着：先把这一觉走完，不管外面是白天黑夜。
    # 原来的写法在离开夜间窗口后直接 return，角色会带着「正在睡」
    # 的状态过一整天，直到当晚 23 点才结算。
    if st.get("sleeping"):
        plan = st.get("plan") or {}
        st["elapsed"] = float(st.get("elapsed", 0.0)) + dt
        slept = max(0.0, float(st["elapsed"]) - float(plan.get("lat_min", 10.0)) / 60.0)
        slept = min(slept, float(plan.get("hours", 7.5)))
        if not _locked(body, "sleep_h"):
            life["sleep_h"] = round(slept, 3)
        if float(st["elapsed"]) >= float(plan.get("hours", 7.5)) - 1e-9:
            _finish(body, st, plan, events, nid)
        return

    if st.get("done_night") == nid:
        return
    bed = float(st.get("bed_h", 23.0) or 23.0) % DAY
    # 以 18:00 为一夜的起点算「离就寝还有多久」。直接比 hour < bed 在
    # 就寝点过了午夜（夜猫子 1:30）时会永远不成立——1:30 之后到 7 点
    # 之间本该是最困的时候，却因为没有 22.5 <= 1.5 而整夜不睡。
    since = (hour - 18.0) % DAY
    off = (bed - 18.0) % DAY
    if since < off or since >= 13.0:
        return
    st["plan"] = plan_night(body, rng, hour)
    st["sleeping"] = True
    st["elapsed"] = 0.0
    events.append("sleep_onset")


def _finish(body: Dict[str, Any], st: Dict[str, Any], plan: Dict[str, Any],
            events: List[str], nid: int) -> None:
    life = body.get("life") or {}
    st["sleeping"] = False
    st["elapsed"] = 0.0
    st["done_night"] = nid
    st["last"] = dict(plan)

    actual = float(plan.get("hours", 7.5)) * float(plan.get("eff", 0.9))
    if not _locked(body, "sleep_h"):
        life["sleep_h"] = round(actual, 3)
    if not _locked(body, "sleep_qual"):
        # 与昨夜做一点黏连：一晚睡不好不会立刻变成长久的坏睡眠，
        # 但连着几天浅睡会把基线拖下去。
        prev = float(life.get("sleep_qual", 0.8) or 0.8)
        life["sleep_qual"] = round(_clip(0.55 * float(plan.get("qual", 0.8)) + 0.45 * prev,
                                         0.12, 1.0), 3)
    debt = float(life.get("sleep_debt", 0.0) or 0.0)
    life["sleep_debt"] = round(_clip(debt + (_need_hours(body) - actual), 0.0, 60.0), 2)
    # 起床这件事本身会把口渴与尿意带出来（见 intero）
    events.append("wake")


def _locked(body: Dict[str, Any], key: str) -> bool:
    try:
        from .body import locked
        return bool(locked(body, key))
    except Exception:
        return False


# ----------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------
def depth_word(n3: float) -> str:
    # 阈值对着成人正常范围来定：N3 占整夜 13%~23% 是常态，
    # 所以 15% 不该说成「偏浅」——那是把正常当异常。
    if n3 >= 0.21:
        return "睡得很沉"
    if n3 >= 0.15:
        return "睡得还算实"
    if n3 >= 0.09:
        return "睡得偏浅"
    return "几乎一直在浅睡"


def line(body: Dict[str, Any]) -> str:
    """一句话描述昨夜。没有记录（新建角色/刚重置）就返回空。"""
    st = body.get("sleep") or {}
    last = st.get("last")
    if not isinstance(last, dict) or not last:
        return ""
    return describe(last)


def describe(last: Dict[str, Any]) -> str:
    h = float(last.get("hours", 0.0))
    hh = int(h)
    mm = int(round((h - hh) * 60))
    parts = [f"睡了 {hh} 小时" + (f" {mm} 分" if mm else "")]
    aw = int(last.get("awakenings", 0))
    if aw >= 3:
        parts.append(f"中间醒了 {aw} 次")
    elif aw >= 1:
        parts.append("醒过一次")
    lat = float(last.get("lat_min", 0.0))
    if lat >= 45:
        parts.append("躺了很久才睡着")
    parts.append(depth_word(float(last.get("n3", 0.15))))
    rem = float(last.get("rem", 0.22))
    if rem >= 0.27:
        parts.append("梦特别多")
    return "，".join(parts)


def summary(body: Dict[str, Any]) -> str:
    """报告里的一行，带效率。"""
    st = body.get("sleep") or {}
    last = st.get("last")
    if not isinstance(last, dict) or not last:
        return ""
    eff = float(last.get("eff", 0.9))
    return f"{describe(last)}（睡眠效率 {eff * 100:.0f}%）"


def symptoms(body: Dict[str, Any]) -> List[Tuple[str, float]]:
    """糟糕的一夜会在第二天留下具体的痕迹，但不是「累」这种万能词。"""
    out: List[Tuple[str, float]] = []
    st = body.get("sleep") or {}
    last = st.get("last")
    if not isinstance(last, dict) or not last:
        return out
    # 睡不好的后遗只在上午算数。到了晚上还说「睡醒还是发懵」，
    # 说的是昨天早上的事——那不是状态，那是复读。
    hour = float(body.get("clock", 0.0) or 0.0) % 24.0
    if hour >= 12.0:
        return out
    # 还睡着的时候没有「睡醒还是发懵」——那要等醒了才成立。
    if st.get("sleeping"):
        return out
    if float(last.get("n3", 0.2)) < 0.10:
        out.append(("睡醒还是发懵", 0.4))
    if int(last.get("awakenings", 0)) >= 4:
        out.append(("后半夜断断续续", 0.35))
    if float(last.get("lat_min", 0)) >= 60:
        out.append(("躺下以后翻来覆去", 0.4))
    return out
