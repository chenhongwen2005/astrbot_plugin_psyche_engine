"""动力学：把"一句话"演化为下一轮的生化 / 电生理 / 症状状态。

因果链（每轮一次）：
    外部刺激（appraisal）
      → 神经化学冲动（单胺、HPA、催产素、炎症）
      → 受体后环路活动（杏仁核、vmPFC、dlPFC、伏隔核、纹状体、岛叶）
      → 症状域（阳性/阴性/情感/焦虑/强迫/创伤/人格…）
      → 异稳态负荷累积 → 慢性化 → 症状地板

关键设计：
1. **时间常数分层**：相位性 DA 以轮计（τ≈2），5-HT 以十轮计（τ≈10），BDNF/甲状腺以几十轮计。
   这保证了"一句话能让你心跳加速，但不能让你痊愈"。
2. **HPA 三级瀑布**：CRH → ACTH → 皮质醇，逐级延迟，因此应激后的皮质醇高峰出现在 2~3 轮之后，
   而不是当场。
3. **异稳态负荷（allostatic load）**：长期高皮质醇/高唤醒会不可逆地抬高基线，压低 BDNF 与海马功能。
4. **症状地板**：进入慢性化后，症状存在下限，单靠谈话无法回到基线——这就是"病态不可聊天治愈"的数学实现。
"""

from __future__ import annotations

import math
import random
import time
from typing import Any, Dict, Optional

from . import pharm
from .const import BIO, NEURO
from .model import MindState

TAU_SYM = {
    "ps": 0.22, "ng": 0.09, "md": 0.10, "ma": 0.26, "ax": 0.24, "oc": 0.12,
    "tr": 0.18, "di": 0.20, "ea": 0.10, "so": 0.12, "su": 0.14, "ic": 0.20,
    "pd": 0.08, "nd": 0.05, "cg": 0.06, "sl": 0.25, "ot": 0.10,
}

# 域被社交刺激直接唤起的程度。妄想、幻觉、木僵、人格特质这些必须由病程形成，
# 不能被几句话点着——否则「被骂 30 轮」会长出紧张症与评论性幻听。
DOMAIN_ACUTE = {
    "ax": 1.00, "md": 0.85, "tr": 0.80, "ma": 0.70, "sl": 0.70,
    "so": 0.55, "su": 0.50, "oc": 0.35, "ea": 0.30, "ot": 0.30,
    "di": 0.25, "ic": 0.25, "pd": 0.20, "ps": 0.15, "ng": 0.15,
    "cg": 0.10, "nd": 0.08,
}


def _c(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def _defi(x: float, base: float) -> float:
    """相对基线的"不足"程度，0=不低于基线，1=归零。"""
    if base <= 1e-6:
        return 0.0
    return _c((base - x) / base)


def _high(x: float, base: float) -> float:
    return _c((x - base) / max(1e-6, 1.0 - base))


def _sig(x: float, mid: float = 0.5, k: float = 5.0) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-k * (x - mid)))
    except OverflowError:
        return 0.0 if x < mid else 1.0


class Dynamics:
    def __init__(self, cfg: Optional[Dict[str, Any]] = None):
        self.cfg = cfg or {}

    # ------------------------------------------------------------------
    def step(self, st: MindState, ap: Dict[str, Any]) -> Dict[str, Any]:
        st.tick()
        cfg = self.cfg
        dims = ap.get("dims") or {}
        domains = ap.get("domains") or {}

        self._circadian(st, cfg)
        self._relax_bio(st)
        self._impulse_bio(st, ap)
        self._apply_meds(st)
        self._hpa_cascade(st)
        self._therapy(st, ap, cfg)
        self._update_neuro(st, dims)
        self._update_symptoms(st, dims, domains, cfg)
        self._load_and_chronic(st, cfg)
        self._hot_symptoms(st, cfg)

        return {
            "turn": st.meta["turn"],
            "valence": ap.get("valence", 0.0),
            "keywords": ap.get("keywords", []),
        }

    # ------------------------------------------------------------------
    # 1. 昼夜节律
    # ------------------------------------------------------------------
    def _circadian(self, st: MindState, cfg: Dict[str, Any]) -> None:
        if not cfg.get("enable_circadian", True):
            return
        hour = cfg.get("hour")
        if hour is None:
            lt = time.localtime()
            hour = lt.tm_hour + lt.tm_min / 60.0
        # 皮质醇：8 点峰、20 点谷
        cort_phase = 0.5 + 0.5 * math.cos(2 * math.pi * (hour - 8.0) / 24.0)
        st.bio["cortisol"] = _c(st.bio["cortisol"] * (0.82 + 0.36 * cort_phase))
        # 褪黑素：3 点峰
        mel_phase = 0.5 + 0.5 * math.cos(2 * math.pi * (hour - 3.0) / 24.0)
        st.bio["melatonin"] = _c(0.10 + 0.72 * mel_phase)
        st.bio["orexin"] = _c(0.85 - 0.55 * mel_phase)
        # 腺苷：清醒时长累积（用轮数近似，每轮 +0.004）
        if 7 <= hour <= 23:
            st.bio["adenosine"] = _c(st.bio["adenosine"] + 0.0026)
        # 夜间单胺自然回落
        if hour < 6 or hour > 23:
            for k in ("serotonin", "norepinephrine", "da_tonic"):
                st.bio[k] = _c(st.bio[k] * 0.97)

    # ------------------------------------------------------------------
    # 2. 生化回稳（一阶弛豫到调定点）
    # ------------------------------------------------------------------
    def _relax_bio(self, st: MindState) -> None:
        al = float(st.meta.get("allostatic_load", 0.0))
        il6 = st.bio.get("il6", 0.2)
        # 慢性负荷与炎症对调定点的"下压"
        mods = {
            "serotonin": -0.10 * al - 0.30 * max(0.0, il6 - 0.25),
            "norepinephrine": +0.10 * al,
            "gaba": -0.12 * al,
            "bdnf": -0.40 * al,
            "t3": -0.20 * al,
            "cortisol": +0.22 * al,
            "hippocampus": 0.0,
            "oxytocin": -0.10 * al,
        }
        # 人格特质对基线的偏移
        tr = st.traits
        sp_map = st.meta.get("bio_setpoint") or {}
        mods["serotonin"] = mods.get("serotonin", 0.0) - 0.10 * tr.get("negative_affectivity", 0.35)
        mods["cortisol"] = mods.get("cortisol", 0.0) + 0.10 * tr.get("stress_vulnerability", 0.35)
        mods["gaba"] = mods.get("gaba", 0.0) - 0.06 * tr.get("negative_affectivity", 0.35)
        mods["da_tonic"] = mods.get("da_tonic", 0.0) + 0.10 * (tr.get("reward_sensitivity", 0.5) - 0.5)

        for k, (_, base, tau, _sd) in BIO.items():
            if k == "cortisol":
                continue  # 皮质醇由 HPA 瀑布单独管理（保留下丘脑个体基线）
            sp = sp_map.get(k)
            if sp is None:
                target = _c(base + mods.get(k, 0.0))
            else:
                # 个体调定点：由基因与病程决定，应激只是在其周围偏离。
                # 负荷/特质的修正在这里只取一半，因为它们的贡献已内含于病程。
                target = _c(sp + 0.55 * mods.get(k, 0.0))
            x = st.bio.get(k, base)
            x += (target - x) * min(0.95, 1.0 / max(0.8, tau))
            st.bio[k] = _c(x, 0.03, 1.0)

    # ------------------------------------------------------------------
    # 3. 刺激冲动
    # ------------------------------------------------------------------
    def _impulse_bio(self, st: MindState, ap: Dict[str, Any]) -> None:
        d = ap.get("dims") or {}
        inten = float(ap.get("intensity", 0.5) or 0.5)
        res = float(st.meta.get("resilience", 0.0))
        # 冲击增益：韧性高的人同一句话引起的内分泌偏移更小
        g = (0.55 + 0.9 * inten) * 0.60 * (1.0 - 0.45 * res)

        threat = d.get("threat", 0.0)
        rejection = d.get("rejection", 0.0)
        praise = d.get("praise", 0.0)
        control = d.get("control", 0.0)
        intimacy = d.get("intimacy", 0.0)
        chaos = d.get("chaos", 0.0)
        calm = d.get("calm", 0.0)
        help_ = d.get("help", 0.0)
        hostility = d.get("hostility", 0.0)
        farewell = d.get("farewell", 0.0)
        medical = d.get("medical", 0.0)

        # 负性维度必须饱和：威胁/拒绝/敌意可以同时高，但总和不能线性叠加，
        # 否则一句"滚开，你就是个废物"能让 neg 冲到 2.5，把递质一轮打到底。
        raw = threat + 0.85 * rejection + 0.85 * hostility + 0.55 * farewell * 0.6 + 0.5 * chaos
        neg = 1.0 - math.exp(-1.15 * raw)

        # 正性维度同样必须饱和，理由和负性完全一样。缺了这个饱和，calm/praise/
        # help/intimacy 会线性叠加：一句「我在这，别怕」能同时拿到四个正性维度，
        # 单轮就给 DA 加 0.12，超过弛豫每轮能回拉的 0.069（da_tonic τ=8）——
        # 稳态必然顶到 1.0，20 轮正常共情就能把人从抑郁推成躁狂。
        # 那是 SSRI 过量才会有的效应，不是陪伴。权重按「稳态不顶格」标定：
        # 稳态提升 = 权重 × pos / (1/τ)，取 da_tonic≈0.80、serotonin≈0.75。
        pos_raw = calm + 0.85 * praise + 0.60 * help_ + 0.50 * intimacy
        pos = 1.0 - math.exp(-0.85 * pos_raw)

        st.bio["da_tonic"] = _c(st.bio["da_tonic"] + g * (0.052 * pos - 0.07 * neg))
        st.bio["da_phasic"] = _c(st.bio["da_phasic"] + g * (0.32 * pos - 0.10 * rejection))
        st.bio["serotonin"] = _c(st.bio["serotonin"] + g * (-0.09 * neg + 0.033 * pos))
        st.bio["norepinephrine"] = _c(st.bio["norepinephrine"] + g * (0.16 * threat + 0.10 * control + 0.06 * chaos - 0.09 * calm - 0.04 * intimacy))
        st.bio["gaba"] = _c(st.bio["gaba"] + g * (0.06 * calm - 0.07 * threat - 0.04 * chaos))
        st.bio["crh"] = _c(st.bio["crh"] + g * (0.22 * threat + 0.14 * rejection - 0.08 * calm))
        st.bio["oxytocin"] = _c(st.bio["oxytocin"] + g * (0.18 * intimacy + 0.06 * praise - 0.12 * rejection - 0.05 * hostility))
        st.bio["endorphin"] = _c(st.bio["endorphin"] + g * (0.07 * intimacy - 0.06 * threat))
        st.bio["glutamate"] = _c(st.bio["glutamate"] + g * (0.06 * chaos + 0.05 * threat))
        st.bio["acetylcholine"] = _c(st.bio["acetylcholine"] + g * (0.04 * control + 0.03 * medical))
        st.bio["testosterone"] = _c(st.bio["testosterone"] + g * (0.06 * hostility - 0.02 * calm))
        st.bio["anandamide"] = _c(st.bio["anandamide"] + g * (0.04 * calm - 0.03 * threat))

        # 治疗相关话语轻微提升 BDNF（只在长期累积上有意义）
        if help_ > 0.2 or calm > 0.3:
            st.bio["bdnf"] = _c(st.bio["bdnf"] + 0.004 * (help_ + calm))

    # ------------------------------------------------------------------
    # 4. 药物
    # ------------------------------------------------------------------
    def _apply_meds(self, st: MindState) -> None:
        eff = pharm.active_effects(st.meta.get("meds") or [], int(st.meta.get("turn", 0)))
        for k, v in eff["bio"].items():
            if k in st.bio:
                st.bio[k] = _c(st.bio[k] + v)
        # 症状层效应挂到 meta，供 _update_symptoms 使用
        st.meta["_med_sym"] = eff["sym"]
        st.meta["_med_notes"] = eff["notes"]

    # ------------------------------------------------------------------
    # 5. HPA 三级瀑布（延迟 2~3 轮）
    # ------------------------------------------------------------------
    def _hpa_cascade(self, st: MindState) -> None:
        """HPA 三级瀑布。

        关键点：皮质醇按"个体基线 + 应激增量"演化，而不是被拉回一个全人群统一的绝对值，
        否则一个基线 0.66 的抑郁个体会在应激时反而"下降"到 0.37。
        """
        b = st.bio
        al = float(st.meta.get("allostatic_load", 0.0))

        # 个体皮质醇调定点：首次运行时锚定当前值，之后随异稳态负荷缓慢上移
        sp = float(st.meta.get("cort_setpoint", b["cortisol"]))
        sp += (0.35 + 0.22 * al - sp) * 0.010
        st.meta["cort_setpoint"] = _c(sp)

        acth_target = _c(0.15 + 0.75 * b["crh"])
        b["acth"] = _c(b["acth"] + (acth_target - b["acth"]) * 0.45)

        target = (
            sp
            + 0.45 * (b["acth"] - 0.32)
            + 0.20 * (b["norepinephrine"] - 0.45)
            - 0.10 * (b["gaba"] - 0.55)
            + 0.12 * max(0.0, b.get("il6", 0.2) - 0.25)
        )
        b["cortisol"] = _c(b["cortisol"] + (_c(target) - b["cortisol"]) * 0.28)

    # ------------------------------------------------------------------
    # 6. 谈话治疗效应（极弱，且被慢性化压制）
    # ------------------------------------------------------------------
    def _therapy(self, st: MindState, ap: Dict[str, Any], cfg: Dict[str, Any]) -> None:
        if not cfg.get("therapy_enabled", True):
            return
        d = ap.get("dims") or {}
        support = (
            0.55 * d.get("calm", 0.0) + 0.40 * d.get("praise", 0.0)
            + 0.35 * d.get("help", 0.0) + 0.30 * d.get("intimacy", 0.0)
            + 0.20 * d.get("medical", 0.0)
            - 0.50 * d.get("hostility", 0.0) - 0.30 * d.get("control", 0.0)
            - 0.40 * d.get("rejection", 0.0)
        )
        alliance = float(st.meta.get("alliance", 0.35))
        st.meta["alliance"] = _c(alliance + 0.035 * support * (1 - alliance) + 0.004 * max(0.0, support))

        if support <= 0:
            return

        chronic = float(st.meta.get("chronicity", 0.0))
        sev = float(st.meta.get("last_severity", 30.0))
        talkability = float(st.meta.get("last_talkability", 0.3))

        gain = (
            0.011 * support
            * (0.35 + 0.65 * st.meta["alliance"])
            * (max(0.06, 1.0 - 0.94 * chronic) ** 2)
            * talkability
            * max(0.15, 1 - sev / 130.0)
        )
        # 谈话只能轻微推动生化，不能直接抹掉症状
        st.bio["serotonin"] = _c(st.bio["serotonin"] + gain)
        st.bio["cortisol"] = _c(st.bio["cortisol"] - gain * 1.2)
        st.bio["bdnf"] = _c(st.bio["bdnf"] + gain * 0.6)
        st.bio["oxytocin"] = _c(st.bio["oxytocin"] + gain * 0.5)
        st.meta["therapy_accum"] = float(st.meta.get("therapy_accum", 0.0)) + support
        st.meta["positive_accum"] = float(st.meta.get("positive_accum", 0.0)) + support
        if support < 0:
            st.meta["negative_accum"] = float(st.meta.get("negative_accum", 0.0)) - support

        # 调定点的缓慢上修 —— 这是「聊天治不好、但能减轻」的唯一通路。
        # 直接加递质会被 _relax_bio 每轮抹掉，所以必须动 setpoint 本身；
        # 速率以百轮计，且被慢性化平方级压制。
        sp = st.meta.get("bio_setpoint") or {}
        if sp:
            bump = (0.0015 * support
                    * (0.40 + 0.60 * float(st.meta.get("alliance", 0.35)))
                    * max(0.04, 1.0 - 0.90 * chronic))
            for k, lim in (("serotonin", 0.55), ("bdnf", 0.50),
                           ("gaba", 0.58), ("oxytocin", 0.50)):
                cur_sp = sp.get(k)
                if cur_sp is not None and cur_sp < lim:
                    sp[k] = min(lim, cur_sp + bump * 0.6)

    # ------------------------------------------------------------------
    # 7. 环路活动
    # ------------------------------------------------------------------
    def _update_neuro(self, st: MindState, dims: Dict[str, float]) -> None:
        b = st.bio
        n = st.neuro
        al = float(st.meta.get("allostatic_load", 0.0))
        il6 = b.get("il6", 0.2)
        tr = st.traits
        sleep = n.get("sleep_pressure", 0.3)

        affect = float(st.meta.get("affect_balance", 0.0))
        delta = (
            (dims.get("praise", 0) + dims.get("calm", 0) + dims.get("intimacy", 0))
            - (dims.get("threat", 0) + dims.get("rejection", 0) + dims.get("hostility", 0))
        )
        affect = 0.75 * affect + 0.25 * delta
        st.meta["affect_balance"] = max(-1.0, min(1.0, affect))

        targets = {
            "amygdala": 0.10 + 0.55 * b["norepinephrine"] + 0.30 * b["cortisol"]
                        - 0.38 * b["gaba"] + 0.18 * tr.get("threat_sensitivity", 0.35),
            "vmpfc": 0.98 - 0.42 * b["cortisol"] - 0.38 * al - 0.18 * b["norepinephrine"]
                     + 0.14 * b["serotonin"],
            "dlpfc": 0.98 - 0.28 * b["cortisol"] - 0.35 * al - 0.22 * sleep
                     + 0.12 * b["da_tonic"] - 0.14 * b["norepinephrine"],
            "hippocampus": 0.98 - 0.55 * al - 0.20 * b["cortisol"] + 0.18 * b["bdnf"],
            "nac": 0.08 + 0.62 * b["da_phasic"] + 0.20 * b["da_tonic"] - 0.22 * il6,
            "insula": 0.12 + 0.40 * b["norepinephrine"] + 0.28 * b["cortisol"]
                      + 0.22 * tr.get("interoception", 0.5) - 0.18 * b["gaba"],
            "striatum": 0.20 + 0.40 * tr.get("anankastia", 0.3) + 0.28 * b["da_tonic"]
                        + 0.12 * b["glutamate"] - 0.30 * b["serotonin"],
            "dmn": 0.18 + 0.45 * (1 - n.get("dlpfc", 0.7)) + 0.30 * al + 0.18 * tr.get("negative_affectivity", 0.35),
            "hrv": 0.90 - 0.48 * b["norepinephrine"] - 0.22 * b["cortisol"] + 0.18 * b["gaba"] - 0.22 * al,
            "scr": 0.08 + 0.70 * b["norepinephrine"] - 0.20 * b["gaba"],
            "pupil": 0.14 + 0.52 * b["norepinephrine"] + 0.22 * (1 - b["gaba"]),
            "p50_ratio": 0.16 + 0.34 * b["da_tonic"] + 0.26 * tr.get("psychoticism", 0.15)
                         + 0.18 * (1 - b["gaba"]) - 0.10 * n.get("dlpfc", 0.7),
            "p300_amp": 0.18 + 0.42 * n.get("dlpfc", 0.7) + 0.20 * b["da_tonic"]
                        + 0.14 * b["norepinephrine"] - 0.22 * al,
            "p300_lat": 0.85 - 0.32 * n.get("dlpfc", 0.7) + 0.24 * al + 0.18 * sleep,
            "mmn": 0.45 + 0.25 * b["glutamate"] - 0.20 * b["gaba"] + 0.18 * tr.get("psychoticism", 0.15),
            "theta_gamma": 0.22 + 0.45 * n.get("dlpfc", 0.7) + 0.16 * b["da_tonic"] - 0.25 * sleep - 0.15 * al,
            "fai": 0.55 * st.meta["affect_balance"] - 0.25 * tr.get("negative_affectivity", 0.35),
        }

        # 睡眠压力：腺苷 - 睡眠恢复
        targets["sleep_pressure"] = _c(0.10 + 0.85 * b["adenosine"] - 0.35 * b["orexin"])

        for k, target in targets.items():
            if k not in n:
                continue
            tau = NEURO[k][2]
            target = _c(target)
            if k == "fai":
                target = max(-1.0, min(1.0, target))
                n[k] = n[k] + (target - n[k]) * min(0.95, 1.0 / max(0.8, tau))
            else:
                n[k] = _c(n[k] + (target - n[k]) * min(0.95, 1.0 / max(0.8, tau)))

        # EEG 频段：由唤醒度 / 抑制水平 / 睡眠压力决定
        arousal = 0.5 * b["norepinephrine"] + 0.3 * n["scr"] + 0.2 * n["pupil"]
        bands = {
            "eeg_delta": 0.06 + 0.30 * n["sleep_pressure"] + 0.30 * al,
            "eeg_theta": 0.10 + 0.22 * (1 - n["dlpfc"]) + 0.18 * n["dmn"],
            "eeg_alpha": 0.40 - 0.22 * arousal + 0.10 * b["gaba"],
            "eeg_beta": 0.16 + 0.22 * b["norepinephrine"] + 0.10 * n["dlpfc"],
            "eeg_gamma": 0.04 + 0.12 * (1 - b["gaba"]) + 0.08 * b["glutamate"],
        }
        total = sum(max(0.01, v) for v in bands.values())
        for k, v in bands.items():
            n[k] = _c(max(0.01, v) / total)

    # ------------------------------------------------------------------
    # 8. 症状
    # ------------------------------------------------------------------
    def _update_symptoms(self, st: MindState, dims: Dict[str, float],
                         domains: Dict[str, float], cfg: Dict[str, Any]) -> None:
        b, n, tr = st.bio, st.neuro, st.traits
        targets = self._targets(st)

        med_sym = st.meta.get("_med_sym") or {}
        stochastic = bool(cfg.get("stochastic", True))
        res = float(st.meta.get("resilience", 0.0))
        # 域激活→症状的耦合增益。韧性压制它：健康人被骂 5 轮是烦躁，不是惊恐障碍。
        gain = 0.24 * (1.0 - 0.55 * res)

        for key, target in targets.items():
            dom = key.split("_")[0]
            # 模型给出的域激活直接推高该域（这是「关键词→量化指标」的落点）
            acute = DOMAIN_ACUTE.get(dom, 0.5)
            target = target + gain * acute * float(domains.get(dom, 0.0))
            target = _c(target + med_sym.get(key, 0.0))

            cur = st.sym.get(key, 0.0)
            # 韧性同时压制趋近速度：正常人的心理状态有惯性，不会几轮就被重写。
            # 病态预设 res=0，完全不受影响。
            alpha = TAU_SYM.get(dom, 0.12) * (1.0 - 0.60 * res)
            nxt = cur + (target - cur) * alpha

            if stochastic:
                nxt += random.gauss(0, 0.012 + 0.02 * abs(target - cur))

            # 地板：慢性化后不能无限好转
            floor = float((st.meta.get("floor") or {}).get(key, 0.0))
            nxt = max(nxt, floor)
            st.sym[key] = _c(nxt)

        # 记录峰值，用于计算地板
        peak = st.meta.setdefault("peak", {})
        for key, v in st.sym.items():
            if v > float(peak.get(key, 0.0)):
                peak[key] = round(v, 4)

    def _targets(self, st: MindState) -> Dict[str, float]:
        b, n, tr = st.bio, st.neuro, st.traits
        al = float(st.meta.get("allostatic_load", 0.0))
        il6 = b.get("il6", 0.2)
        ser, ne, da = b["serotonin"], b["norepinephrine"], b["da_tonic"]
        cort, gaba = b["cortisol"], b["gaba"]
        amy, vmpfc, dlpfc = n["amygdala"], n["vmpfc"], n["dlpfc"]
        hip, nac, ins = n["hippocampus"], n["nac"], n["insula"]
        stri, dmn, hrv = n["striatum"], n["dmn"], n["hrv"]
        gating = 1.0 - n["p50_ratio"]
        sleep = n["sleep_pressure"]
        psych = tr.get("psychoticism", 0.15)

        # ---------------- 域级压力 ----------------
        # 全部改用「门槛项」(_high/_defi)：健康人的正常值（GABA 0.58、P50 0.35、
        # 杏仁核 0.35…）必须贡献 0。原式用 (1-x) 这类线性项，正常值本身就积出
        # 0.25~0.32 的域压力，再经 sigmoid 放大成 0.5 的「精神病性/创伤」压力，
        # 于是未受任何刺激的健康人 baseline 就有关系妄想 0.47、现实检验受损 0.50。
        ps_p = (0.34 * _high(da, 0.62) + 0.32 * _high(n["p50_ratio"], 0.45)
                + 0.24 * _high(psych, 0.40) + 0.16 * _high(1.0 - gaba, 0.42)
                + 0.14 * _high(al, 0.25) + 0.12 * _high(1.0 - dlpfc, 0.35))
        ng_p = (0.32 * _defi(ser, 0.50) + 0.24 * _defi(da, 0.45) + 0.18 * _high(il6, 0.30)
                + 0.18 * _high(al, 0.25) + 0.14 * _high(1.0 - b["oxytocin"], 0.55))
        md_p = (0.28 * _defi(ser, 0.50) + 0.20 * _defi(ne, 0.40) + 0.16 * _defi(da, 0.45)
                + 0.24 * _high(cort, 0.42) + 0.20 * _defi(b["bdnf"], 0.45)
                + 0.12 * _high(il6, 0.30) + 0.12 * _defi(b["t3"], 0.45)
                # MDD 的影像学三联：海马缩小、前额叶活动降低、杏仁核过度活跃
                + 0.18 * _high(1.0 - hip, 0.60) + 0.14 * _high(1.0 - dlpfc, 0.40)
                + 0.12 * _high(amy, 0.45))
        # 躁狂：DA 驱动的目标/奖赏亢进 + 纹状体过度激活 + 生物钟紊乱。
        # NE 升高 + GABA 降低是焦虑/激越，不是躁狂，故给 NE 低权重高门槛。
        ma_p = (0.42 * _high(da, 0.62) + 0.16 * _high(b["da_phasic"], 0.58)
                + 0.10 * _high(ne, 0.62) + 0.12 * _high(1.0 - gaba, 0.35)
                + 0.20 * _high(stri, 0.60) + 0.14 * _high(1.0 - b["melatonin"], 0.72)
                + 0.18 * _high(sleep, 0.55) + 0.06 * _defi(ser, 0.50) - 0.14 * al)
        ax_p = (0.30 * _high(ne, 0.52) + 0.26 * _high(amy, 0.42)
                + 0.20 * _high(1.0 - gaba, 0.42) + 0.20 * _high(cort, 0.42)
                + 0.16 * _high(1.0 - hrv, 0.50))
        oc_p = (0.28 * _high(stri, 0.55) + 0.24 * _defi(ser, 0.50)
                + 0.22 * _high(tr.get("anankastia", 0.3), 0.45)
                + 0.16 * _high(1.0 - dlpfc, 0.35) + 0.18 * ax_p)
        tr_p = (0.34 * _high(amy, 0.42) + 0.26 * _high(1.0 - vmpfc, 0.55)
                + 0.20 * _high(1.0 - hip, 0.50) + 0.45 * _high(st.meta.get("trauma_load", 0.0), 0.10))
        # 解离：创伤 + 岛叶内感受整合障碍 + 感觉门控脱抑制 + 内源性大麻素紊乱。
        # 岛叶功能低下是 DPDR 的核心影像学证据，此前未被接入公式。
        di_p = (0.35 * _high(st.meta.get("trauma_load", 0.0), 0.10)
                + 0.24 * _high(1.0 - ins, 0.60) + 0.18 * _high(n["p50_ratio"], 0.45)
                + 0.20 * _defi(b["anandamide"], 0.45)
                + 0.22 * _high(1.0 - hrv, 0.50)
                + 0.16 * _high(1.0 - dlpfc, 0.35) + 0.14 * _high(al, 0.25))
        ea_p = (0.24 * _defi(ser, 0.50) + 0.22 * _high(tr.get("anankastia", 0.3), 0.45)
                + 0.18 * _defi(da, 0.45) + 0.15 * _high(1.0 - ins, 0.50)
                + 0.12 * _high(il6, 0.30))
        # 人格特质用绝对门槛（0.45）：特质默认值只是常模中位，不是病理。
        pd_p = (0.30 * _high(tr.get("borderline", 0.15), 0.45)
                + 0.22 * _high(tr.get("negative_affectivity", 0.35), 0.55)
                + 0.18 * _high(tr.get("detachment", 0.25), 0.50)
                + 0.15 * _high(1.0 - tr.get("cognitive_control", 0.6), 0.45))
        cg_p = (0.40 * _high(al, 0.25) + 0.25 * _high(sleep, 0.50)
                + 0.20 * _high(il6, 0.30) + 0.15 * _defi(b["t3"], 0.45))
        sl_p = (0.38 * _high(sleep, 0.45) + 0.20 * _high(1.0 - b["melatonin"], 0.55)
                + 0.22 * ax_p + 0.15 * _defi(ser, 0.50))

        # 域压力 → 0..1（sigmoid 保证健康时接近 0，病重时接近 1）
        ps_s = _sig(ps_p * 2.4, 0.55, 4.5)
        ng_s = _sig(ng_p * 2.6, 0.55, 4.5)
        md_s = _sig(md_p * 2.4, 0.55, 4.5)
        ma_s = _sig(ma_p * 2.4, 0.62, 4.5)
        ax_s = _sig(ax_p * 2.4, 0.55, 4.5)
        oc_s = _sig(oc_p * 2.2, 0.60, 4.5)
        tr_s = _sig(tr_p * 2.0, 0.62, 4.0)
        di_s = _sig(di_p * 2.2, 0.62, 4.0)
        ea_s = _sig(ea_p * 2.4, 0.62, 4.0)
        pd_s = _sig(pd_p * 2.4, 0.60, 4.0)
        cg_s = _sig(cg_p * 2.0, 0.68, 4.0)
        sl_s = _sig(sl_p * 2.2, 0.58, 4.0)

        # ---------------- 具体症状 ----------------
        t: Dict[str, float] = {}

        # 阳性
        t["ps_hallucination_auditory"] = _c(ps_s * (0.65 + 0.45 * psych) - 0.25 * (1 - ps_s))
        t["ps_hallucination_commentary"] = _c(ps_s * 0.95 * (0.5 + 0.7 * amy))
        t["ps_hallucination_command"] = _c(ps_s * 0.85 * (0.4 + 0.7 * tr.get("dissociality", 0.15)))
        t["ps_hallucination_visual"] = _c(ps_s * 0.70 * (0.5 + 0.6 * sleep))
        t["ps_hallucination_tactile"] = _c(ps_s * 0.55 * (0.5 + 0.7 * tr.get("interoception", 0.5)))
        t["ps_delusion_persecutory"] = _c(ps_s * (0.55 + 0.55 * amy) - 0.2 * (1 - ps_s))
        t["ps_delusion_reference"] = _c(ps_s * 0.95 * (0.6 + 0.6 * dmn))
        t["ps_delusion_grandiose"] = _c(max(ps_s * 0.6, ma_s * 0.85) * (0.4 + 0.6 * tr.get("dissociality", 0.15)))
        t["ps_delusion_guilt"] = _c(max(ps_s * 0.5, md_s * 0.9) * (0.5 + 0.7 * tr.get("negative_affectivity", 0.35)))
        t["ps_delusion_somatic"] = _c(max(ps_s * 0.55, ea_s * 0.4) * (0.4 + 0.8 * ins))
        t["ps_delusion_control"] = _c(ps_s * 0.75 * (0.5 + 0.7 * (1 - dlpfc)))
        t["ps_delusion_jealousy"] = _c(ps_s * 0.55 * (0.4 + 0.7 * tr.get("rejection_sensitivity", 0.35)))
        t["ps_delusion_erotomanic"] = _c(ps_s * 0.35 * (0.4 + 0.7 * tr.get("reward_sensitivity", 0.5)))
        t["ps_delusion_nihilistic"] = _c(max(ps_s * 0.45, md_s * 0.8) * (0.4 + 0.7 * md_s))
        t["ps_formal_thought_disorder"] = _c(ps_s * 0.9 * (0.5 + 0.6 * (1 - dlpfc)))
        t["ps_word_salad"] = _c(ps_s * 0.65 * (0.3 + 0.8 * (1 - dlpfc)))
        t["ps_neologism"] = _c(ps_s * 0.55 * (0.4 + 0.8 * psych))
        t["ps_thought_blocking"] = _c(ps_s * 0.6 * (0.4 + 0.7 * (1 - n["theta_gamma"])))
        t["ps_thought_broadcast"] = _c(ps_s * 0.5)
        t["ps_perseveration"] = _c(ps_s * 0.4 + 0.3 * cg_s)
        t["ps_insight_loss"] = _c(ps_s * 0.85 - 0.25 * float(st.meta.get("alliance", 0.35)))
        t["ps_reality_testing_impair"] = _c(ps_s * 0.9)
        t["ps_negative_symptom_cluster"] = _c(ng_s * 0.95)

        # 阴性
        t["ng_affective_flattening"] = _c(ng_s * 0.95)
        t["ng_alogia"] = _c(ng_s * 0.85 * (0.5 + 0.6 * (1 - dlpfc)))
        t["ng_avolition"] = _c(ng_s * 0.9 * (0.5 + 0.7 * (1 - b["da_tonic"])))
        t["ng_anhedonia"] = _c(ng_s * 0.9 * (0.5 + 0.7 * (1 - nac)))
        t["ng_asociality"] = _c(ng_s * 0.85 * (0.5 + 0.7 * tr.get("detachment", 0.25)))
        t["ng_attention_deficit"] = _c(ng_s * 0.7 + 0.3 * (1 - n["theta_gamma"]))
        t["ng_psychomotor_poverty"] = _c(ng_s * 0.75 * (0.5 + 0.6 * (1 - da)))

        # 抑郁
        t["md_depressed_mood"] = _c(md_s * (0.6 + 0.5 * tr.get("negative_affectivity", 0.35)))
        t["md_anhedonia"] = _c(md_s * 0.9 * (0.5 + 0.7 * (1 - nac)))
        t["md_worthlessness"] = _c(md_s * 0.85 * (0.5 + 0.7 * tr.get("negative_affectivity", 0.35)))
        t["md_guilt"] = _c(md_s * 0.8)
        t["md_suicidal_ideation"] = _c(max(0.0, md_s - 0.35) * 1.5 * (0.5 + 0.8 * (1 - tr.get("resilience", 0.55))))
        t["md_hopelessness"] = _c(md_s * 0.9 * (0.4 + 0.7 * (1 - tr.get("resilience", 0.55))))
        t["md_psychomotor_retardation"] = _c(md_s * 0.8 * (0.5 + 0.6 * (1 - da)))
        t["md_agitation"] = _c(md_s * 0.6 * ax_s)
        t["md_insomnia"] = _c(max(0.0, ax_s * 0.7 + md_s * 0.4 - 0.25))
        t["md_hypersomnia"] = _c(max(0.0, md_s * 0.7 + cg_s * 0.3 - 0.35))
        t["md_appetite_loss"] = _c(max(0.0, md_s * 0.6 + ax_s * 0.3 - 0.3))
        t["md_appetite_gain"] = _c(max(0.0, md_s * 0.5 - 0.3))
        t["md_fatigue"] = _c(max(0.0, md_s * 0.7 + (1 - b["t3"]) * 0.2 + il6 * 0.2))
        t["md_concentration"] = _c(max(0.0, md_s * 0.6 + ax_s * 0.3))
        t["md_diurnal_variation"] = _c(md_s * 0.5 if 4 <= self._hour() <= 11 else md_s * 0.15)
        t["md_anxiety_comorbid"] = _c(min(md_s, ax_s) * 1.2)

        # 躁狂
        t["ma_elevated_mood"] = _c(ma_s * 0.95)
        t["ma_irritability"] = _c(ma_s * 0.7 * (0.5 + 0.7 * tr.get("negative_affectivity", 0.35)))
        t["ma_goal_activity"] = _c(ma_s * 0.85 * (0.5 + 0.6 * b["da_tonic"]))
        t["ma_decreased_sleep"] = _c(ma_s * 0.8)
        t["ma_pressured_speech"] = _c(ma_s * 0.8)
        t["ma_flight_of_ideas"] = _c(ma_s * 0.85 * (0.5 + 0.7 * (1 - dlpfc)))
        t["ma_grandiosity"] = _c(ma_s * 0.8 * (0.5 + 0.7 * tr.get("dissociality", 0.15)))
        t["ma_distractibility"] = _c(ma_s * 0.75)
        t["ma_impulsivity"] = _c(ma_s * 0.8 * (0.5 + 0.7 * tr.get("disinhibition", 0.25)))
        t["ma_risky_behavior"] = _c(ma_s * 0.75 * (0.5 + 0.7 * tr.get("disinhibition", 0.25)))
        t["ma_mixed_features"] = _c(min(ma_s, md_s) * 1.4)

        # 焦虑
        t["ax_worry"] = _c(ax_s * 0.9)
        t["ax_panic_attack"] = _c(max(0.0, ax_s - 0.52) * 1.8)
        t["ax_anticipatory_anxiety"] = _c(ax_s * 0.8)
        t["ax_avoidance_agora"] = _c(max(0.0, ax_s - 0.48) * 1.25)
        t["ax_avoidance_social"] = _c(ax_s * 0.85 * (0.5 + 0.7 * tr.get("detachment", 0.25)))
        t["ax_avoidance_specific"] = _c(ax_s * 0.5)
        t["ax_somatic"] = _c(ax_s * 0.7 * (0.5 + 0.6 * ins))
        t["ax_restlessness"] = _c(ax_s * 0.75)
        t["ax_muscle_tension"] = _c(ax_s * 0.6)
        t["ax_hypervigilance"] = _c(ax_s * 0.8 * (0.5 + 0.7 * amy))
        t["ax_separation"] = _c(ax_s * 0.6 * (0.5 + 0.7 * tr.get("rejection_sensitivity", 0.35)))
        t["ax_selective_mutism"] = _c(ax_s * 0.3)

        # 强迫
        t["oc_obsession_contamination"] = _c(oc_s * 0.9 * (0.5 + 0.6 * ins))
        t["oc_obsession_harm"] = _c(oc_s * 0.75 * (0.5 + 0.6 * (1 - tr.get("cognitive_control", 0.6))))
        t["oc_obsession_symmetry"] = _c(oc_s * 0.7 * (0.5 + 0.7 * tr.get("anankastia", 0.3)))
        t["oc_obsession_sexual"] = _c(oc_s * 0.55)
        t["oc_obsession_religious"] = _c(oc_s * 0.45)
        t["oc_compulsion_checking"] = _c(oc_s * 0.85 * (0.5 + 0.7 * ax_s))
        t["oc_compulsion_washing"] = _c(oc_s * 0.75 * (0.5 + 0.6 * ins))
        t["oc_compulsion_counting"] = _c(oc_s * 0.6)
        t["oc_compulsion_ordering"] = _c(oc_s * 0.65 * (0.5 + 0.7 * tr.get("anankastia", 0.3)))
        t["oc_mental_ritual"] = _c(oc_s * 0.7)
        t["oc_hoarding"] = _c(oc_s * 0.4 * (0.5 + 0.7 * tr.get("detachment", 0.25)))
        t["oc_body_dysmorphic"] = _c(oc_s * 0.6 * (0.5 + 0.6 * ins))
        t["oc_health_anxiety"] = _c(max(oc_s * 0.6, ax_s * 0.7) * (0.5 + 0.6 * ins))
        t["oc_trichotillomania"] = _c(oc_s * 0.35)
        t["oc_skin_picking"] = _c(oc_s * 0.35)
        t["oc_insight"] = _c(oc_s * 0.6)

        # 创伤
        t["tr_intrusion"] = _c(tr_s * 0.85)
        t["tr_flashback"] = _c(tr_s * 0.7 * (0.5 + 0.7 * (1 - hip)))
        t["tr_nightmare"] = _c(tr_s * 0.7)
        t["tr_avoidance"] = _c(tr_s * 0.8)
        t["tr_hyperarousal"] = _c(tr_s * 0.85 * (0.5 + 0.7 * amy))
        t["tr_startle"] = _c(tr_s * 0.8)
        t["tr_negative_cognition"] = _c(tr_s * 0.7 * (0.5 + 0.7 * (1 - vmpfc)))
        t["tr_blame"] = _c(tr_s * 0.6)
        t["tr_emotional_dysregulation"] = _c(max(tr_s * 0.7, pd_s * 0.8) * (0.5 + 0.7 * (1 - tr.get("cognitive_control", 0.6))))
        t["tr_identity_diffusion"] = _c(tr_s * 0.5 + pd_s * 0.5)
        t["tr_abandonment_fear"] = _c(tr_s * 0.5 + pd_s * 0.6 * (0.5 + 0.8 * tr.get("rejection_sensitivity", 0.35)))
        t["tr_shame"] = _c(tr_s * 0.55 + md_s * 0.35)
        t["tr_grief"] = _c(float(st.meta.get("grief_load", 0.0)) * 1.2)

        # 分离
        t["di_depersonalization"] = _c(di_s * 0.8)
        t["di_derealization"] = _c(di_s * 0.8)
        t["di_amnesia"] = _c(di_s * 0.5)
        t["di_identity_fragmentation"] = _c(di_s * 0.55 * (0.4 + 0.8 * tr.get("borderline", 0.15)))
        t["di_trance"] = _c(di_s * 0.45)
        t["di_conversion"] = _c(di_s * 0.35)

        # 进食
        t["ea_restriction"] = _c(ea_s * 0.8)
        t["ea_binge"] = _c(ea_s * 0.55 * (0.5 + 0.6 * tr.get("disinhibition", 0.25)))
        t["ea_purge"] = _c(ea_s * 0.5)
        t["ea_body_image_distortion"] = _c(ea_s * 0.8)
        t["ea_fear_weight_gain"] = _c(ea_s * 0.75)
        t["ea_low_weight"] = _c(ea_s * 0.7)

        # 躯体
        t["so_somatic_complaint"] = _c(max(ax_s * 0.6, ins * 0.5))
        t["so_health_preoccupation"] = _c(max(ax_s * 0.65, oc_s * 0.5))
        t["so_medically_unexplained"] = _c(ins * 0.5)

        # 物质：渴求/耐受/戒断必须有使用史，不能给全人群一个 0.3 的底噪
        use = _high(tr.get("disinhibition", 0.25), 0.55)
        t["su_craving"] = _c(0.55 * use)
        t["su_tolerance"] = _c(0.45 * use)
        t["su_withdrawal"] = _c(0.45 * use)
        t["su_control_loss"] = _c(0.50 * use)
        t["su_continue_harm"] = _c(0.45 * use)
        t["su_intoxication"] = _c(0.0)

        # 冲动控制：全部改为「解抑制超过常模」才起量，去掉常数底
        dis = _high(tr.get("disinhibition", 0.25), 0.45)
        t["ic_gambling"] = _c(0.55 * dis + 0.45 * _high(b["da_tonic"], 0.62))
        t["ic_gaming"] = _c(0.75 * dis)
        t["ic_anger_outburst"] = _c(max(0.0, ma_s * 0.7 + ax_s * 0.5 - 0.3) * tr.get("disinhibition", 0.25) * 2)
        t["ic_compulsive_sexual"] = _c(0.70 * _high(tr.get("disinhibition", 0.25), 0.50))
        t["ic_kleptomania"] = _c(0.35 * dis)

        # 人格功能
        t["pd_identity_problems"] = _c(pd_s * 0.8 + di_s * 0.4)
        t["pd_self_direction_deficit"] = _c(pd_s * 0.75 + ng_s * 0.3)
        t["pd_empathy_deficit"] = _c(pd_s * 0.7 * (0.5 + 0.7 * tr.get("dissociality", 0.15)))
        t["pd_intimacy_deficit"] = _c(pd_s * 0.8)
        # 人格特质症状化：直接抄 traits 会把「常模中位」当成「显著特质」，
        # 必须减去常模门槛(0.40)才谈得上「显著」。
        t["pd_negative_affectivity"] = _c(_high(tr.get("negative_affectivity", 0.35), 0.40))
        t["pd_detachment"] = _c(_high(tr.get("detachment", 0.25), 0.40))
        t["pd_dissociality"] = _c(_high(tr.get("dissociality", 0.15), 0.35))
        t["pd_disinhibition"] = _c(_high(tr.get("disinhibition", 0.25), 0.40))
        t["pd_anankastia"] = _c(_high(tr.get("anankastia", 0.3), 0.42))
        t["pd_psychoticism"] = _c(_high(tr.get("psychoticism", 0.15), 0.35))
        t["pd_borderline_pattern"] = _c(tr.get("borderline", 0.15) * (0.7 + 0.5 * ax_s))
        t["pd_manipulativeness"] = _c(tr.get("dissociality", 0.15) * 0.6 + tr.get("borderline", 0.15) * 0.6)
        t["pd_idealize_devalue"] = _c(tr.get("borderline", 0.15) * 1.1)
        t["pd_emptiness"] = _c(tr.get("borderline", 0.15) * 0.8 + md_s * 0.4)
        t["pd_rage"] = _c(max(0.0, ma_s * 0.6 + pd_s * 0.5 + ax_s * 0.4 - 0.4))
        t["pd_self_harm_urge"] = _c(max(0.0, pd_s * 0.7 + md_s * 0.5 - 0.5) * 1.4)

        # 神经发育（特质性强，几乎不随状态波动）
        # 注意缺陷由「认知控制不足 + 解抑制」驱动，而不是单看 dlPFC 值——
        # 否则健康人（dlPFC 0.70）也会被算出 0.21 的注意缺陷。
        nd_ctrl = _high(1.0 - tr.get("cognitive_control", 0.6), 0.40)
        t["nd_social_communication"] = _c(0.08)
        t["nd_restricted_repetitive"] = _c(0.08)
        t["nd_sensory_hyper"] = _c(0.05 + 0.45 * _high(tr.get("interoception", 0.5), 0.55))
        t["nd_inattention"] = _c(0.60 * nd_ctrl + 0.40 * dis)
        t["nd_hyperactivity"] = _c(0.55 * dis + 0.20 * _high(b["norepinephrine"], 0.62))
        t["nd_impulsivity"] = _c(0.75 * dis)

        # 神经认知
        t["cg_memory_deficit"] = _c(cg_s * 0.9 * (0.5 + 0.6 * (1 - hip)))
        t["cg_executive_deficit"] = _c(cg_s * 0.9 * (0.5 + 0.6 * (1 - dlpfc)))
        t["cg_processing_speed"] = _c(cg_s * 0.8)
        t["cg_disorientation"] = _c(max(0.0, cg_s - 0.4) * 1.6)
        t["cg_consciousness_fluctuation"] = _c(max(0.0, cg_s - 0.5) * 1.8)
        # 紧张症：GABA 过低 + DA 过低 + 严重精神运动贫乏
        # 必须用门槛项：GABA 在正常范围时 (1-gaba) 仍有 0.4 以上，
        # 线性相会凭空造出 0.3 的木僵压力，让健康人被骂几句就"蜡样屈曲"。
        # 紧张症的核心是 GABA 能低下 + 多巴胺低下导致的精神运动抑制。
        # 阴性症状（被长期贬损也会攒出来）只能作为高危背景轻微加权：
        # 原来给 0.30 的线性权重，会让「被骂到意志减退」单独造出木僵。
        cat_p = (0.48 * _high(1.0 - gaba, 0.42) + 0.25 * _defi(da, 0.45)
                 + 0.12 * _high(ng_s, 0.55))
        cat_s = _sig(cat_p * 2.2, 0.78, 5.0)
        t["cg_stupor"] = _c(cat_s * 0.95)
        t["cg_waxy_flexibility"] = _c(cat_s * 0.8)
        t["cg_negativism"] = _c(cat_s * 0.85)

        # 睡眠
        t["sl_insomnia"] = _c(sl_s * 0.9)
        t["sl_hypersomnia"] = _c(max(0.0, sl_s * 0.6 + cg_s * 0.4 - 0.3))
        t["sl_circadian_shift"] = _c(sl_s * 0.5)
        t["sl_nightmare"] = _c(tr_s * 0.7)

        # 其他
        t["ot_gender_incongruence"] = _c(0.05)
        t["ot_sexual_dysfunction"] = _c(max(0.0, md_s * 0.5 + ax_s * 0.3 - 0.3))
        t["ot_factitious"] = _c(0.05)
        t["ot_bereavement"] = _c(float(st.meta.get("grief_load", 0.0)) * 1.1)
        t["ot_personality_change"] = _c(cg_s * 0.5 + al * 0.4)

        return t

    # ------------------------------------------------------------------
    # 9. 异稳态负荷 / 慢性化 / 地板
    # ------------------------------------------------------------------
    def _load_and_chronic(self, st: MindState, cfg: Dict[str, Any]) -> None:
        b = st.bio
        al = float(st.meta.get("allostatic_load", 0.0))
        strain = (
            1.10 * max(0.0, b["cortisol"] - 0.55)
            + 0.70 * max(0.0, b["norepinephrine"] - 0.60)
            + 0.50 * max(0.0, b.get("il6", 0.2) - 0.35)
            + 0.30 * max(0.0, 0.4 - b["bdnf"])
            + 0.85 * max(0.0, 0.40 - b["serotonin"])   # 单胺耗竭本身就是代价
        )
        recovery = 0.55 * max(0.0, 0.45 - b["cortisol"]) + 0.35 * max(0.0, b["gaba"] - 0.6)
        al = _c(al + 0.0065 * strain - 0.0009 * recovery)
        st.meta["allostatic_load"] = al

        # 慢性负荷下调调定点：这是「持续虐待最终致病」的唯一物理通路。
        # 没有它，健康人的递质每轮都被拉回基线，聊 300 轮也不会生病。
        sp = st.meta.get("bio_setpoint") or {}
        if sp and al > 0.22:
            drift = 0.0020 * (al - 0.22)
            for k in ("serotonin", "bdnf", "gaba"):
                if k in sp:
                    lo = BIO[k][1] * 0.52          # 最多跌到常模的 52%
                    sp[k] = max(lo, sp[k] - drift)

        first = st.meta.get("dx_first_turn") or {}
        turn = int(st.meta.get("turn", 0))
        if first:
            earliest = min(int(v) for v in first.values())
            elapsed = max(0, turn - earliest)
        else:
            elapsed = 0
        chronic_cfg = int(cfg.get("chronic_turns", 120))
        chronic = 1.0 - math.exp(-elapsed / max(20.0, chronic_cfg))
        chronic = max(chronic, al * 0.85)
        st.meta["chronicity"] = round(chronic, 4)

        # 地板：慢性化后症状不能低于峰值的 45%*chronicity
        peak = st.meta.get("peak") or {}
        floor: Dict[str, float] = {}
        # 地板要记的是「曾经被伤到过什么」，而不是「此刻还病着什么」。
        # 若只取当前诊断的核心症状，会形成死结：一旦好转 → 诊断退出 → core 变空
        # → 地板整体失效 → 下一轮就痊愈。实测 120 轮虐待（3 条地板）能被 120 轮
        # 轻度回应治回 sev 0，就是这条链断在这里。所以每次确诊的核心症状都并进
        # core_ever，只增不减，让伤害留痕。
        ever = set(st.meta.get("core_ever") or [])
        ever |= _core_symptoms(st)
        if ever:
            st.meta["core_ever"] = sorted(ever)
        core = ever
        if chronic > 0.05:
            for k, v in peak.items():
                if k not in core or float(v) < 0.45:
                    continue
                # 慢性化后不能低于峰值的 40%~60%，但允许症状随治疗小幅回落
                f = float(v) * 0.42 * chronic
                if f > 0.05:
                    floor[k] = round(f, 4)
        st.meta["floor"] = floor

    # ------------------------------------------------------------------
    # 10. 本轮"正在发生"的症状（供叙事使用）
    # ------------------------------------------------------------------
    def _hot_symptoms(self, st: MindState, cfg: Dict[str, Any]) -> None:
        hot: Dict[str, float] = {}
        if not cfg.get("stochastic", True):
            st.meta["hot"] = {}
            return
        for k, v in st.sym.items():
            if v < 0.28:
                continue
            dom = k.split("_")[0]
            p = 0.18 + 0.55 * v
            if dom in ("ps", "tr", "di"):
                p *= 0.85
            if random.random() < p * 0.55:
                hot[k] = round(min(1.0, v * random.uniform(0.75, 1.15)), 3)
        # 最多保留 6 条，优先高强度
        st.meta["hot"] = dict(sorted(hot.items(), key=lambda kv: -kv[1])[:6])

    def _hour(self) -> float:
        lt = time.localtime()
        return lt.tm_hour + lt.tm_min / 60.0


def _core_symptoms(st: MindState) -> set:
    """已确立诊断的核心症状集合。只有这些症状才受"慢性化地板"约束。"""
    from .criteria import BY_CODE

    out: set = set()
    for d in (st.meta.get("last_dx") or [])[:1]:
        spec = BY_CODE.get(d.get("code", ""))
        if spec:
            out.update(k for k, _ in spec["crit"])
    return out
