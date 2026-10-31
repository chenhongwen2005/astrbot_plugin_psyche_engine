"""身体状态容器。

刻意用纯 dict + 显式 schema，而不是 dataclass：
  1) 要能原样塞进 MindState.meta 或独立字段，JSON 序列化零成本；
  2) 新增器官/检验时不用改类定义，旧存档也能读（缺的键按默认值补）。

时间模型：
  虚拟时钟 clock 以「小时」为单位累积，每轮对话推进 hours_per_turn（默认 6，
  即 4 轮＝1 天）。不跟真实时间走，是为了让"熬夜三天""连吃一周外卖"这类
  长程暴露能在几十轮对话内被观察到。精神科那套以「轮」为单位的 τ 保持不变，
  两边通过显式的 hours_per_turn 换算，互不干扰。
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple

from .const import ENV, LIFE, ORGANS

SEX_ZH = {"m": "男", "f": "女"}


# ----------------------------------------------------------------------
# 年龄对器官储备的影响
# ----------------------------------------------------------------------
# 值 = 每增长 10 岁，器官功能下降的绝对量（到 0.35 封底）
AGE_DECLINE: Dict[str, float] = {
    "heart": 0.020, "vessels": 0.045, "lungs": 0.030, "kidney": 0.055,
    "kidney_tubule": 0.030, "liver": 0.015, "marrow": 0.020,
    "bone": 0.050, "muscle": 0.040, "joint": 0.045, "eye": 0.045,
    "ear": 0.040, "nerve": 0.020, "brain": 0.015, "skin": 0.025,
    "immune": 0.030, "pancreas_endo": 0.020, "thyroid": 0.010,
    "gonad": 0.030, "gut": 0.010, "coag": 0.005,
}

# 衰退的起点。真实世界里 30 岁之前器官储备几乎是一条平线，
# 之前写成 20 岁起算，会让 34 岁的人一上来就只剩 92% 肾功能——
# 那不是"储备下降"，那是肾功能不全，化验单会跟着一起假下来。
DECLINE_ONSET_AGE = 30.0


def organ_baseline(organ: str, age: float) -> float:
    dec = AGE_DECLINE.get(organ, 0.010)
    v = 1.0 - dec * max(0.0, age - DECLINE_ONSET_AGE) / 10.0
    return max(0.35, min(1.0, v))


def healthy_life() -> Dict[str, float]:
    return {k: v[1] for k, v in LIFE.items()}


def healthy_env() -> Dict[str, float]:
    return {k: v[1] for k, v in ENV.items()}


def new_body(
    *,
    sex: str = "m",
    age: float = 30.0,
    height_cm: Optional[float] = None,
    weight_kg: Optional[float] = None,
    preset: str = "healthy",
    seed: int = 20261030,
) -> Dict[str, Any]:
    if height_cm is None:
        height_cm = 172.0 if sex == "m" else 160.0
    if weight_kg is None:
        bmi_target = 22.5
        weight_kg = round(bmi_target * (height_cm / 100.0) ** 2, 1)

    organs = {k: organ_baseline(k, age) for k in ORGANS}
    # 脂肪与胰岛素敏感性：健康人按 BMI 微调
    bmi = weight_kg / (height_cm / 100.0) ** 2
    organs["fat"] = max(0.35, min(1.6, bmi / 22.5))
    organs["fat_sens"] = max(0.25, min(1.0, 1.10 - 0.02 * max(0.0, bmi - 22.5)))

    body: Dict[str, Any] = {
        "v": 1,
        "seed": seed,
        "sex": sex,
        "age": age,
        "height": height_cm,
        "clock": 0.0,
        "tick": 0,
        "preset": preset,
        "organs": organs,
        "damage": {k: 0.0 for k in ORGANS},
        "irreversible": {k: 0.0 for k in ORGANS},
        "life": healthy_life(),
        "env": healthy_env(),
        "conditions": [],      # 活动疾病
        "history": [],         # 既往病史（已痊愈）
        "meds": [],            # 生理用药
        "labs": {},
        "vitals": {},
        "derived": {},
        "log": [],             # 最近 40 条生活事件
        "flags": {},
        "dead": False,
    }
    _apply_preset(body, preset)
    return body


# ----------------------------------------------------------------------
# 起始预设
# ----------------------------------------------------------------------
PRESETS: Dict[str, Dict[str, Any]] = {
    "healthy": {},
    "athlete": {"age": 26.0, "life": {"fitness": 0.90, "activity": 2.2,
                                      "sleep_h": 8.0, "resting_hr": 52.0},
                "organs": {"heart": 1.05, "lungs": 1.08, "muscle": 1.10,
                           "fat": -0.18}},
    "sedentary": {"life": {"fitness": 0.32, "activity": 0.4, "sedentary": 11.0,
                            "sleep_h": 6.4},
                  "organs": {"fat": 0.12}},
    "obese": {"age": 42.0, "bmi_shift": 9.0,
              "life": {"kcal": 1.35, "satfat": 1.5, "sugar": 1.6,
                       "activity": 0.5, "fitness": 0.35},
              "organs": {"fat_sens": -0.35, "fat": 0.45}},
    "smoker": {"life": {"smoking": 18.0, "fitness": 0.45},
               "organs": {"lungs": -0.12, "airway": -0.15, "vessels": -0.10}},
    "drinker": {"life": {"alcohol": 4.0},
                "organs": {"liver": -0.20, "gut": -0.05}},
    "insomniac": {"life": {"sleep_h": 5.0, "sleep_debt": 12.0, "sleep_qual": 0.35,
                            "stress": 0.65},
                  "organs": {"immune": -0.10, "brain": -0.05}},
    "burnout": {"age": 38.0, "life": {"stress": 0.85, "sleep_h": 5.6,
                                       "sleep_debt": 9.0, "activity": 0.4},
                "organs": {"immune": -0.15, "heart": -0.06}},
    "elderly": {"age": 76.0, "life": {"fitness": 0.30, "activity": 0.5,
                                       "vitd": 0.35, "protein": 0.65},
                "organs": {"bone": -0.10, "muscle": -0.10}},
    "frail": {"age": 84.0, "life": {"fitness": 0.18, "activity": 0.25,
                                     "protein": 0.55, "water": 0.6},
              "organs": {"muscle": -0.20, "bone": -0.20, "immune": -0.15}},
    "chronically_ill": {"age": 58.0,
                        "life": {"fitness": 0.30, "activity": 0.5, "stress": 0.6},
                        "organs": {"heart": -0.10, "kidney": -0.10}},
}


def _apply_preset(body: Dict[str, Any], preset: str) -> None:
    spec = PRESETS.get(preset)
    if not spec:
        return
    if "age" in spec:
        body["age"] = spec["age"]
        body["organs"] = {k: organ_baseline(k, body["age"]) for k in ORGANS}
    if "bmi_shift" in spec:
        body["organs"]["fat"] = max(0.5, body["organs"]["fat"]
                                    + spec["bmi_shift"] / 22.5)
    for o, d in (spec.get("organs") or {}).items():
        if o in body["organs"]:
            if o == "fat":
                body["organs"][o] = max(0.3, body["organs"][o] + d)
            else:
                body["organs"][o] = max(0.10, min(1.10, body["organs"][o] + d))
    for k, v in (spec.get("life") or {}).items():
        if k in body["life"]:
            body["life"][k] = float(v)
    # 体脂设定点跟着预设走：运动员本来就该瘦，肥胖者本来就该重。
    # 没有这一项时，设定点回归会把所有预设的体型在一年内拉平到同一个数。
    body["fat_set"] = max(0.55, min(1.70, float(body["organs"].get("fat", 1.0))))
    body["preset"] = preset


# ----------------------------------------------------------------------
# 存取与兼容
# ----------------------------------------------------------------------
def ensure_body(raw: Optional[Dict[str, Any]], *, sex: str = "m",
                age: float = 30.0) -> Dict[str, Any]:
    """把旧存档/残缺结构补齐成完整 body。"""
    if not raw:
        return new_body(sex=sex, age=age)
    b = raw
    b.setdefault("v", 1)
    b.setdefault("seed", 20261030)
    b.setdefault("sex", sex)
    b.setdefault("age", age)
    b.setdefault("height", 172.0 if b["sex"] == "m" else 160.0)
    b.setdefault("clock", 0.0)
    b.setdefault("tick", 0)
    b.setdefault("preset", "healthy")
    b.setdefault("fat_set", max(0.55, min(1.70, float((b.get("organs") or {}).get("fat", 1.0)))))
    organs = b.get("organs") or {}
    for k in ORGANS:
        organs.setdefault(k, organ_baseline(k, b["age"]))
    b["organs"] = organs
    for field, default in (("damage", {}), ("irreversible", {}),
                           ("life", {}), ("env", {}), ("labs", {}),
                           ("vitals", {}), ("derived", {}), ("flags", {})):
        cur = b.get(field) or {}
        base = healthy_life() if field == "life" else (
            healthy_env() if field == "env" else (
                {k: 0.0 for k in ORGANS} if field in ("damage", "irreversible") else {}))
        for k, v in base.items():
            cur.setdefault(k, v)
        b[field] = cur
    for field in ("conditions", "history", "meds", "log"):
        b.setdefault(field, [])
    b.setdefault("dead", False)
    return b


def rng_for(body: Dict[str, Any], salt: int = 0) -> random.Random:
    """按 (seed, tick) 定种子：同一存档重放得到同样的病程。"""
    return random.Random(int(body.get("seed", 0)) ^ (int(body.get("tick", 0)) * 2654435761) ^ salt)


def alive_conditions(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for c in body.get("conditions") or []:
        if float(c.get("sev", 0.0)) > 0.02:
            out.append(c)
    return out


def condition_codes(body: Dict[str, Any]) -> List[str]:
    return [c["code"] for c in alive_conditions(body)]


def organ(body: Dict[str, Any], name: str) -> float:
    return float((body.get("organs") or {}).get(name, 1.0))


def life(body: Dict[str, Any], name: str) -> float:
    return float((body.get("life") or {}).get(name, 0.0))


def env(body: Dict[str, Any], name: str) -> float:
    return float((body.get("env") or {}).get(name, 0.0))


def locked(body: Dict[str, Any], name: str) -> bool:
    """该生活维度是否被用户钉住。

    睡眠、三餐、运动每小时都会把 sleep_h / salt / sugar / activity 往自己的
    目标拉，`/心理 设置 sleep_h 4` 第二天就被改回 7.5。钉住之后自动逻辑让位，
    值由用户说了算，直到用同样的命令设回 auto。
    """
    return bool((body.get("life_lock") or {}).get(name))


def bmi(body: Dict[str, Any]) -> float:
    h = float(body.get("height", 172.0)) / 100.0
    w = float((body.get("vitals") or {}).get("WEIGHT")
              or 22.5 * h * h)
    return w / (h * h) if h > 0 else 22.0


def hour_of_day(body: Dict[str, Any]) -> float:
    return float(body.get("clock", 0.0)) % 24.0


def day_index(body: Dict[str, Any]) -> int:
    return int(float(body.get("clock", 0.0)) // 24.0)


def push_log(body: Dict[str, Any], text: str, kind: str = "life") -> None:
    clock = float(body.get("clock", 0.0))
    body.setdefault("log", []).append({
        "h": round(clock, 1),
        "d": int(clock // 24) + 1,
        "kind": kind,
        "text": text,
    })
    if len(body["log"]) > 60:
        del body["log"][:-60]


def add_condition(body: Dict[str, Any], code: str, zh: str, *,
                  sev: float = 0.25, note: str = "") -> Dict[str, Any]:
    for c in body.get("conditions") or []:
        if c["code"] == code:
            c["sev"] = max(float(c["sev"]), sev)
            c["recur"] = int(c.get("recur", 0)) + 1
            return c
    item = {
        "code": code, "zh": zh,
        "onset": round(float(body.get("clock", 0.0)), 1),
        "sev": float(sev), "peak": float(sev),
        "stage": 0, "treated": False, "note": note, "recur": 0,
    }
    body.setdefault("conditions", []).append(item)
    body.setdefault("conditions", []).sort(key=lambda c: -float(c["sev"]))
    return item


def remove_condition(body: Dict[str, Any], code: str) -> None:
    conds = body.get("conditions") or []
    keep = []
    for c in conds:
        if c["code"] == code:
            h = dict(c)
            h["resolved"] = round(float(body.get("clock", 0.0)), 1)
            body.setdefault("history", []).append(h)
        else:
            keep.append(c)
    body["conditions"] = keep


def summary_line(body: Dict[str, Any]) -> str:
    d = int(float(body.get("clock", 0.0)) // 24)
    hh = hour_of_day(body)
    codes = [c.get("zh", c["code"]) for c in alive_conditions(body)]
    if codes:
        top = codes[:4]
        s = "、".join(top) + (f" 等 {len(codes)} 项" if len(codes) > 4 else "")
    else:
        s = "无活动性疾病"
    return (f"第 {d + 1} 天 {int(hh):02d}:{int((hh % 1) * 60):02d}｜"
            f"{SEX_ZH.get(body.get('sex', 'm'), '男')} {body.get('age', 30):.0f} 岁｜{s}")


def to_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    """序列化：去掉体积大的逐小时日志细节，保留可读事件。"""
    out = dict(body)
    out["log"] = (body.get("log") or [])[-20:]
    return out
