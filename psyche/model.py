"""状态容器：一份可序列化的"类脑精神状态"。

所有子状态均为 dict[str, float]，键集合由 const.py 定义。
这样做的好处：序列化零成本、易于扩展、便于做 z 分数与原型匹配。
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .const import BIO, NEURO, SYM, TRAITS


def _baseline_bio() -> Dict[str, float]:
    return {k: v[1] for k, v in BIO.items()}


def _baseline_neuro() -> Dict[str, float]:
    return {k: v[1] for k, v in NEURO.items()}


def _baseline_sym() -> Dict[str, float]:
    # 初始为亚临床水平，避免一上来就满头病名
    return {k: 0.08 for k in SYM}


def _baseline_traits() -> Dict[str, float]:
    return {k: v[1] for k, v in TRAITS.items()}


def default_meta() -> Dict[str, Any]:
    return {
        "turn": 0,
        "created_at": time.time(),
        "updated_at": time.time(),
        "preset": "healthy",
        "persona": "",
        # 病程
        "dx_first_turn": {},          # code -> turn
        "dx_history": [],             # [{turn, code, prob, sev}]
        "episodes": 0,                # 发作次数（由缓解→复发时 +1）
        "remission_turns": 0,
        # 治疗相关
        "alliance": 0.35,             # 治疗联盟 0..1
        "therapy_accum": 0.0,         # 累计有效正向输入（轮当量）
        "positive_accum": 0.0,
        "negative_accum": 0.0,
        # 负荷与固化
        "allostatic_load": 0.10,      # 异稳态负荷 0..1，几乎不可逆
        "trauma_load": 0.0,
        "resilience": 0.0,            # 心理韧性 0..1，压制单轮冲击与域增益；健康人高、病人低
        "chronicity": 0.0,            # 0..1，由病程与负荷共同决定
        "floor": {},                  # 症状地板 {sym: value}
        # 药物
        "meds": [],                   # [{name, start_turn, dose}]
        # 依从性 / 压力
        "pressure": 0.0,              # 演出约束压力（合规检测用）
        "violations": 0,
        "compliance_avg": 1.0,
        # 安全
        "crisis": False,
        "crisis_turns": 0,
        # 本轮
        "hot": {},                    # 本轮"正在发生"的症状及强度
        "appraisal": {},              # 本轮评估向量
        "last_user": "",
    }


@dataclass
class MindState:
    bio: Dict[str, float] = field(default_factory=_baseline_bio)
    # 身体：器官功能、检验、生活方式、活动疾病。字段独立于精神侧，
    # 两套模型只在 Physiology.couple() 处单向对接。
    body: Dict[str, Any] = field(default_factory=dict)
    neuro: Dict[str, float] = field(default_factory=_baseline_neuro)
    sym: Dict[str, float] = field(default_factory=_baseline_sym)
    traits: Dict[str, float] = field(default_factory=_baseline_traits)
    meta: Dict[str, Any] = field(default_factory=default_meta)

    # ---------------- 基本操作 ----------------
    def clone(self) -> "MindState":
        return MindState(
            body=copy.deepcopy(self.body),
            bio=copy.deepcopy(self.bio),
            neuro=copy.deepcopy(self.neuro),
            sym=copy.deepcopy(self.sym),
            traits=copy.deepcopy(self.traits),
            meta=copy.deepcopy(self.meta),
        )

    def z_bio(self, key: str) -> float:
        base, sd = BIO[key][1], BIO[key][3]
        return (self.bio.get(key, base) - base) / max(sd, 1e-6)

    def z_neuro(self, key: str) -> float:
        base, sd = NEURO[key][1], NEURO[key][3]
        return (self.neuro.get(key, base) - base) / max(sd, 1e-6)

    def s(self, key: str) -> float:
        """取症状强度，缺省 0。"""
        return float(self.sym.get(key, 0.0))

    def t(self, key: str) -> float:
        return float(self.traits.get(key, TRAITS.get(key, ("", 0.5))[1]))

    def bump(self, key: str, delta: float, lo: float = 0.0, hi: float = 1.0) -> None:
        if key not in self.sym:
            return
        self.sym[key] = max(lo, min(hi, self.sym.get(key, 0.0) + delta))

    def tick(self) -> None:
        self.meta["turn"] = int(self.meta.get("turn", 0)) + 1
        self.meta["updated_at"] = time.time()

    # ---------------- 序列化 ----------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "v": 2,
            "body": self.body,
            "bio": {k: round(v, 5) for k, v in self.bio.items()},
            "neuro": {k: round(v, 5) for k, v in self.neuro.items()},
            "sym": {k: round(v, 4) for k, v in self.sym.items() if v > 0.001},
            "traits": {k: round(v, 5) for k, v in self.traits.items()},
            "meta": self.meta,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MindState":
        st = cls()
        raw_body = data.get("body") or {}
        if raw_body:
            try:
                from .compat import physio as _P

                st.body = _P.ensure_body(raw_body)
            except Exception:
                st.body = dict(raw_body)
        st.bio.update({k: float(v) for k, v in (data.get("bio") or {}).items() if k in st.bio})
        st.neuro.update({k: float(v) for k, v in (data.get("neuro") or {}).items() if k in st.neuro})
        st.sym.update({k: float(v) for k, v in (data.get("sym") or {}).items() if k in st.sym})
        st.traits.update({k: float(v) for k, v in (data.get("traits") or {}).items() if k in st.traits})
        meta = default_meta()
        meta.update(data.get("meta") or {})
        st.meta = meta
        return st

    @classmethod
    def from_json(cls, raw: Optional[str]) -> "MindState":
        if not raw:
            return cls()
        try:
            return cls.from_dict(json.loads(raw))
        except Exception:
            return cls()

    # ---------------- 派生指标 ----------------
    def features(self) -> Dict[str, float]:
        """把生化/电生理压成一组可解释的中层特征，供诊断原型匹配使用。"""
        b, n = self.bio, self.neuro
        al = float(self.meta.get("allostatic_load", 0.0))
        inflam = b.get("il6", 0.2)
        return {
            "dopamine": _clip01(0.6 * b.get("da_tonic", 0.55) + 0.4 * b.get("da_phasic", 0.5)),
            "serotonin": _clip01(b.get("serotonin", 0.55)),
            "norepinephrine": _clip01(b.get("norepinephrine", 0.45)),
            "hpa_axis": _clip01(0.55 * b.get("cortisol", 0.35) + 0.45 * b.get("crh", 0.3)),
            "gaba": _clip01(b.get("gaba", 0.58)),
            "glutamate": _clip01(b.get("glutamate", 0.52)),
            "inflammation": _clip01(inflam * 1.6),
            "neuroplasticity": _clip01(0.5 * b.get("bdnf", 0.5) + 0.3 * b.get("t3", 0.5) + 0.2 * (1 - al)),
            "reward_response": _clip01(0.5 * n.get("nac", 0.5) + 0.5 * b.get("da_phasic", 0.5)),
            "threat_reactivity": _clip01(0.7 * n.get("amygdala", 0.35) + 0.3 * b.get("norepinephrine", 0.45)),
            "prefrontal_control": _clip01(n.get("dlpfc", 0.7)),
            "hippocampal_integrity": _clip01(n.get("hippocampus", 0.7)),
            "salience": _clip01(0.6 * n.get("insula", 0.4) + 0.4 * n.get("amygdala", 0.35)),
            "default_mode": _clip01(n.get("dmn", 0.5)),
            "interoception": _clip01(n.get("insula", 0.4)),
            "arousal": _clip01(0.5 * n.get("scr", 0.25) + 0.3 * n.get("pupil", 0.4) + 0.2 * b.get("norepinephrine", 0.45)),
            "sleep_debt": _clip01(n.get("sleep_pressure", 0.3)),
            "autonomic_flex": _clip01(n.get("hrv", 0.55)),
            "gating": _clip01(1.0 - n.get("p50_ratio", 0.35)),
            "striatal_gain": _clip01(n.get("striatum", 0.5)),
            "oxytocin": _clip01(b.get("oxytocin", 0.5)),
            "allostatic_load": _clip01(al),
        }


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))
