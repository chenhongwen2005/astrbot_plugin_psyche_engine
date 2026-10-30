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


# ---------------------------------------------------------------------------
# 副作用层
# ---------------------------------------------------------------------------
# 之前副作用只有一个去处：塞进 `sym`（症状层）。问题在于症状层是「疾病」的度量，
# 药带来的嗜睡、手抖、口干混进去以后，和病情本身完全无法区分——于是会出现两个后果：
#   1. 健康人吃奥氮平，诊断器看到「嗜睡 + 意志减退」就往抑郁/阴性症状上算，等于误诊；
#   2. 注入块里没有任何一句提到药，模型既不知道自己吃什么，也不可能主动说「我手抖」，
#      更不可能在对方问「这药有什么副作用」时答得出来。
# 所以副作用必须有独立的状态量与独立的文本通道，不能寄生在症状层。
SIDE_DEFS: Dict[str, tuple] = {
    # id: (名称, 体感描述——注入块给模型的就是这个，要求是身体感受而非诊断名词)
    "sedation": ("嗜睡", "犯困，反应变慢，说话变短"),
    "weight_gain": ("体重增加", "食欲变大，衣服变紧"),
    "appetite_up": ("食欲增加", "总想吃，尤其想吃碳水"),
    "appetite_down": ("食欲下降", "吃两口就饱，饭没味道"),
    "dry_mouth": ("口干", "嘴里发干，老想喝水"),
    "constipation": ("便秘", "排便变少、腹胀"),
    "nausea": ("恶心", "胃里翻，闻不得油烟"),
    "akathisia": ("静坐不能", "坐不住，腿里像有东西在爬"),
    "tremor": ("手抖", "端碗、写字时发抖"),
    "eps_stiff": ("肌肉僵硬", "动作发僵，转身不利索"),
    "prolactin": ("催乳素升高", "乳房胀痛、月经不规律"),
    "sexual": ("性功能减退", "没兴趣，也很难有反应"),
    "sweating": ("多汗", "动不动一身汗"),
    "polyuria": ("多尿口渴", "老跑厕所，总觉得渴"),
    "memory": ("记忆减退", "刚说的事想不起来"),
    "headache": ("头痛", "太阳穴一跳一跳"),
    "orthostatic": ("起身发晕", "站起来眼前发黑"),
    "activation": ("一过性激越", "心里发紧、坐立不安"),
    "insomnia": ("入睡困难", "躺下很久睡不着"),
    "rash": ("皮疹", "身上起红点，发痒"),
}

# 副作用起效速度（达到 63% 所需轮数）。多数副作用比疗效早得多，这是关键差别：
# SSRI 要 18 轮才见效，但恶心第 2 轮就来——患者抱怨的往往正是「还没效先难受」。
SIDE_ONSET: Dict[str, float] = {
    "sedation": 1.5, "nausea": 2.0, "headache": 2.5, "activation": 2.5,
    "dry_mouth": 3.0, "orthostatic": 3.0, "sweating": 4.0, "appetite_down": 3.0,
    "insomnia": 4.0, "polyuria": 4.0, "tremor": 5.0, "akathisia": 4.0,
    "eps_stiff": 6.0, "rash": 6.0, "memory": 8.0, "sexual": 8.0,
    "constipation": 6.0, "appetite_up": 7.0, "weight_gain": 14.0, "prolactin": 10.0,
}

# 副作用里真正会碰到症状层的少数几条（其余只作为身体感受存在，不参与诊断）
SIDE_SYM: Dict[str, Dict[str, float]] = {
    "sedation": {"md_hypersomnia": 0.09, "md_concentration": 0.05},
    "akathisia": {"md_agitation": 0.10, "ax_somatic": 0.08},
    "eps_stiff": {"ng_psychomotor_poverty": 0.07},
    "activation": {"md_agitation": 0.07, "ax_worry": 0.05},
    "nausea": {"so_somatic_complaint": 0.06},
    "headache": {"so_somatic_complaint": 0.05},
    "tremor": {"so_somatic_complaint": 0.04},
    "dry_mouth": {"so_somatic_complaint": 0.03},
}

# 每个药的副作用谱（系数 = 剂量 1、达峰时的强度）
SIDE_PROFILE: Dict[str, Dict[str, float]] = {
    "奥氮平": {"sedation": 0.72, "weight_gain": 0.85, "appetite_up": 0.75, "dry_mouth": 0.35,
               "constipation": 0.35, "orthostatic": 0.25},
    "利培酮": {"prolactin": 0.80, "eps_stiff": 0.50, "weight_gain": 0.50, "sedation": 0.35,
               "orthostatic": 0.30},
    "氯氮平": {"sedation": 0.90, "weight_gain": 0.90, "appetite_up": 0.80, "constipation": 0.80,
               "dry_mouth": 0.70, "orthostatic": 0.60, "prolactin": 0.20},
    "氟哌啶醇": {"eps_stiff": 0.90, "akathisia": 0.80, "tremor": 0.70, "prolactin": 0.60,
                 "sedation": 0.30, "dry_mouth": 0.30},
    "舍曲林": {"nausea": 0.50, "sexual": 0.50, "dry_mouth": 0.30, "sweating": 0.30,
               "headache": 0.25, "activation": 0.30},
    "氟西汀": {"nausea": 0.50, "sexual": 0.50, "activation": 0.50, "headache": 0.25,
               "sweating": 0.25, "insomnia": 0.30},
    "文拉法辛": {"nausea": 0.50, "sweating": 0.55, "dry_mouth": 0.35, "sexual": 0.40,
                 "orthostatic": 0.30, "headache": 0.20},
    "米氮平": {"sedation": 0.80, "appetite_up": 0.90, "weight_gain": 0.80, "dry_mouth": 0.40},
    "锂盐": {"tremor": 0.70, "polyuria": 0.80, "dry_mouth": 0.40, "weight_gain": 0.50,
             "memory": 0.30, "nausea": 0.25},
    "丙戊酸": {"weight_gain": 0.70, "appetite_up": 0.60, "tremor": 0.40, "memory": 0.20},
    "拉莫三嗪": {"rash": 0.45, "headache": 0.30, "nausea": 0.30, "orthostatic": 0.15},
    "氯硝西泮": {"sedation": 0.80, "memory": 0.60, "orthostatic": 0.40, "dry_mouth": 0.30},
    "丁螺环酮": {"nausea": 0.30, "headache": 0.35, "orthostatic": 0.15},
    "普萘洛尔": {"orthostatic": 0.50, "sedation": 0.30, "sexual": 0.20},
    "哌甲酯": {"appetite_down": 0.70, "insomnia": 0.60, "headache": 0.30, "tremor": 0.25},
    "托莫西汀": {"nausea": 0.40, "appetite_down": 0.40, "dry_mouth": 0.40, "sedation": 0.20},
    "纳曲酮": {"nausea": 0.50, "headache": 0.30, "appetite_down": 0.30},
    "褪黑素": {"sedation": 0.30, "headache": 0.20},
    "电休克": {"memory": 0.90, "headache": 0.50, "nausea": 0.40},
}

# 剂量超过 1.0 时副作用的额外放大：副作用比疗效更依赖剂量，个体化加量常先撞到副作用
DOSE_SIDE_GAIN = 0.60


def severity_zh(v: float) -> str:
    if v >= 0.75:
        return "明显"
    if v >= 0.50:
        return "中度"
    if v >= 0.25:
        return "轻微"
    return "刚出现"


def side_effects(meds: List[Dict[str, Any]], turn: int) -> List[Dict[str, Any]]:
    """当前已出现的躯体副作用，按强度降序。"""
    out: List[Dict[str, Any]] = []
    for m in meds or []:
        name = m.get("name", "")
        prof = SIDE_PROFILE.get(name)
        if not prof:
            continue
        on = turn - int(m.get("start_turn", turn))
        dose = float(m.get("dose", 1.0))
        amp = 1.0 + DOSE_SIDE_GAIN * max(0.0, dose - 1.0)
        for sid, coef in prof.items():
            meta = SIDE_DEFS.get(sid)
            if not meta:
                continue
            r = ramp(on, SIDE_ONSET.get(sid, 3.0))
            v = min(1.0, coef * min(1.0, dose) * r * amp)
            if v < 0.05:
                continue
            out.append({
                "id": sid, "zh": meta[0], "desc": meta[1], "drug": name,
                "intensity": round(v, 3), "level": severity_zh(v), "on": on,
            })
    out.sort(key=lambda d: -d["intensity"])
    return out


def sedation_level(meds: List[Dict[str, Any]], turn: int) -> float:
    """镇静深度：影响语速、句子长度与反应速度，是「主动表现」最直接的抓手。"""
    total = 0.0
    for m in meds or []:
        spec = DRUGS.get(m.get("name", ""))
        if not spec:
            continue
        sed = float(spec.get("sedation", 0.0) or 0.0)
        if sed <= 0:
            continue
        on = turn - int(m.get("start_turn", turn))
        r = ramp(on, 1.5)
        total += sed * float(m.get("dose", 1.0)) * r
    return max(0.0, min(1.0, total))


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

    # 副作用：独立成一层，只有少数几条会顺带压到症状层
    sides = side_effects(meds, turn)
    for s in sides:
        for k, v in (SIDE_SYM.get(s["id"]) or {}).items():
            sym[k] = sym.get(k, 0.0) + v * s["intensity"]

    return {"bio": bio, "sym": sym, "notes": notes,
            "side": sides, "sedation": sedation_level(meds, turn)}
