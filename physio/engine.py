"""生理动力学：让身体在时间里自己走。

一轮对话推进 hours_per_turn 小时（默认 6，即 4 轮＝1 天）。推进过程按小时
迭代，因为吃饭、睡觉、通勤暴露都发生在小时尺度上；疾病发生按天抽签，
器官损伤按小时累积。

四层结构：
  1) 生活层  —— 吃什么、睡多久、动不动、在什么环境里：影响体重、营养、体能、暴露
  2) 疾病层  —— 由风险算日发病概率；已有疾病按病程演进，治疗则缓解
  3) 器官层  —— 疾病对器官的损伤累积，部分不可逆（纤维化/坏死）
  4) 指标层  —— 由上述三层推导出化验单与生命体征（labs.py）

安全边界（有意为之）：
  · 不输出任何预后、生存期、死亡率数字；
  · 默认不模拟死亡，只模拟"危重"，避免把角色扮演变成骇人内容；
  · 药物剂量只作为相对强度使用，不出现在任何面向用户的文本里。
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Tuple

from . import body as B
from . import labs as L
from .const import ENV, LIFE, ORGANS
from .diseases import DISEASES
from .drugs import DRUGS

# 一年 365 天，1 天 24 小时
DAY = 24.0


class Physiology:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        self.cfg = cfg or {}
        self.hours_per_turn = float(self.cfg.get("physio_hours_per_turn", 6.0))
        self.enable_onset = bool(self.cfg.get("physio_disease_onset", True))
        self.enable_mortality = bool(self.cfg.get("physio_mortality", False))
        self.onset_scale = float(self.cfg.get("physio_onset_scale", 0.30))
        self.verbose = bool(self.cfg.get("physio_verbose", False))

    # ==================================================================
    # 对外入口
    # ==================================================================
    def step(self, body: Dict[str, Any], hours: Optional[float] = None) -> Dict[str, Any]:
        """推进一段时间，返回这段时间发生的事。"""
        body = B.ensure_body(body)
        if body.get("dead"):
            return {"events": [], "dead": True}
        hours = float(self.hours_per_turn if hours is None else hours)
        hours = max(0.0, min(24.0 * 14, hours))
        events: List[str] = []

        remaining = hours
        while remaining > 1e-6:
            chunk = min(1.0, remaining)
            remaining -= chunk
            self._advance_hour(body, chunk, events)

        self._organs(body, hours)
        self._conditions(body, hours, events)
        if self.enable_onset:
            self._onset(body, hours, events)
        self._refresh(body)
        return {"events": events, "dead": bool(body.get("dead"))}

    def add_med(self, body: Dict[str, Any], name: str, dose: float = 1.0) -> str:
        drug = name if name in DRUGS else None
        if not drug:
            return f"未知药物：{name}"
        body = B.ensure_body(body)
        body.setdefault("meds", []).append({
            "name": drug, "start_h": float(body.get("clock", 0.0)),
            "dose": float(dose),
        })
        B.push_log(body, f"开始服用{drug}", "med")
        return f"已开始服用{drug}（{DRUGS[drug]['cls']}），按常规剂量起效需要一到两天。"

    def remove_med(self, body: Dict[str, Any], name: str) -> str:
        body = B.ensure_body(body)
        before = len(body.get("meds") or [])
        body["meds"] = [m for m in body.get("meds") or [] if m.get("name") != name]
        if len(body["meds"]) == before:
            return f"未在服用 {name}。"
        B.push_log(body, f"停用{name}", "med")
        return f"已停用 {name}。"

    # ==================================================================
    # 1. 生活层
    # ==================================================================
    def _advance_hour(self, body: Dict[str, Any], dt: float,
                      events: List[str]) -> None:
        clock = float(body.get("clock", 0.0)) + dt
        body["clock"] = clock
        body["tick"] = int(body.get("tick", 0)) + 1
        h = clock % 24.0
        rng = B.rng_for(body, salt=7)

        # 跨日结算：热量收支 → 体脂。按天算而不是按轮，才不会一顿饭改一次体重
        if int(clock // 24) != int((clock - dt) // 24):
            self._daily_balance(body, events)

        self._env_tick(body, dt, rng)
        self._meals(body, h, rng, events)
        self._sleep(body, h, dt, rng, events)
        self._exercise(body, h, dt, rng, events)
        self._substance(body, h, dt, rng)
        self._hydration(body, dt, rng)
        self._stress_tick(body, dt, rng)

    def _env_tick(self, body: Dict[str, Any], dt: float, rng: random.Random) -> None:
        e = body["env"]
        # 季节温度与空气质量的慢漂移
        day = float(body.get("clock", 0.0)) / DAY
        season = math.sin(2 * math.pi * (day - 80) / 365.0)
        e["temp_c"] = 22.0 + 11.0 * season
        e["humidity"] = max(20.0, min(95.0, 55.0 + 18.0 * season
                                     + rng.uniform(-6, 6)))
        base_pm = 22.0 + 12.0 * (1.0 - season)
        e["pm25"] = max(3.0, e.get("pm25", base_pm) * 0.92 + base_pm * 0.08
                        + rng.uniform(-4, 4))
        # 病原与过敏原：冬春呼吸道病原高，花粉季过敏原高
        path_base = 0.12 + 0.10 * (1.0 - season)
        e["pathogen"] = max(0.0, min(1.0, e.get("pathogen", path_base) * 0.9
                                     + path_base * 0.1 + rng.uniform(-0.02, 0.02)))
        all_base = 0.08 + 0.18 * max(0.0, math.sin(2 * math.pi * (day - 100) / 365.0))
        e["allergen"] = max(0.0, min(1.0, e.get("allergen", all_base) * 0.93
                                     + all_base * 0.07 + rng.uniform(-0.02, 0.02)))

    def _meals(self, body: Dict[str, Any], h: float, rng: random.Random,
               events: List[str]) -> None:
        life = body["life"]
        # 三餐窗口
        meals = ((7.0, 9.0, 0.30, "早餐"), (11.5, 13.5, 0.40, "午餐"),
                 (17.5, 20.0, 0.35, "晚餐"))
        day = int(float(body.get("clock", 0.0)) // 24)
        done = body.setdefault("_meals_done", {})
        for lo, hi, share, name in meals:
            if not (lo <= h < hi):
                continue
            key = f"{day}-{name}"
            if key in done:
                continue
            done[key] = 1
            if len(done) > 12:
                for k in list(done)[:-6]:
                    done.pop(k, None)
            if rng.random() > 0.06:  # 大多数时候按时吃
                need_now = 2000.0 * (0.80 + 0.40 * float(life.get("fitness", 0.5)))
                kcal = share * need_now * float(life.get("kcal", 1.0))
                # 加工食品倾向：压力大、久坐、睡得少的人更常吃高盐高糖
                junk = min(1.0, 0.25
                           + 0.25 * max(0.0, float(life.get("stress", 0.3)) - 0.4)
                           + 0.20 * max(0.0, float(life.get("sleep_debt", 0.0)) / 20.0)
                           + 0.15 * max(0.0, float(life.get("sedentary", 6.0)) - 8.0) / 8.0)
                life["salt"] = life.get("salt", 1.0) * 0.94 + (1.0 + 0.45 * junk) * 0.06
                life["sugar"] = life.get("sugar", 1.0) * 0.94 + (1.0 + 0.6 * junk) * 0.06
                life["satfat"] = life.get("satfat", 1.0) * 0.94 + (1.0 + 0.4 * junk) * 0.06
                life["fiber"] = max(0.2, life.get("fiber", 0.7) * 0.98
                                    + 0.02 * (0.9 - 0.5 * junk))
                life["protein"] = max(0.3, min(1.2, life.get("protein", 0.85) * 0.98
                                                + 0.02 * 0.95))
                body["_kcal_today"] = float(body.get("_kcal_today", 0.0)) + kcal
            else:
                if name == "早餐":
                    events.append("skip_breakfast")

    def _sleep(self, body: Dict[str, Any], h: float, dt: float,
               rng: random.Random, events: List[str]) -> None:
        life = body["life"]
        night = (h >= 23.0 or h < 7.0)
        if not night:
            return
        # 睡眠债与压力决定实际入睡与时长
        debt = float(life.get("sleep_debt", 0.0))
        stress = float(life.get("stress", 0.3))
        target = 7.5 + 0.04 * debt
        target -= 1.4 * max(0.0, stress - 0.5)
        target = max(4.0, min(9.5, target))
        p_sleep = 0.92 - 0.35 * max(0.0, stress - 0.6)
        if rng.random() < p_sleep:
            life["sleep_h"] = float(life.get("sleep_h", 7.5)) * 0.9 + target * 0.1
            life["sleep_debt"] = max(0.0, debt - 0.20)
            life["sleep_qual"] = min(1.0, max(0.15,
                float(life.get("sleep_qual", 0.8)) * 0.95
                + 0.05 * (1.0 - stress) * 0.9))
        else:
            life["sleep_debt"] = min(60.0, debt + 1.0)
            life["sleep_qual"] = max(0.10, float(life.get("sleep_qual", 0.8)) - 0.03)

    def _exercise(self, body: Dict[str, Any], h: float, dt: float,
                  rng: random.Random, events: List[str]) -> None:
        life = body["life"]
        if not (16.0 <= h < 20.0):
            return
        base_p = 0.06 + 0.45 * min(1.0, float(life.get("activity", 1.0)) / 2.0)
        base_p -= 0.25 * max(0.0, float(life.get("sleep_debt", 0.0)) / 20.0)
        base_p -= 0.20 * max(0.0, float(life.get("stress", 0.3)) - 0.7)
        base_p = max(0.01, min(0.9, base_p))
        if rng.random() > base_p:
            return
        intensity = 0.4 + 0.5 * min(1.0, float(life.get("fitness", 0.5)))
        life["fitness"] = min(1.0, float(life.get("fitness", 0.5)) + 0.004 * intensity)
        life["sleep_debt"] = max(0.0, float(life.get("sleep_debt", 0.0)) - 0.05)
        body["organs"]["muscle"] = min(1.10, body["organs"].get("muscle", 1.0) + 0.002)
        body["organs"]["heart"] = min(1.10, body["organs"].get("heart", 1.0) + 0.001)
        body["organs"]["fat"] = max(0.55, body["organs"].get("fat", 1.0) - 0.0004)
        events.append("exercise")
        # 运动损伤
        p_inj = 0.010 * intensity * (1.0 + 0.6 * max(0.0, 30.0 - float(body.get("age", 30))) / 30.0)
        if rng.random() < p_inj:
            self._injure(body, rng, events)

    def _injure(self, body: Dict[str, Any], rng: random.Random,
                events: List[str]) -> None:
        kind = rng.choice(["ankle", "knee", "back", "muscle"])
        zh = {"ankle": "踝关节扭伤", "knee": "膝关节扭伤",
              "back": "腰肌拉伤", "muscle": "肌肉拉伤"}[kind]
        body["organs"]["muscle"] = max(0.5, body["organs"].get("muscle", 1.0) - 0.01)
        body["organs"]["joint"] = max(0.4, body["organs"].get("joint", 1.0) - 0.005)
        body["flags"]["injury"] = zh
        body["flags"]["injury_until"] = float(body.get("clock", 0.0)) + 240.0
        B.push_log(body, f"运动时{zh}", "injury")
        events.append(f"injury:{zh}")

    def _substance(self, body: Dict[str, Any], h: float, dt: float,
                   rng: random.Random) -> None:
        life = body["life"]
        smoke = float(life.get("smoking", 0.0))
        if smoke > 0 and 7 <= h < 23:
            # 每支烟约使当日暴露上升
            life["smoking"] = smoke
        alc = float(life.get("alcohol", 0.0))
        if alc > 0 and 19 <= h < 24:
            body["organs"]["liver"] = max(0.2, body["organs"].get("liver", 1.0) - 0.0015 * alc)

    def _hydration(self, body: Dict[str, Any], dt: float, rng: random.Random) -> None:
        life = body["life"]
        # 出汗与环境温度影响水合
        temp = B.env(body, "temp_c")
        loss = 0.03 + max(0.0, temp - 26.0) * 0.004
        water = float(life.get("water", 0.85)) - loss * 0.02
        # 进食与饮水补充
        intake = 0.02 if (7 <= B.hour_of_day(body) < 22) else 0.005
        life["water"] = max(0.15, min(1.0, water + intake))

    def _stress_tick(self, body: Dict[str, Any], dt: float, rng: random.Random) -> None:
        life = body["life"]
        # 压力缓慢回归基线，睡眠不足与疾病会把它推高
        target = 0.30 + 0.45 * min(1.0, float(life.get("sleep_debt", 0.0)) / 24.0)
        target += 0.25 * min(1.0, L.dysfunction_score(body))
        life["stress"] = float(life.get("stress", 0.3)) * 0.995 + target * 0.005

    # ==================================================================
    # 2. 器官层
    # ==================================================================
    def _organs(self, body: Dict[str, Any], hours: float) -> None:
        impair: Dict[str, float] = {k: 0.0 for k in ORGANS}
        for c in B.alive_conditions(body):
            spec = DISEASES.get(c["code"])
            if not spec:
                continue
            sev = float(c.get("sev", 0.0))
            ctrl = 1.0 - 0.5 * float(c.get("treat_effect", 0.0))
            for o, k in (spec["org"] or {}).items():
                if o in impair:
                    impair[o] = min(0.80, impair[o] + abs(k) * sev * ctrl)

        # 生活方式对器官的慢性影响
        life = body["life"]
        impair["liver"] = min(0.95, impair["liver"]
                              + 0.004 * max(0.0, float(life.get("alcohol", 0)) - 1.0))
        impair["lungs"] = min(0.95, impair["lungs"]
                              + 0.0015 * float(life.get("smoking", 0)))
        impair["vessels"] = min(0.95, impair["vessels"]
                                + 0.0004 * float(life.get("smoking", 0))
                                + 0.0002 * max(0.0, B.bmi(body) - 26.0))
        impair["fat_sens"] = min(0.9, impair["fat_sens"]
                                 + 0.0006 * max(0.0, B.bmi(body) - 25.0))

        for o, fn in list(body["organs"].items()):
            base = B.organ_baseline(o, float(body.get("age", 30.0)))
            if o == "fat":
                continue
            if o == "fat_sens":
                body["organs"][o] = max(0.20, min(1.15, fn))
                continue
            target = base * (1.0 - impair.get(o, 0.0))
            dmg = float(body["damage"].get(o, 0.0))
            if impair.get(o, 0.0) > 0.02:
                # 损伤累积：器官越脆弱，同样的打击留下越多痕迹
                # 2400 小时 ≈ 100 天持续损伤才累到 1.0，避免一次感冒就伤到器官
                dmg += impair[o] * hours / 2400.0
            else:
                dmg -= hours / max(24.0, ORGANS[o][2])
            dmg = max(0.0, min(0.95, dmg))
            body["damage"][o] = dmg

            # 不可逆部分：纤维化、坏死，只增不减
            irr = float(body["irreversible"].get(o, 0.0))
            irr = min(0.85, irr + max(0.0, dmg - irr) * hours / 7200.0)
            body["irreversible"][o] = irr

            fn_new = base * (1.0 - max(dmg, irr))
            # 向目标缓慢逼近，避免器官值跳变
            body["organs"][o] = max(0.05, min(1.15, fn + (fn_new - fn) * min(1.0, hours / 48.0)))



    def _daily_balance(self, body: Dict[str, Any], events: List[str]) -> None:
        """一天结束时的热量收支结算。7700 kcal ≈ 1 kg 脂肪。"""
        intake = float(body.pop("_kcal_today", 0.0))
        if intake <= 0:
            return
        life = body["life"]
        need = 2000.0 * (0.80 + 0.40 * float(life.get("fitness", 0.5)))
        need *= 1.0 + 0.15 * max(0.0, B.bmi(body) - 25.0)
        surplus = intake - need
        fat = float(body["organs"].get("fat", 1.0))
        # 1 个脂肪单位≈15 kg 体重，换算成体脂单位
        delta = surplus / 7700.0 / 15.0
        # 设定点回归：身体对"掉体重"的抵抗强于对"长体重"的抵抗，这是真实现象。
        # 设定点本身由预设决定（运动员本来就瘦、肥胖者本来就重），
        # 长期的热量赤字/盈余会把它缓慢挪动——但一天不会。
        setp = float(body.get("fat_set", 1.0))
        delta += (setp - fat) * (0.0060 if fat < setp else 0.0012)
        body["organs"]["fat"] = max(0.30, min(1.8, fat + delta))
        # 饮食习惯是慢变量：偶尔少吃一顿不该改变"平时的食量"。
        # 用连续赤字/盈余天数做迟滞，避免一顿没吃就把人设改成节食者。
        deficit = int(body.get("_deficit_days", 0))
        surplus_days = int(body.get("_surplus_days", 0))
        if intake < need * 0.75:
            deficit += 1
            surplus_days = 0
            events.append("underate")
        elif intake > need * 1.30:
            surplus_days += 1
            deficit = 0
            events.append("overate")
        else:
            deficit = max(0, deficit - 1)
            surplus_days = max(0, surplus_days - 1)
        if deficit >= 4:
            life["kcal"] = max(0.45, float(life.get("kcal", 1.0)) * 0.98)
            deficit = 0
        if surplus_days >= 10:
            life["kcal"] = min(1.6, float(life.get("kcal", 1.0)) * 1.01)
            surplus_days = 0
        # 设定点随长期收支缓慢漂移：连续赤字把身体"重新校准"得轻一些，
        # 连续盈余则相反。每月最多几个百分点，不会一次吃多就改体重。
        body["fat_set"] = max(0.55, min(1.70, setp + delta * 0.25))
        body["_deficit_days"] = deficit
        body["_surplus_days"] = surplus_days

    # ==================================================================
    # 3. 疾病层
    # ==================================================================
    def _risk_factor(self, body: Dict[str, Any], key: str) -> float:
        """把风险因子名映射成 0..1+ 的强度。未知因子按 0 处理。"""
        life = body["life"]
        e = body["env"]
        age = float(body.get("age", 30.0))
        bmi = B.bmi(body)
        vit = body.get("vitals") or {}
        lb = body.get("labs") or {}
        m = {
            "age": min(1.0, max(0.0, (age - 35.0) / 45.0)),
            "bmi": min(1.0, max(0.0, (bmi - 24.0) / 12.0)),
            "smoking": min(1.0, float(life.get("smoking", 0)) / 20.0),
            "alcohol": min(1.0, float(life.get("alcohol", 0)) / 4.0),
            "stress": min(1.0, float(life.get("stress", 0.3))),
            "fitness": min(1.0, max(0.0, 1.0 - float(life.get("fitness", 0.5)) * 2.0)),
            "sedentary": min(1.0, max(0.0, (float(life.get("sedentary", 6)) - 6.0) / 8.0)),
            "sleep_debt": min(1.0, float(life.get("sleep_debt", 0)) / 24.0),
            "water": min(1.0, max(0.0, 1.0 - float(life.get("water", 0.85)))),
            "iron": min(1.0, max(0.0, 1.0 - float(life.get("iron", 0.85)))),
            "b12": min(1.0, max(0.0, 1.0 - float(life.get("b12", 0.85)))),
            "folate": min(1.0, max(0.0, 1.0 - float(life.get("folate", 0.85)))),
            "vitd": min(1.0, max(0.0, 1.0 - float(life.get("vitd", 0.65)))),
            "sun": min(1.0, max(0.0, 1.0 - float(life.get("sun", 20)) / 40.0)),
            "fiber": min(1.0, max(0.0, 1.0 - float(life.get("fiber", 0.7)))),
            "salt": min(1.0, max(0.0, float(life.get("salt", 1.0)) - 1.0)),
            "sugar": min(1.0, max(0.0, float(life.get("sugar", 1.0)) - 1.0)),
            "satfat": min(1.0, max(0.0, float(life.get("satfat", 1.0)) - 1.0)),
            "protein": min(1.0, max(0.0, 1.0 - float(life.get("protein", 0.85)))),
            "pathogen": min(1.0, float(e.get("pathogen", 0.15))),
            "allergen": min(1.0, float(e.get("allergen", 0.1))),
            "pm25": min(1.0, float(e.get("pm25", 25)) / 120.0),
            "noise": min(1.0, max(0.0, (float(e.get("noise", 45)) - 50.0) / 40.0)),
            "humidity": min(1.0, max(0.0, (float(e.get("humidity", 55)) - 60.0) / 35.0)),
            "immune": min(1.0, max(0.0, 1.0 - B.organ(body, "immune")) * 3.0),
            "coag": min(1.0, max(0.0, 1.0 - B.organ(body, "coag")) * 3.0),
            "bone": min(1.0, max(0.0, 1.0 - B.organ(body, "bone")) * 3.0),
            "HGB": min(1.0, max(0.0, 1.0 - float(lb.get("HGB", 140.0)) / 130.0)),
            "LDL": min(1.0, max(0.0, (float(lb.get("LDL", 2.4)) - 3.4) / 2.0)),
            "TG": min(1.0, max(0.0, (float(lb.get("TG", 1.1)) - 1.7) / 3.0)),
            "UA": min(1.0, max(0.0, (float(lb.get("UA", 330)) - 420) / 200.0)),
            "SBP": min(1.0, max(0.0, (float(vit.get("SBP", 115)) - 130) / 40.0)),
            "sex": 0.5,
            "hygiene": min(1.0, max(0.0, 1.0 - float(life.get("hygiene", 0.85)))),
        }
        return m.get(key, 0.0)

    def _onset(self, body: Dict[str, Any], hours: float,
               events: List[str]) -> None:
        if hours <= 0:
            return
        days = hours / DAY
        rng = B.rng_for(body, salt=13)
        # 已有较多慢病时不再继续抽新的，避免"病越攒越多"失真
        chronic_n = sum(1 for c in (body.get("conditions") or [])
                        if not (DISEASES.get(c["code"]) or {}).get("acute"))
        allow_chronic = chronic_n < 6
        immunity = max(0.35, B.organ(body, "immune"))
        for code, spec in DISEASES.items():
            if spec.get("sex") and spec["sex"] != body.get("sex", "m"):
                continue
            ar = spec.get("age")
            age = float(body.get("age", 30.0))
            if ar and not (ar[0] <= age <= ar[1]):
                continue
            # 已有该病则不再重复抽
            if any(c["code"] == code for c in body.get("conditions") or []):
                continue
            is_acute = bool(spec.get("acute"))
            if not is_acute and not allow_chronic:
                continue
            # 急症 base = 日概率；慢病 base = 月概率。同一套数字在两种尺度上才都合理
            window = days if is_acute else days / 30.0
            base = float(spec["base"]) * self.onset_scale
            mult = 1.0
            for rf, w in (spec.get("risk") or {}).items():
                mult *= 1.0 + w * self._risk_factor(body, rf)
            # 免疫低时感染类风险上升
            if spec["sys"] in ("resp", "gi", "derm") and "pathogen" in (spec.get("risk") or {}):
                mult *= 1.0 + 0.8 * (1.0 - immunity)
            p = 1.0 - math.exp(-base * mult * window)
            if rng.random() < p:
                item = B.add_condition(body, code, spec["zh"], sev=0.06, note=spec["note"])
                item["treat_effect"] = 0.0
                B.push_log(body, f"出现{spec['zh']}的早期迹象", "onset")
                events.append(f"onset:{spec['zh']}")

    def _conditions(self, body: Dict[str, Any], hours: float,
                    events: List[str]) -> None:
        clock = float(body.get("clock", 0.0))
        for c in list(body.get("conditions") or []):
            spec = DISEASES.get(c["code"])
            if not spec:
                B.remove_condition(body, c["code"])
                continue
            sev = float(c.get("sev", 0.0))

            # 治疗效应：有对症药物在服则逐步上升
            te = 0.0
            for m in body.get("meds") or []:
                d = DRUGS.get(m.get("name", ""))
                if not d or c["code"] not in d["ind"]:
                    continue
                on = clock - float(m.get("start_h", clock))
                if on <= 0:
                    continue
                te = max(te, (1.0 - math.exp(-on / 36.0)) * min(1.0, float(m.get("dose", 1.0))))
            c["treat_effect"] = te
            c["treated"] = te > 0.35

            acute = bool(spec.get("acute"))
            dur = spec.get("dur")
            elapsed = clock - float(c.get("onset", clock))

            if acute:
                # 急症走「上升 → 平台 → 消退」三段，不能一边长一边掉：
                # 那样会停在两者相抵的点上，病就永远好不了。
                total = float(dur or 240.0)
                peak_at = total * 0.35
                if elapsed < peak_at:
                    grow_tau = max(2.0, peak_at * 0.45)
                    sev += (0.85 - sev) * (1.0 - math.exp(-hours / grow_tau))
                elif elapsed < total:
                    # 平台期：维持，缓慢下滑
                    sev -= sev * (1.0 - math.exp(-hours / (total * 1.4)))
                else:
                    # 消退期：指数衰减，越过自限期后必然归零
                    sev *= math.exp(-hours / max(12.0, total * 0.22))
            else:
                grow_tau = DAY * 75.0
                target = 0.55 if not c.get("treated") else 0.28
                sev += (target - sev) * (1.0 - math.exp(-hours / grow_tau))

            # 治疗把严重度往下压（急慢性都适用）
            if te > 0.05:
                sev -= sev * te * (1.0 - math.exp(-hours / (DAY * 5.0)))
            sev = max(0.0, min(1.0, sev))
            c["sev"] = sev
            c["peak"] = max(float(c.get("peak", sev)), sev)

            # 危重：不是死亡，而是"需要立即处理"的状态
            if spec.get("mortal", 0.0) > 0.004 and sev > 0.75 and te < 0.2:
                if not (body.get("flags") or {}).get("critical"):
                    body["flags"]["critical"] = True
                    body["flags"]["critical_cause"] = spec["zh"]
                    B.push_log(body, f"{spec['zh']}发展到危重状态", "critical")
                    events.append("critical")

            expired = acute and dur and elapsed > float(dur) * 1.3
            if sev <= 0.03 or (expired and sev < 0.12):
                B.remove_condition(body, c["code"])
                B.push_log(body, f"{spec['zh']}已恢复", "resolve")
                events.append(f"resolve:{spec['zh']}")

    # ==================================================================
    # 4. 指标层
    # ==================================================================
    def refresh(self, body: Dict[str, Any]) -> None:
        """只重算指标，不推进时间。

        新建或读取的身体还没有任何一次 step，labs/vitals 是空的；此时查体检会
        得到体重 0、体征"未记录"。凡是要读指标的地方先调这里补算一次。
        """
        self._refresh(B.ensure_body(body))

    def _refresh(self, body: Dict[str, Any]) -> None:
        labs, vitals, derived = L.compute(body)
        body["labs"] = {k: round(v, 3) for k, v in labs.items()}
        body["vitals"] = {k: round(v, 2) for k, v in vitals.items()}
        body["derived"] = {
            "inflammation": round(derived.get("inflammation", 0.0), 3),
            "pain": round(derived.get("pain_drive", 0.0), 3),
            "fever": round(derived.get("fever_drive", 0.0), 3),
            "dysfunction": round(derived.get("dysfunction", 0.0), 3),
            "drug_load": round(derived.get("drug_load", 0.0), 3),
            "drug_notes": derived.get("drug_notes", []),
            "abnormal": derived.get("abnormal", []),
            "symptoms": derived.get("symptoms", []),
            "organ_failure": derived.get("organ_failure", []),
        }
        # 危重标记随病情缓解而解除
        if (body.get("flags") or {}).get("critical"):
            worst = max([float(c.get("sev", 0)) for c in B.alive_conditions(body)] or [0])
            if worst < 0.35:
                body["flags"]["critical"] = False
                body["flags"].pop("critical_cause", None)
        # 损伤标记到期
        inv = (body.get("flags") or {}).get("injury_until")
        if inv and float(body.get("clock", 0)) > float(inv):
            body["flags"].pop("injury", None)
            body["flags"].pop("injury_until", None)

    # ==================================================================
    # 与精神模块的耦合
    # ==================================================================
    def couple(self, body: Dict[str, Any], st) -> None:
        """把身体状态写回精神模块的几个共享量。

        宁可少耦合：只动炎症、皮质醇、甲状腺素与睡眠压力这四个有明确通路、
        且在两边都有对应键的量。别的都留在各自模块里，避免调一处坏两处。
        """
        d = body.get("derived") or {}
        inflam = float(d.get("inflammation", 0.0))
        fever = float(d.get("fever", 0.0))
        pain = float(d.get("pain", 0.0))
        dys = float(d.get("dysfunction", 0.0))
        if inflam > 0:
            st.bio["il6"] = min(1.0, st.bio.get("il6", 0.2) + 0.35 * inflam)
        if fever > 0.2 or pain > 0.3:
            st.bio["cortisol"] = min(1.0, st.bio.get("cortisol", 0.35) + 0.12 * max(fever, pain))
            st.bio["norepinephrine"] = min(1.0, st.bio.get("norepinephrine", 0.45) + 0.10 * pain)
        if dys > 0.25:
            # 长期身体不适会拉低情绪与精力，这是真实的共病通路，不是"加成"
            st.bio["serotonin"] = max(0.05, st.bio.get("serotonin", 0.55) - 0.06 * dys)
            st.bio["bdnf"] = max(0.05, st.bio.get("bdnf", 0.5) - 0.05 * dys)
            st.neuro["sleep_pressure"] = min(1.0, st.neuro.get("sleep_pressure", 0.3) + 0.05 * dys)
        t3 = (body.get("labs") or {}).get("FT3")
        if t3 is not None:
            # 精神侧 t3 的常模是 0.50±0.10（无量纲），不能把化验值直接除个数就写进去。
            # 这里把「参考区间上下限」映射成 ±0.09，即 ±0.9σ：
            # 正常范围内只会轻微偏离，超出区间才逐步变大。
            half = 1.85  # (6.8 - 3.1) / 2
            dev = (float(t3) - 4.95) / half
            st.bio["t3"] = max(0.15, min(0.90, 0.50 + 0.09 * dev))
