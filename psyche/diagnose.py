"""诊断层：把连续的状态向量映射为 ICD-11 诊断结论。

不是查表，而是三步贝叶斯式推断：

    ① 症状学似然  P(symptoms | disorder)
       该诊断要求的条目有多少条达到阈值、达到的有多重、有没有"排除性"条目被违反
       （例如妄想障碍要求幻觉不突出，一旦幻听很重就扣分）。

    ② 生物学先验  P(biomarker | disorder)
       把当前 21 维特征与诊断原型的典型偏移方向做余弦式匹配。
       这一项专门用于"症状相似但病因不同"的鉴别：同样是退缩不语，
       精分（DA↑、门控↓）与抑郁（5-HT↓、皮质醇↑）的生物学签名相反。

    ③ 病程与固化
       同一诊断需持续存在才能"确立"；确立后写入 dx_first_turn，
       由 dynamics 计算慢性化与症状地板。

输出包含：主诊断、共病、严重度指数、病程、鉴别诊断、可治疗性。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .const import SEVERITY_LABELS, COURSE_LABELS, symptom_label
from .criteria import CORE, DISORDERS, GROUP_TALKABILITY
from .model import MindState


@dataclass
class DxResult:
    code: str
    zh: str
    en: str
    group: str
    prob: float
    severity: float
    severity_label: str
    met: int
    total: int
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    caps_violated: List[str] = field(default_factory=list)
    bio_fit: float = 0.0
    duration: int = 0
    course: str = ""
    chronic: float = 0.0
    curability: float = 0.0
    talkability: float = 0.0
    note: str = ""
    perf: str = ""
    custom: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code, "zh": self.zh, "en": self.en, "group": self.group,
            "prob": round(self.prob, 3), "severity": round(self.severity, 1),
            "severity_label": self.severity_label, "met": self.met, "total": self.total,
            "evidence": self.evidence, "bio_fit": round(self.bio_fit, 3),
            "duration": self.duration, "course": self.course,
            "chronic": round(self.chronic, 3), "curability": self.curability,
            "talkability": round(self.talkability, 3), "note": self.note,
            "perf": self.perf, "custom": self.custom,
        }


@dataclass
class Diagnosis:
    primary: Optional[DxResult]
    comorbid: List[DxResult]
    differential: List[DxResult]
    severity: float
    severity_label: str
    chronic: float
    talkability: float

    def all(self) -> List[DxResult]:
        out = []
        if self.primary:
            out.append(self.primary)
        out.extend(self.comorbid)
        return out

    def codes(self) -> List[str]:
        return [d.code for d in self.all()]


def _sig(x: float, mid: float = 0.0, k: float = 1.0) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-k * (x - mid)))
    except OverflowError:
        return 0.0 if x < mid else 1.0


def severity_label(v: float) -> str:
    label = SEVERITY_LABELS[0][1]
    for th, name in SEVERITY_LABELS:
        if v >= th:
            label = name
    return label


def _bio_fit(features: Dict[str, float], profile: Dict[str, float]) -> float:
    if not profile:
        return 0.0
    num, den = 0.0, 0.0
    for k, direction in profile.items():
        if k not in features:
            continue
        # 特征映射到 -1..1 的偏离度
        z = max(-1.0, min(1.0, (features[k] - 0.5) / 0.5))
        num += direction * z * abs(direction)
        den += abs(direction)
    if den <= 0:
        return 0.0
    return max(-1.0, min(1.0, num / den))


def diagnose(st: MindState, cfg: Dict[str, Any] | None = None) -> Diagnosis:
    cfg = cfg or {}
    feats = st.features()
    turn = int(st.meta.get("turn", 0))
    first_map: Dict[str, int] = dict(st.meta.get("dx_first_turn") or {})
    chronic = float(st.meta.get("chronicity", 0.0))

    results: List[DxResult] = []
    prior_duration = max([turn - int(v) for v in first_map.values()] or [0])
    # 即便尚未跑过一次动力学，也按病程估算慢性化，保证首次展示一致
    if prior_duration > 0:
        est = 1.0 - math.exp(-prior_duration / max(20.0, float(cfg.get("chronic_turns", 120))))
        chronic = max(chronic, min(0.97, est))
    for d in DISORDERS:
        crit = d["crit"]
        total_w = sum(w for _, w in crit)
        met = [(k, w) for k, w in crit if st.s(k) >= d["min_sev"]]
        # 加权覆盖：症状越重贡献越大，避免"刚过阈值"就把覆盖度顶满
        met_w = sum(w * st.s(k) for k, w in met)
        coverage = met_w / total_w if total_w > 0 else 0.0

        onset = first_map.get(d["code"])
        duration = max(0, turn - int(onset)) if onset is not None else 0

        # 排除性条目（caps）：违反越多，越不像该诊断
        cap_pen = 0.0
        caps_violated: List[str] = []
        for k, cap in (d.get("caps") or {}).items():
            excess = st.s(k) - cap
            if excess > 0:
                cap_pen += excess
                caps_violated.append(k)

        # 核心症状未命中：该诊断不成立
        core = CORE.get(d["code"]) or []
        core_miss = bool(core) and not any(st.s(k) >= d["min_sev"] * 0.9 for k in core)
        if core_miss:
            cap_pen += 1.0

        bio = _bio_fit(feats, d.get("profile") or {})

        # 症状不足：越过 min_n 才有资格，否则快速衰减
        n_short = max(0, d["min_n"] - len(met))

        logit = (
            -2.15
            + 4.70 * coverage
            + 1.55 * bio
            + 0.55 * min(1.0, sum(st.s(k) for k, _ in met) / max(1, len(met)))
            + 0.35 * min(1.0, len(crit) / 7.0)
            - 3.00 * cap_pen
            - 1.35 * n_short
        )

        # 病程时限：急性/短暂性诊断不能用来解释一个已经病了 200 轮的人
        max_t = int(d.get("max_turns") or 0)
        # 未确诊时没有起病点，用「观察期长度」代替病程。
        # 否则会形成死锁：确诊需要病程，病程又要确诊后才开始累积，
        # 结果 dur 恒为 0，任何有 min_turns 的障碍永远够不着门槛
        # （实测 200 轮持续侮辱/贬损，dur 一直是 0，严重度 35 却诊断不出任何东西）。
        dur_cap = duration if onset is not None else max(prior_duration, turn)
        if max_t and dur_cap > max_t:
            logit -= 2.4 * min(2.0, dur_cap / max(1, max_t))

        # 病程下限：ICD-11 对多数障碍都有最短病程要求（GAD「数月」、广场恐惧「数月」）。
        # 没有这一段，健康人聊 5 轮被骂两句就会被确诊广泛性焦虑障碍。
        min_t = int(d.get("min_turns") or 0)
        if min_t > 1 and dur_cap < min_t:
            shortfall = (min_t - dur_cap) / float(min_t)
            logit -= 2.4 * shortfall

        # 复发/发作次数要求（如复发性抑郁需要 ≥2 次发作史）
        need_ep = int((d.get("needs") or {}).get("episodes_min", 0))
        if need_ep and int(st.meta.get("episodes", 0)) < need_ep:
            logit -= 2.2

        # 急性反应性诊断不能用来解释一个长期病程的人
        if d.get("acute") and prior_duration > 80:
            logit -= 1.8

        # 人格与神经发育障碍是终生构型：没有病史就不能在几十轮对话里"新发"
        if d["group"] in ("personality", "neurodev") and onset is None:
            logit -= 2.6

        # 互斥诊断不能覆盖一个已经确立的病程（如把慢性抑郁改判成混合性焦虑抑郁）
        ex = d.get("excludes") or []
        if ex and any(c in first_map for c in ex) and onset is None:
            logit -= 1.1

        # 既已确立的诊断不会因为一次谈话就消失：给出持续先验
        # （这既符合临床，也实现了"一旦病态，极难自愈"）
        if onset is not None and (coverage > 0.06 or len(met) >= 1):
            # 反复发作/终生性障碍（双相、精神病性、人格、发育、认知）病史权重更高
            lifelong = d["group"] in ("bipolar", "psychotic", "personality", "neurodev", "neurocognitive")
            logit += 1.40 if lifelong else 0.75
            if (turn - int(onset)) > 100:
                logit += 0.45

        prob = _sig(logit, 0.0, 1.0)

        if len(met) < d["min_n"]:
            prob *= 0.35

        evidence = [
            {"key": k, "label": symptom_label(k), "value": round(st.s(k), 3), "weight": w}
            for k, w in sorted(met, key=lambda kv: -st.s(kv[0]))[:6]
        ]

        sev = 0.0
        if met:
            mean_met = sum(st.s(k) for k, _ in met) / len(met)
            # 用幂函数压缩，避免"条目多"把严重度顶到 90+
            sev = 100.0 * (mean_met ** 1.30) * (0.65 + 0.35 * coverage)
            sev *= min(1.10, 0.90 + 0.06 * len(met))
            # 人格与神经发育障碍是稳定构型，严重度上限低于急性发作
            sev = min(sev, {"personality": 85.0, "neurodev": 72.0}.get(d["group"], 100.0))

        curability = float(d.get("curability", 0.05))
        talk = curability * GROUP_TALKABILITY.get(d["group"], 0.3)

        results.append(DxResult(
            code=d["code"], zh=d["zh"], en=d["en"], group=d["group"],
            prob=prob, severity=min(100.0, sev), severity_label=severity_label(min(100.0, sev)),
            met=len(met), total=len(crit), evidence=evidence,
            caps_violated=caps_violated, bio_fit=bio,
            duration=duration, course=_course(sev, duration, chronic, len(first_map) > 0),
            chronic=chronic, curability=curability, talkability=talk,
            note=d.get("note", ""), perf=d.get("perf", d["group"]), custom=d.get("custom", False),
        ))

    results.sort(key=lambda r: (-r.prob, -r.severity))

    # 主诊断：概率 × 严重度综合排序，避免"轻微但概率高"压过"重且明确"
    # 以概率为主序（概率已含症状覆盖与生物学拟合），严重度只做轻微次序修正
    ranked = sorted(results, key=lambda r: -(r.prob + 0.15 * r.severity / 100.0))
    if ranked and ranked[0].custom:
        for r in ranked[1:]:
            if not r.custom and r.prob >= ranked[0].prob - 0.15 and r.met >= 2:
                ranked.remove(r)
                ranked.insert(0, r)
                break
    # 确诊门槛：概率、条目数、严重度三者都要够。
    # 只看 prob>=0.30 会让「严重度 29 的紧张症」成立——临床上不可能。
    # 严重度下限取 22：环性心境、轻度人格障碍这类本身就轻，不能一刀切到 30。
    primary = (ranked[0] if ranked
               and ranked[0].prob >= 0.42
               and ranked[0].met >= 2
               and ranked[0].severity >= 22.0
               else None)

    comorbid: List[DxResult] = []
    if primary:
        excl: set = set()
        for d in DISORDERS:
            if d["code"] == primary.code:
                excl.update(d.get("excludes") or [])
            elif primary.code in (d.get("excludes") or []):
                excl.add(d["code"])
        for r in ranked[1:]:
            if len(comorbid) >= 2:
                break
            if r.code == primary.code or r.code in excl:
                continue
            if r.prob >= 0.55 and r.severity >= 38 and r.group != primary.group:
                comorbid.append(r)

    differential = [r for r in ranked[1:5]
                    if r.code != (primary.code if primary else "") and r.prob >= 0.08][:3]

    if primary:
        overall = max(primary.severity, max((c.severity for c in comorbid), default=0.0) * 0.85)
        talk = primary.talkability
    else:
        overall = max((r.severity for r in ranked[:3]), default=0.0) * 0.6
        talk = 0.3

    return Diagnosis(
        primary=primary, comorbid=comorbid, differential=differential,
        severity=round(overall, 1), severity_label=severity_label(overall),
        chronic=chronic, talkability=talk,
    )


def _course(sev: float, duration: int, chronic: float, has_history: bool) -> str:
    if sev < 15:
        return "full_remission"
    if sev < 32:
        return "partial_remission"
    if chronic > 0.5 or duration > 20:
        return "continuous"
    if has_history and duration <= 3:
        return "recurrent"
    return "first"


def update_state(st: MindState, dx: Diagnosis) -> None:
    """把诊断结论写回状态：确立病程、记录历史、给出治疗可及性。"""
    turn = int(st.meta.get("turn", 0))
    first_map: Dict[str, int] = dict(st.meta.get("dx_first_turn") or {})
    hist: List[Dict[str, Any]] = list(st.meta.get("dx_history") or [])

    for r in dx.all():
        if r.code not in first_map and r.prob >= 0.55 and r.severity >= 28:
            first_map[r.code] = turn
            hist.append({"turn": turn, "code": r.code, "zh": r.zh,
                         "prob": round(r.prob, 3), "sev": round(r.severity, 1), "event": "onset"})

    # 历史只保留最近 60 条
    st.meta["dx_first_turn"] = first_map
    st.meta["dx_history"] = hist[-60:]
    st.meta["last_severity"] = dx.severity
    st.meta["last_talkability"] = dx.talkability
    st.meta["last_dx"] = [r.to_dict() for r in dx.all()]
    st.meta["last_dx_turn"] = turn
