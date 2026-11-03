"""外伤：人是被自己笨手笨脚弄伤的。

为什么单独一个模块
    疾病目录里的每一条都是「病原体或内因把身体弄坏了」，按天抽签决定
    这个月会不会得。外伤不是这么来的：切菜时手一滑、下楼梯踩空一级、
    端着开水转身撞到人，这些事发生的概率跟"这个月"没关系，跟"此刻在
    干什么、有多困、喝了多少"有关系。

    所以这批条目的 base 一律为 0，不参与按天抽签；改由这里按小时算
    情境风险。它们仍然留在 DISEASES 里，因为病程、疼痛、症状、治疗、
    器官损伤那一整套管线都现成——另开一套只会让两边的规则慢慢走偏。

情境怎么算
    每个模板挂一组因子，因子返回的是乘数：
      · 做饭（三餐前后）——切伤、烫伤、烫到嘴、呛到
      · 笨手笨脚——困、累、喝酒，这一项的权重最大
      · 运动量——拉伤、扭伤、水泡、擦伤
      · 视力——看不清才切得到手
      · 户外与日照——晒伤、蜂蜇
      · 干燥——鼻出血

    乘数不是拍脑袋：喝酒后切到手的概率确实是平时的两三倍，困到睡眠债
    十小时以上的人端不稳杯子，这两条都能在日常经验里对上。

严重度不是抽签抽出来的
    伤口多大取决于当时在干什么。切菜切到手指是浅口，剁骨头时走刀是
    深口。这里让 sev0 跟着因子走，而不是所有外伤都从同一个初值开始。
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .diseases import DISEASES
from . import body as B

# 每个模板每小时的基础风险（中性条件下）。
# 上表原本按「一周一次小磕碰」定标，实测在做饭、运动、疲劳这些乘数
# 叠上去之后变成三天一次——一年一百多次，那不是人，那是纸糊的。
# 乘数保留（它们各自都对），基线压到 0.4 倍，落到一年三十来次。
BASE: Dict[str, float] = {
    "INJ-BRUISE": 0.00064,
    "INJ-PAPER": 0.00040,
    "INJ-CUT": 0.00036,
    "INJ-STUB": 0.00028,
    "INJ-SCALD-MOUTH": 0.00020,
    "INJ-BLISTER": 0.00016,
    "INJ-CHOKE": 0.00016,
    "INJ-SCRAPE": 0.00012,
    "INJ-SPLINTER": 0.00012,
    "INJ-BURN": 0.00012,
    "INJ-STRAIN": 0.00012,
    "INJ-SPRAIN-WRIST": 0.00008,
    "INJ-FOREIGN-EYE": 0.00008,
    "ENT-EPISTAXIS": 0.00008,
    "INJ-SUNBURN": 0.00008,
    "INJ-STING": 0.00008,
    # 中重度：低一个数量级。年化之后大约是「一年一两次」的量级，
    # 各自还要乘情境因子（运动、疲劳、年龄）才会有明显上升。
    "INJ-FALL": 0.0000060,
    "INJ-LACERATION": 0.0000040,
    "INJ-BURN-2ND": 0.0000030,
    "INJ-FRACTURE-WRIST": 0.0000020,
    "INJ-FRACTURE-ANKLE": 0.0000015,
    "INJ-CONCUSSION": 0.0000015,
    "INJ-DENTAL": 0.0000015,
    "INJ-DISLOC-SHOULDER": 0.0000010,
    "INJ-EYE-CHEM": 0.0000008,
}

# 每个模板受哪些因子影响
FACTORS: Dict[str, tuple] = {
    "INJ-BRUISE": ("dense", "clumsy"),
    "INJ-PAPER": ("desk",),
    "INJ-CUT": ("cook", "clumsy", "sight"),
    "INJ-STUB": ("dense", "clumsy"),
    "INJ-SCALD-MOUTH": ("cook", "clumsy"),
    "INJ-BLISTER": ("sport",),
    "INJ-CHOKE": ("cook", "clumsy"),
    "INJ-SCRAPE": ("sport", "clumsy"),
    "INJ-SPLINTER": ("chores",),
    "INJ-BURN": ("cook", "clumsy"),
    "INJ-STRAIN": ("sport", "age"),
    "INJ-SPRAIN-WRIST": ("sport", "clumsy"),
    "INJ-FOREIGN-EYE": ("outdoor", "wind"),
    "ENT-EPISTAXIS": ("dry",),
    "INJ-SUNBURN": ("outdoor", "sun"),
    "INJ-STING": ("outdoor", "warm"),
    # 中重度
    "INJ-FALL": ("dense", "clumsy", "age"),
    "INJ-LACERATION": ("cook", "clumsy"),
    "INJ-BURN-2ND": ("cook", "clumsy"),
    "INJ-FRACTURE-WRIST": ("sport", "dense", "age"),
    "INJ-FRACTURE-ANKLE": ("sport", "age"),
    "INJ-CONCUSSION": ("sport", "dense", "clumsy"),
    "INJ-DENTAL": ("sport", "clumsy"),
    "INJ-DISLOC-SHOULDER": ("sport", "age"),
    "INJ-EYE-CHEM": ("chores",),
}


# 一上来就是重伤的那几条，初值另算
_SEVERE = frozenset({
    "INJ-LACERATION", "INJ-BURN-2ND", "INJ-FRACTURE-WRIST",
    "INJ-FRACTURE-ANKLE", "INJ-DISLOC-SHOULDER", "INJ-CONCUSSION",
    "INJ-FALL", "INJ-EYE-CHEM", "INJ-DENTAL",
})


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(v)))


def _ctx(body: Dict[str, Any]) -> Dict[str, float]:
    """当下情境。一次算好，所有模板共用。"""
    life = body.get("life") or {}
    env = body.get("env") or {}
    hour = B.hour_of_day(body)
    energy = float((body.get("energy") or {}).get("level", 0.7) or 0.7)
    debt = float(life.get("sleep_debt", 0.0) or 0.0)
    # 用**此刻的血酒精**，不用"每天几杯"的习惯：白天不喝酒的人晚上不会
    # 因为"习惯是两杯"而更容易切到手。
    try:
        from . import substance as _SUB
        alc = min(2.5, _SUB.etoh(body) / 0.5)
    except Exception:
        alc = float(life.get("alcohol", 0.0) or 0.0) * 0.3
    stress = _clip(life.get("stress", 0.3), 0.0, 1.0)
    act = _clip(life.get("activity", 1.0), 0.0, 2.5)
    age = float(body.get("age", 30.0) or 30.0)

    # 三餐前后在灶台边上：7-9、11-13.5、17-20
    cook = 1.0 if (6.5 <= hour < 9.0 or 11.0 <= hour < 13.5
                   or 17.0 <= hour < 20.0) else 1.0
    # 白天在户外的时间大致由日照与活动量推——没有定位，只能这么估
    outdoors = 0.5 + 0.5 * act
    if hour < 7.0 or hour >= 21.0:
        outdoors *= 0.05
    sun_min = float(life.get("sun", 20.0) or 20.0)

    fatigue = _clip((1.0 - energy) * 1.6 + debt / 14.0, 0.0, 1.6)
    return {
        "hour": hour,
        "cook": cook,
        "fatigue": fatigue,
        "alc": alc,
        "stress": stress,
        "act": act,
        "age": age,
        "energy": energy,
        "outdoor": _clip(outdoors, 0.0, 1.4),
        "sun": _clip(sun_min / 60.0, 0.0, 4.0),
        "temp": float(env.get("temp_c", 22.0) or 22.0),
        "humidity": float(env.get("humidity", 55.0) or 55.0),
        "wind": float(env.get("pm25", 25.0) or 25.0) / 100.0,
    }


def _fam(body: Dict[str, Any], name: str, c: Dict[str, float]) -> float:
    """单个因子的乘数。"""
    if name == "cook":
        return 3.2
    if name == "clumsy":
        # 困与醉是两件事，但都会让人端不稳东西
        return 1.0 + 1.05 * min(2.0, c["alc"]) + 0.85 * c["fatigue"] \
            + 0.30 * max(0.0, c["stress"] - 0.55)
    if name == "sport":
        return 0.35 + 1.15 * c["act"]
    if name == "desk":
        # 长时间伏案／翻纸才有纸割伤，躺着不会有
        return 0.3 + 0.9 * _clip(B.life(body, "sedentary") / 8.0, 0.0, 1.5)
    if name == "sight":
        eye = 1.0
        for o, fn in (body.get("organs") or {}).items():
            if o == "eye":
                eye = float(fn)
        return 1.0 + 1.4 * max(0.0, 1.0 - eye)
    if name == "dense":
        # 人多、东西多的地方磕碰多：用活动量与是否白天粗估
        return 0.45 + 0.55 * c["outdoor"] + 0.25 * c["act"]
    if name == "chores":
        return 0.5 + 0.7 * _clip(c["act"], 0.0, 1.5)
    if name == "outdoor":
        return 0.10 + 0.90 * c["outdoor"]
    if name == "sun":
        return 0.2 + 0.8 * min(1.0, c["sun"] / 1.5) * _clip((c["temp"] - 18.0) / 12.0, 0.0, 1.0)
    if name == "wind":
        return 0.5 + 1.5 * c["wind"]
    if name == "dry":
        return 0.4 + 1.6 * _clip((45.0 - c["humidity"]) / 30.0, 0.0, 1.0)
    if name == "warm":
        return 0.15 + 0.85 * _clip((c["temp"] - 15.0) / 15.0, 0.0, 1.0)
    if name == "age":
        # 三十五岁往后，热身不够就拉伤是常事
        return 0.7 + 0.9 * _clip((c["age"] - 35.0) / 30.0, 0.0, 1.0)
    return 1.0


def _mult(body: Dict[str, Any], code: str, c: Dict[str, float]) -> float:
    m = 1.0
    for f in FACTORS.get(code, ()):
        m *= _fam(body, f, c)
    return m


# ----------------------------------------------------------------------
# 受伤
# ----------------------------------------------------------------------
def _sev0(body: Dict[str, Any], code: str, c: Dict[str, float], rng) -> float:
    """伤得多重取决于当时在干什么，不是抽签抽出来的。"""
    base = 0.22 + rng.uniform(0.0, 0.16)
    if code in ("INJ-CUT", "INJ-BURN", "INJ-STRAIN", "INJ-SPRAIN-WRIST"):
        # 又困又醉的人下刀更狠、摔得更实
        base += 0.22 * min(1.0, c["fatigue"]) + 0.18 * min(1.0, c["alc"])
    if code in ("ENT-EPISTAXIS", "INJ-CHOKE", "INJ-PAPER"):
        base *= 0.7
    # 中重度伤一上来就重：骨折、脱位、二度烧伤不是「刚开始有点疼」
    if code in _SEVERE:
        base = 0.56 + rng.uniform(0.0, 0.22)
        base += 0.10 * min(1.0, c["alc"]) + 0.08 * _clip((c["age"] - 50.0) / 40.0, 0.0, 1.0)
    return round(_clip(base, 0.10, 0.90), 3)


def _inflict(body: Dict[str, Any], code: str, c: Dict[str, float],
             rng, events: List[str]) -> None:
    spec = DISEASES.get(code)
    if not spec:
        return
    if any(x.get("code") == code for x in (body.get("conditions") or [])):
        return                                    # 同一个伤口不叠两条
    item = B.add_condition(body, code, spec["zh"],
                           sev=_sev0(body, code, c, rng), note=spec.get("note", ""))
    item["sev0"] = item.get("sev")
    item["treat_effect"] = 0.0
    # 受伤那一刻的动作会留在描述里，而不是干巴巴一个病名
    zh = _detail(code)
    B.push_log(body, f"{zh}", "injury")
    events.append(f"injury:{spec['zh']}")


def _detail(code: str) -> str:
    return {
        "INJ-CUT": "切东西的时候划到了手",
        "INJ-PAPER": "被纸边划了一下",
        "INJ-SCRAPE": "摔了一跤，蹭破一块皮",
        "INJ-BRUISE": "撞到了，青了一块",
        "INJ-BURN": "被热的东西烫到了",
        "INJ-SCALD-MOUTH": "吃太急，烫到嘴了",
        "INJ-STRAIN": "猛一使劲，抻到了",
        "INJ-SPRAIN-WRIST": "撑地的时候手腕别了一下",
        "INJ-FOREIGN-EYE": "有东西进眼睛里了",
        "INJ-SPLINTER": "手上扎了根刺",
        "INJ-STUB": "脚趾踢到硬东西上了",
        "ENT-EPISTAXIS": "鼻子出血了",
        "INJ-BLISTER": "鞋把脚磨出水泡了",
        "INJ-SUNBURN": "晒过头了",
        "INJ-STING": "被虫子蜇了",
        "INJ-CHOKE": "呛了一下",
        "INJ-LACERATION": "切东西时割得很深，血止不住",
        "INJ-BURN-2ND": "被热水泼到，起了一片泡",
        "INJ-FRACTURE-WRIST": "摔的时候用手撑地，手腕折了",
        "INJ-FRACTURE-ANKLE": "落地时脚踝别断了一样",
        "INJ-DISLOC-SHOULDER": "胳膊被拽脱了臼",
        "INJ-CONCUSSION": "头撞到了，好一会儿缓不过来",
        "INJ-FALL": "脚下一滑，整个人摔在地上",
        "INJ-EYE-CHEM": "有东西溅进眼睛，冲了半天",
        "INJ-DENTAL": "磕到牙，崩掉一块",
    }.get(code, "受了点外伤")


def inflict(body: Dict[str, Any], code: str, events: List[str]) -> bool:
    """指定一条外伤，按当下情境定初值。

    运动损伤走这条：跑步崴脚不是随机的「平地摔」，而是这次运动强度、
    年龄、疲劳共同决定的一次意外，用同一套初值算法才不会两边打架。
    """
    spec = DISEASES.get(code)
    if not spec or spec.get("kind") != "injury":
        return False
    rng = B.rng_for(body, salt=37)
    _inflict(body, code, _ctx(body), rng, events)
    # 旧的 flags 里有一个 injury 摘要，时间线还在读它
    flags = body.setdefault("flags", {})
    flags["injury"] = spec["zh"]
    flags["injury_until"] = float(body.get("clock", 0.0)) + float(spec.get("dur") or 240.0)
    return True


def step(body: Dict[str, Any], hours: float, events: List[str]) -> None:
    """按小时推进。睡着、危重的时候不会平地摔一跤。"""
    if hours <= 0:
        return
    flags = body.get("flags") or {}
    if flags.get("critical"):
        return
    sleep = body.get("sleep") or {}
    if sleep.get("sleeping"):
        return
    c = _ctx(body)
    rng = B.rng_for(body, salt=31)
    for code, base in BASE.items():
        p = 1.0 - math.exp(-base * _mult(body, code, c) * float(hours))
        if rng.random() < p:
            _inflict(body, code, c, rng, events)


# ----------------------------------------------------------------------
# 输出
# ----------------------------------------------------------------------
def active(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for cond in body.get("conditions") or []:
        spec = DISEASES.get(cond.get("code", ""))
        if spec and spec.get("kind") == "injury" and float(cond.get("sev", 0)) > 0.03:
            out.append(cond)
    return out


def line(body: Dict[str, Any]) -> str:
    """注入块里的一行。

    只写「哪伤、第几天、到哪一步」，不重复症状——症状已经由「身上：」
    那一行说了，两处都写同一句「手指上划开一道口子」，读起来像是复读。
    这里补的是那行给不出的信息：这是第几天，以及正在结痂还是快好了。
    """
    items = sorted(active(body), key=lambda x: -float(x.get("sev", 0)))[:2]
    if not items:
        return ""
    clock = float(body.get("clock", 0.0) or 0.0)
    bits = []
    for cond in items:
        spec = DISEASES.get(cond["code"]) or {}
        name = spec.get("zh", "外伤")
        s0 = max(1e-6, float(cond.get("sev0", 0.3) or 0.3))
        left = float(cond.get("sev", 0.0)) / s0
        if left > 0.72:
            stage = "刚弄的"
        elif left > 0.34:
            stage = "正在长好"
        else:
            stage = "快好了"
        hours = max(0.0, clock - float(cond.get("onset", clock)))
        if hours < 24.0:
            bits.append(f"{name}（{stage}）")
        else:
            bits.append(f"{name}（第 {int(hours // 24) + 1} 天，{stage}）")
    return "外伤：" + "；".join(bits)


def symptoms(body: Dict[str, Any]) -> List[Any]:
    """症状表补一条「伤口在疼」，避免只有病名没有体感。"""
    out = []
    for cond in active(body):
        sev = float(cond.get("sev", 0.0))
        if sev >= 0.45:
            out.append(("伤口一跳一跳地疼", min(0.9, sev)))
    return out


def summary(body: Dict[str, Any]) -> str:
    return line(body)
