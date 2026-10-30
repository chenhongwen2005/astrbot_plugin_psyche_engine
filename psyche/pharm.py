"""精神药理模块。

刻意做成"延迟起效 + 副作用 + 部分拮抗"的模型，而不是开关：
- SSRI 需要 14~28 轮才起效（对应真实世界的 2~4 周），早期甚至可能加重焦虑；
- 抗精神病药阻断 D2 后阳性症状下降，但阴性症状与锥体外系反应上升；
- 苯二氮䓬类 1 轮见效，但 40 轮后耐受，停药反跳；
- 锂盐起效慢、治疗窗窄，过量会出现震颤/意识模糊。

这样做是为了让"吃药"成为一个有代价的决策，而不是一键回血。
"""

from __future__ import annotations

from typing import Any, Dict, List

# targets: 生化靶点增量（每轮趋近，乘以前述 ramp）
# sym: 症状增量（直接作用于症状层，主要用于副作用）
# latency: 达到 63% 效应所需轮数
DRUGS: Dict[str, Dict[str, Any]] = {
    "奥氮平": {
        "class": "第二代抗精神病药",
        "targets": {"da_tonic": -0.22, "serotonin": +0.10, "gaba": +0.06},
        "sym": {"ps_hallucination_auditory": -0.10, "ps_delusion_persecutory": -0.08,
                "ng_avolition": +0.05, "md_hypersomnia": +0.05},
        "latency": 5.0, "sedation": 0.6,
        "note": "D2/5-HT2A 拮抗，镇静与体重增加明显",
    },
    "利培酮": {
        "class": "第二代抗精神病药",
        "targets": {"da_tonic": -0.26, "serotonin": +0.06},
        "sym": {"ps_hallucination_auditory": -0.12, "ps_delusion_persecutory": -0.09,
                "ng_anhedonia": +0.03},
        "latency": 5.0, "sedation": 0.3,
        "note": "D2 拮抗较强，催乳素升高",
    },
    "氯氮平": {
        "class": "第二代抗精神病药（难治性）",
        "targets": {"da_tonic": -0.12, "serotonin": +0.12, "gaba": +0.08},
        "sym": {"ps_hallucination_auditory": -0.16, "ps_delusion_persecutory": -0.12,
                "ps_formal_thought_disorder": -0.08, "ng_avolition": +0.04},
        "latency": 8.0, "sedation": 0.7,
        "note": "难治性精分首选，需监测粒细胞",
    },
    "氟哌啶醇": {
        "class": "第一代抗精神病药",
        "targets": {"da_tonic": -0.34},
        "sym": {"ps_hallucination_auditory": -0.14, "ps_delusion_persecutory": -0.10,
                "ng_affective_flattening": +0.08, "ng_psychomotor_poverty": +0.10,
                "md_agitation": +0.06},
        "latency": 3.0, "sedation": 0.4,
        "note": "高效价 D2 阻断，锥体外系反应风险高",
    },
    "舍曲林": {
        "class": "SSRI",
        "targets": {"serotonin": +0.22, "bdnf": +0.10, "cortisol": -0.06},
        "sym": {"md_depressed_mood": -0.10, "md_anhedonia": -0.07, "oc_obsession_contamination": -0.08,
                "ax_worry": -0.04},
        "latency": 18.0, "sedation": 0.1,
        "note": "2~4 周起效；早期可能一过性焦虑加重、胃肠不适",
        "early_worse": {"ax_worry": +0.05, "md_agitation": +0.04},
    },
    "氟西汀": {
        "class": "SSRI",
        "targets": {"serotonin": +0.20, "bdnf": +0.12},
        "sym": {"md_depressed_mood": -0.09, "ea_binge": -0.06, "md_anhedonia": -0.06},
        "latency": 20.0, "sedation": 0.05,
        "note": "半衰期长，激活作用偏强，可能诱发激越",
        "early_worse": {"md_agitation": +0.05, "ax_worry": +0.04},
    },
    "文拉法辛": {
        "class": "SNRI",
        "targets": {"serotonin": +0.16, "norepinephrine": +0.12, "da_tonic": +0.05},
        "sym": {"md_depressed_mood": -0.10, "md_fatigue": -0.08, "md_concentration": -0.05},
        "latency": 15.0, "sedation": 0.0,
        "note": "高剂量去甲肾上腺素能增强；停药综合征明显",
    },
    "米氮平": {
        "class": "NaSSA",
        "targets": {"serotonin": +0.14, "norepinephrine": +0.10},
        "sym": {"md_insomnia": -0.14, "md_appetite_loss": -0.10, "md_depressed_mood": -0.06},
        "latency": 10.0, "sedation": 0.8,
        "note": "镇静、食欲增加，适合伴失眠与消瘦者",
    },
    "锂盐": {
        "class": "心境稳定剂",
        "targets": {"da_tonic": -0.10, "glutamate": -0.10, "bdnf": +0.12},
        "sym": {"ma_elevated_mood": -0.12, "ma_goal_activity": -0.10, "ma_irritability": -0.08,
                "md_suicidal_ideation": -0.10},
        "latency": 12.0, "sedation": 0.2,
        "note": "治疗窗窄；中毒时手抖、呕吐、意识模糊",
        "toxicity": {"cg_disorientation": +0.15, "ax_somatic": +0.10},
    },
    "丙戊酸": {
        "class": "心境稳定剂",
        "targets": {"gaba": +0.14, "glutamate": -0.06},
        "sym": {"ma_elevated_mood": -0.10, "ma_irritability": -0.10, "ma_mixed_features": -0.06},
        "latency": 8.0, "sedation": 0.3,
        "note": "GABA 能增强，体重与肝功能需监测",
    },
    "拉莫三嗪": {
        "class": "心境稳定剂",
        "targets": {"glutamate": -0.12, "bdnf": +0.06},
        "sym": {"md_depressed_mood": -0.07, "ma_mixed_features": -0.05},
        "latency": 20.0, "sedation": 0.1,
        "note": "双相抑郁维持期首选，需缓慢加量防皮疹",
    },
    "氯硝西泮": {
        "class": "苯二氮䓬类",
        "targets": {"gaba": +0.24},
        "sym": {"ax_worry": -0.14, "ax_panic_attack": -0.16, "ax_hypervigilance": -0.10,
                "md_insomnia": -0.08},
        "latency": 1.0, "sedation": 0.6,
        "note": "1 轮见效；40 轮后耐受，骤停反跳性焦虑",
        "tolerance_after": 40,
    },
    "丁螺环酮": {
        "class": "5-HT1A 部分激动剂",
        "targets": {"serotonin": +0.10},
        "sym": {"ax_worry": -0.08, "ax_anticipatory_anxiety": -0.06},
        "latency": 14.0, "sedation": 0.05,
        "note": "无依赖，起效慢",
    },
    "普萘洛尔": {
        "class": "β 受体阻滞剂",
        "targets": {"norepinephrine": -0.12},
        "sym": {"ax_somatic": -0.14, "ax_muscle_tension": -0.06, "scr": -0.0},
        "latency": 2.0, "sedation": 0.1,
        "note": "主要压躯体症状（心悸、手抖），对认知性担忧无效",
    },
    "哌甲酯": {
        "class": "中枢兴奋剂",
        "targets": {"da_tonic": +0.20, "norepinephrine": +0.16},
        "sym": {"nd_inattention": -0.14, "nd_hyperactivity": -0.08, "nd_impulsivity": -0.08,
                "md_fatigue": -0.05, "ax_worry": +0.05},
        "latency": 1.5, "sedation": -0.3,
        "note": "快速起效；可致失眠、食欲下降、焦虑加重",
    },
    "托莫西汀": {
        "class": "选择性 NE 再摄取抑制",
        "targets": {"norepinephrine": +0.14, "da_tonic": +0.05},
        "sym": {"nd_inattention": -0.10, "nd_hyperactivity": -0.06},
        "latency": 14.0, "sedation": 0.1,
        "note": "无成瘾性，起效慢",
    },
    "纳曲酮": {
        "class": "阿片受体拮抗剂",
        "targets": {"endorphin": -0.10},
        "sym": {"su_craving": -0.12, "ic_gambling": -0.06},
        "latency": 4.0, "sedation": 0.0,
        "note": "降低酒精/阿片渴求与 gambling 欣快",
    },
    "褪黑素": {
        "class": "时相调节",
        "targets": {"melatonin": +0.20, "adenosine": +0.05},
        "sym": {"sl_insomnia": -0.10, "sl_circadian_shift": -0.08},
        "latency": 2.0, "sedation": 0.2,
        "note": "对入睡时相偏移有效，对焦虑性失眠有限",
    },
    "电休克": {
        "class": "物理治疗（ECT）",
        "targets": {"bdnf": +0.20, "cortisol": -0.12, "da_tonic": +0.06},
        "sym": {"md_depressed_mood": -0.22, "md_suicidal_ideation": -0.24,
                "ma_elevated_mood": -0.10, "cg_memory_deficit": +0.10},
        "latency": 3.0, "sedation": 0.5,
        "note": "重度抑郁/紧张症有效，可逆性记忆损害",
    },
}

ALIASES = {
    "olanzapine": "奥氮平", "risperidone": "利培酮", "clozapine": "氯氮平",
    "haloperidol": "氟哌啶醇", "sertraline": "舍曲林", "fluoxetine": "氟西汀",
    "venlafaxine": "文拉法辛", "mirtazapine": "米氮平", "lithium": "锂盐",
    "valproate": "丙戊酸", "lamotrigine": "拉莫三嗪", "clonazepam": "氯硝西泮",
    "buspirone": "丁螺环酮", "propranolol": "普萘洛尔", "methylphenidate": "哌甲酯",
    "atomoxetine": "托莫西汀", "naltrexone": "纳曲酮", "melatonin": "褪黑素", "ect": "电休克",
}


def resolve(name: str) -> str | None:
    name = (name or "").strip()
    if name in DRUGS:
        return name
    return ALIASES.get(name.lower())


def ramp(turns_on: float, latency: float) -> float:
    """一阶起效曲线：t=latency 时达到 63%。"""
    if turns_on <= 0:
        return 0.0
    lat = max(0.5, latency)
    return 1.0 - pow(2.718281828, -turns_on / lat)


def active_effects(meds: List[Dict[str, Any]], turn: int) -> Dict[str, Any]:
    """汇总当前所有在服药物的生化/症状效应。"""
    bio: Dict[str, float] = {}
    sym: Dict[str, float] = {}
    notes: List[str] = []
    for m in meds or []:
        spec = DRUGS.get(m.get("name", ""))
        if not spec:
            continue
        on = turn - int(m.get("start_turn", turn))
        r = ramp(on, spec.get("latency", 5.0))
        dose = float(m.get("dose", 1.0))

        # 耐受：苯二氮䓬类长期使用效应衰减
        tol_after = spec.get("tolerance_after")
        if tol_after and on > tol_after:
            r *= max(0.25, 1.0 - (on - tol_after) / (tol_after * 2.0))

        # 早期恶化（SSRI 激活综合征）
        early = spec.get("early_worse") or {}
        if on <= max(2.0, spec.get("latency", 5.0) * 0.25):
            for k, v in early.items():
                sym[k] = sym.get(k, 0.0) + v * dose * 0.8

        for k, v in (spec.get("targets") or {}).items():
            bio[k] = bio.get(k, 0.0) + v * r * dose
        for k, v in (spec.get("sym") or {}).items():
            sym[k] = sym.get(k, 0.0) + v * r * dose

        # 锂盐中毒（剂量 > 1.4 视为过量）
        if spec.get("toxicity") and dose > 1.4:
            for k, v in spec["toxicity"].items():
                sym[k] = sym.get(k, 0.0) + v * dose * r

        if r > 0.05:
            notes.append(f"{m['name']}（第{on}轮，效应 {r:.0%}）")
    return {"bio": bio, "sym": sym, "notes": notes}
