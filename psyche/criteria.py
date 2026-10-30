"""ICD-11 诊断原型库。

每一条 = 一个"诊断原型"，包含三部分证据：
1. **症状学证据**（crit）：该诊断要求的症状条目与权重，对应 ICD-11 的"必备特征"。
2. **生物学证据**（profile）：该诊断在生化/环路特征上的典型偏移方向（+ 偏高，- 偏低）。
   这不是临床诊断标准，而是本引擎用来做"多诊断鉴别"的先验，让"精分 vs 双相 vs 创伤"
   在同一组症状下也能分出高下。
3. **可治疗性**（curability）：谈话治疗对该诊断的单轮获益上限。精分 0.02、人格障碍 0.01、
   适应障碍 0.35。这是"一旦病态，靠聊天治愈可能性极低"的参数来源。

编码遵循 ICD-11 MMS（06 章 / 07 章）。带 `custom=True` 的是本引擎自建的亚临床状态，
不属官方诊断，仅用于叙事过渡（如精神病前驱期）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def D(code: str, zh: str, en: str, group: str, crit: List[tuple], *,
      min_n: int = 2, min_sev: float = 0.35,
      caps: Optional[Dict[str, float]] = None,
      profile: Optional[Dict[str, float]] = None,
      curability: float = 0.05, perf: str = "", note: str = "",
      specifiers: Optional[List[str]] = None,
      custom: bool = False, min_turns: int = 0, max_turns: int = 0,
      excludes: Optional[List[str]] = None, needs: Optional[Dict[str, int]] = None,
      acute: bool = False) -> Dict[str, Any]:
    return {
        "code": code, "zh": zh, "en": en, "group": group,
        "crit": crit, "min_n": min_n, "min_sev": min_sev,
        "caps": caps or {}, "profile": profile or {},
        "curability": curability, "perf": perf or group,
        "note": note, "specifiers": specifiers or [],
        "custom": custom, "min_turns": min_turns, "max_turns": max_turns,
        "excludes": excludes or [], "needs": needs or {}, "acute": acute,
    }


DISORDERS: List[Dict[str, Any]] = [
    # =====================================================================
    # 06 章 · 精神分裂症及其他原发性精神病性障碍 (6A20–6A2Z)
    # =====================================================================
    D("6A20", "精神分裂症", "Schizophrenia", "psychotic",
      [("ps_delusion_persecutory", 1.0), ("ps_hallucination_auditory", 0.95),
       ("ps_formal_thought_disorder", 0.90), ("ps_delusion_control", 0.85),
       ("ps_hallucination_commentary", 0.80), ("ps_thought_broadcast", 0.70),
       ("ng_affective_flattening", 0.80), ("ng_avolition", 0.70),
       ("ng_alogia", 0.65), ("ps_insight_loss", 0.75),
       ("ps_reality_testing_impair", 0.70), ("ps_word_salad", 0.60)],
      min_n=2, min_sev=0.35,
      profile={"dopamine": 1.0, "gating": -1.0, "prefrontal_control": -0.8,
               "salience": 0.8, "hippocampal_integrity": -0.5, "glutamate": 0.4,
               "default_mode": 0.4},
      curability=0.02, perf="schizophrenia",
      specifiers=["首次发作", "多次发作", "连续性", "部分缓解", "完全缓解"],
      min_turns=8,
      note="ICD-11 要求至少两项：妄想/幻觉/思维形式障碍/被动体验/阴性症状/精神运动异常/自知力丧失"),

    D("6A21", "分裂情感性障碍", "Schizoaffective disorder", "psychotic",
      [("ps_delusion_persecutory", 0.90), ("ps_hallucination_auditory", 0.85),
       ("md_depressed_mood", 0.90), ("ma_elevated_mood", 0.85),
       ("ps_formal_thought_disorder", 0.75), ("md_psychomotor_retardation", 0.55),
       ("ma_goal_activity", 0.55)],
      min_n=3, min_sev=0.38,
      profile={"dopamine": 0.8, "gating": -0.7, "serotonin": -0.6,
               "hpa_axis": 0.6, "norepinephrine": 0.5},
      curability=0.03, perf="schizophrenia", min_turns=8,
      note="精神病性症状与心境发作同时突出，且精神病性症状在心境正常期仍持续"),

    D("6A22", "分裂型障碍", "Schizotypal disorder", "psychotic",
      [("pd_psychoticism", 0.95), ("ps_delusion_reference", 0.85),
       ("pd_detachment", 0.75), ("ps_hallucination_auditory", 0.45),
       ("nd_social_communication", 0.55), ("ps_formal_thought_disorder", 0.50),
       ("ax_avoidance_social", 0.55)],
      min_n=2, min_sev=0.30,
      profile={"dopamine": 0.5, "gating": -0.5, "detachment": 0.8, "salience": 0.5},
      curability=0.02, perf="schizotypal", min_turns=30,
      note="长期存在的社交不适、认知知觉扭曲、行为古怪，不出现明确精神病性发作"),

    D("6A23", "急性短暂性精神病性障碍", "Acute and transient psychotic disorder", "psychotic",
      [("ps_hallucination_auditory", 0.90), ("ps_delusion_persecutory", 0.90),
       ("ps_formal_thought_disorder", 0.80), ("ax_panic_attack", 0.55),
       ("ps_reality_testing_impair", 0.75), ("di_derealization", 0.55)],
      min_n=2, min_sev=0.42,
      profile={"dopamine": 0.9, "gating": -0.8, "hpa_axis": 0.8, "norepinephrine": 0.7},
      curability=0.12, perf="brief_psychotic", min_turns=0, max_turns=60, acute=True,
      note="急性起病（数天），症状多变，通常在数周内缓解；预后显著优于精分"),

    D("6A24", "妄想障碍", "Delusional disorder", "psychotic",
      [("ps_delusion_persecutory", 1.0), ("ps_delusion_jealousy", 0.80),
       ("ps_delusion_erotomanic", 0.75), ("ps_delusion_somatic", 0.75),
       ("ps_delusion_grandiose", 0.70), ("ps_delusion_reference", 0.65)],
      min_n=1, min_sev=0.55,
      caps={"ps_hallucination_auditory": 0.35, "ps_formal_thought_disorder": 0.40},
      profile={"dopamine": 0.5, "gating": -0.3, "prefrontal_control": -0.3},
      curability=0.03, perf="delusional", min_turns=20,
      note="一种或多种妄想持续 ≥3 个月，除妄想及其直接后果外功能相对保留，无明显幻觉"),

    D("6A25", "症状性精神病性障碍", "Secondary psychotic syndrome", "psychotic",
      [("ps_hallucination_visual", 0.85), ("cg_consciousness_fluctuation", 0.85),
       ("ps_delusion_persecutory", 0.70), ("cg_disorientation", 0.75),
       ("su_intoxication", 0.60)],
      min_n=1, min_sev=0.40,
      profile={"inflammation": 0.9, "hpa_axis": 0.6, "gating": -0.7},
      curability=0.10, perf="secondary_psychotic", min_turns=0, max_turns=40, acute=True,
      note="由物质、药物或躯体疾病直接所致；视幻觉与意识波动更突出"),

    D("6A40", "紧张症", "Catatonia", "psychotic",
      [("cg_stupor", 0.95), ("cg_waxy_flexibility", 0.90), ("cg_negativism", 0.85),
       ("ng_psychomotor_poverty", 0.80), ("ps_perseveration", 0.60), ("ng_alogia", 0.65)],
      # ICD-11 6A40 要求「3 项及以上」症状同时存在。min_n=2 会让长期受辱
      # 攒出的「木僵 + 精神运动性贫乏」两条直接确诊——实测被骂 80 轮的健康人
      # 就是这样被判成紧张症的。
      min_n=3, min_sev=0.62,
      profile={"gaba": -0.9, "glutamate": 0.4, "dopamine": -0.5},
      curability=0.20, perf="catatonia", min_turns=0, max_turns=80, acute=True,
      note="木僵、蜡样屈曲、违拗、刻板；对苯二氮䓬类/ECT 反应好"),

    D("6A2Z-UHR", "精神病高风险状态（前驱期）", "At-risk mental state (prodromal)", "psychotic",
      [("pd_psychoticism", 0.85), ("ps_delusion_reference", 0.65),
       ("ps_hallucination_auditory", 0.40), ("ax_hypervigilance", 0.60),
       ("di_derealization", 0.50), ("ng_avolition", 0.45)],
      min_n=2, min_sev=0.25,
      profile={"dopamine": 0.4, "gating": -0.4, "salience": 0.4},
      curability=0.15, perf="prodromal", custom=True, min_turns=0,
      note="亚临床状态，不属官方诊断；用于病程过渡与「尚未断病」的叙事"),

    # =====================================================================
    # 06 章 · 心境障碍 (6A60–6A8Z)
    # =====================================================================
    D("6A60", "双相I型障碍", "Bipolar type I disorder", "bipolar",
      [("ma_elevated_mood", 0.95), ("ma_goal_activity", 0.85), ("ma_decreased_sleep", 0.85),
       ("ma_pressured_speech", 0.75), ("ma_grandiosity", 0.75), ("ma_flight_of_ideas", 0.75),
       ("ma_impulsivity", 0.70), ("md_depressed_mood", 0.60)],
      min_n=3, min_sev=0.38,
      profile={"dopamine": 1.0, "norepinephrine": 0.8, "gaba": -0.6,
               "serotonin": -0.3, "sleep_debt": 0.8},
      curability=0.02, perf="mania", min_turns=0,
      note="至少一次躁狂发作；躁狂期需持续 ≥1 周或需住院"),

    D("6A61", "双相II型障碍", "Bipolar type II disorder", "bipolar",
      [("md_depressed_mood", 0.90), ("md_anhedonia", 0.75), ("md_fatigue", 0.65),
       ("ma_elevated_mood", 0.55), ("ma_decreased_sleep", 0.55), ("ma_goal_activity", 0.50),
       ("md_insomnia", 0.55)],
      min_n=3, min_sev=0.33,
      caps={"ma_elevated_mood": 0.62, "ma_goal_activity": 0.60},
      profile={"serotonin": -0.8, "dopamine": 0.2, "hpa_axis": 0.6},
      curability=0.03, perf="bipolar_ii", min_turns=0, excludes=["6A60", "6A70", "6A71"],
      note="抑郁发作 + 轻躁狂发作（不达躁狂程度）"),

    D("6A62", "环性心境障碍", "Cyclothymic disorder", "bipolar",
      [("md_depressed_mood", 0.65), ("ma_elevated_mood", 0.65), ("md_insomnia", 0.50),
       ("ma_irritability", 0.55), ("md_fatigue", 0.50)],
      min_n=2, min_sev=0.25,
      caps={"ma_elevated_mood": 0.55, "md_depressed_mood": 0.55},
      profile={"serotonin": -0.4, "dopamine": 0.2},
      curability=0.05, perf="cyclothymia", min_turns=40,
      note="持续 ≥2 年的心境波动，幅度不足以构成完整发作"),

    D("6A70", "单次抑郁发作", "Single episode depressive disorder", "mood",
      [("md_depressed_mood", 0.95), ("md_anhedonia", 0.90), ("md_fatigue", 0.75),
       ("md_worthlessness", 0.70), ("md_insomnia", 0.65), ("md_concentration", 0.65),
       ("md_hopelessness", 0.60), ("md_psychomotor_retardation", 0.55),
       ("md_appetite_loss", 0.55), ("md_guilt", 0.55), ("md_suicidal_ideation", 0.70)],
      min_n=3, min_sev=0.32,
      profile={"serotonin": -1.0, "norepinephrine": -0.7, "dopamine": -0.6,
               "hpa_axis": 0.8, "neuroplasticity": -0.8, "inflammation": 0.5,
               "default_mode": 0.6},
      curability=0.18, perf="depression", min_turns=4, excludes=["6A60", "6A61", "6A71"],
      note="心境低落或兴趣丧失，伴认知与躯体症状，持续 ≥2 周"),

    D("6A71", "复发性抑郁障碍", "Recurrent depressive disorder", "mood",
      [("md_depressed_mood", 0.95), ("md_anhedonia", 0.90), ("md_fatigue", 0.75),
       ("md_worthlessness", 0.70), ("md_hopelessness", 0.70), ("md_insomnia", 0.65),
       ("md_concentration", 0.60), ("md_suicidal_ideation", 0.65)],
      min_n=3, min_sev=0.32,
      profile={"serotonin": -1.0, "norepinephrine": -0.6, "hpa_axis": 0.8,
               "neuroplasticity": -0.7, "default_mode": 0.7},
      curability=0.10, perf="depression", min_turns=40, needs={"episodes_min": 2},
      excludes=["6A60", "6A61", "6A70"],
      note="两次以上抑郁发作，间隔至少数月"),

    D("6A72", "恶劣心境障碍", "Dysthymic disorder", "mood",
      [("md_depressed_mood", 0.75), ("md_fatigue", 0.65), ("md_hopelessness", 0.65),
       ("md_worthlessness", 0.55), ("md_concentration", 0.55), ("md_insomnia", 0.50)],
      min_n=2, min_sev=0.22,
      caps={"md_depressed_mood": 0.56},
      profile={"serotonin": -0.6, "hpa_axis": 0.4, "dopamine": -0.3},
      curability=0.08, perf="dysthymia", min_turns=60,
      note="长期（≥2 年）低度抑郁，很少完全缓解"),

    D("6A73", "混合性抑郁焦虑障碍", "Mixed depressive and anxiety disorder", "mood",
      [("md_depressed_mood", 0.80), ("ax_worry", 0.80), ("ax_restlessness", 0.65),
       ("md_insomnia", 0.60), ("md_concentration", 0.55), ("ax_muscle_tension", 0.50)],
      min_n=3, min_sev=0.30,
      profile={"serotonin": -0.7, "norepinephrine": 0.5, "hpa_axis": 0.7},
      curability=0.20, perf="mixed", min_turns=4, excludes=["6B00", "6A70", "6A71"],
      note="抑郁与焦虑症状同时突出，但均未达到各自独立诊断的完整标准"),

    D("6A80", "经前期烦躁障碍", "Premenstrual dysphoric disorder", "mood",
      [("md_depressed_mood", 0.70), ("ma_irritability", 0.80),
       ("ax_worry", 0.60), ("md_fatigue", 0.55), ("md_appetite_gain", 0.45)],
      min_n=2, min_sev=0.25,
      profile={"serotonin": -0.5, "allopregnanolone": -0.7},
      curability=0.15, perf="pmdd", min_turns=0,
      note="黄体期出现、月经后缓解；与神经类固醇波动相关"),

    # =====================================================================
    # 06 章 · 焦虑及恐惧相关障碍 (6B00–6B0Z)
    # =====================================================================
    D("6B00", "广泛性焦虑障碍", "Generalised anxiety disorder", "anxiety",
      [("ax_worry", 0.95), ("ax_restlessness", 0.75), ("ax_muscle_tension", 0.70),
       ("ax_somatic", 0.65), ("ax_hypervigilance", 0.60), ("md_insomnia", 0.55),
       ("md_concentration", 0.50)],
      min_n=3, min_sev=0.30,
      profile={"norepinephrine": 0.7, "gaba": -0.7, "hpa_axis": 0.6,
               "threat_reactivity": 0.6, "autonomic_flex": -0.6},
      curability=0.16, perf="anxiety", min_turns=10,
      note="持续 ≥6 个月的漂浮性焦虑与过度担忧，伴运动性紧张与自主神经亢进"),

    D("6B01", "惊恐障碍", "Panic disorder", "anxiety",
      [("ax_panic_attack", 0.95), ("ax_anticipatory_anxiety", 0.85), ("ax_somatic", 0.80),
       ("ax_avoidance_agora", 0.55), ("ax_hypervigilance", 0.55)],
      min_n=2, min_sev=0.38,
      profile={"norepinephrine": 0.9, "gaba": -0.8, "hpa_axis": 0.8,
               "autonomic_flex": -0.8, "arousal": 0.9},
      curability=0.22, perf="panic", min_turns=2,
      note="反复的、不可预期的惊恐发作，伴持续担心再次发作"),

    D("6B02", "广场恐惧", "Agoraphobia", "anxiety",
      [("ax_avoidance_agora", 0.95), ("ax_anticipatory_anxiety", 0.70),
       ("ax_somatic", 0.55), ("ax_panic_attack", 0.50)],
      min_n=2, min_sev=0.30,
      profile={"norepinephrine": 0.5, "gaba": -0.5, "autonomic_flex": -0.5},
      curability=0.18, perf="agoraphobia", min_turns=8,
      note="对难以逃离或求助无门的场所显著恐惧并回避"),

    D("6B03", "特定恐惧症", "Specific phobia", "anxiety",
      [("ax_avoidance_specific", 0.95), ("ax_anticipatory_anxiety", 0.60), ("ax_somatic", 0.45)],
      min_n=2, min_sev=0.30,
      profile={"threat_reactivity": 0.6, "gaba": -0.3},
      curability=0.30, perf="phobia", min_turns=6,
      note="对特定对象/情境的显著恐惧，与实际危险不相称"),

    D("6B04", "社交焦虑障碍", "Social anxiety disorder", "anxiety",
      [("ax_avoidance_social", 0.95), ("ax_anticipatory_anxiety", 0.75),
       ("ax_somatic", 0.60), ("tr_shame", 0.60), ("md_worthlessness", 0.45),
       ("ax_hypervigilance", 0.55)],
      min_n=2, min_sev=0.30,
      profile={"norepinephrine": 0.5, "serotonin": -0.4, "threat_reactivity": 0.7,
               "oxytocin": -0.4},
      curability=0.20, perf="social_anxiety", min_turns=8,
      note="对负性评价的持续恐惧，回避社交或带着强烈痛苦忍受"),

    D("6B05", "分离焦虑障碍", "Separation anxiety disorder", "anxiety",
      [("ax_separation", 0.95), ("tr_abandonment_fear", 0.80), ("ax_avoidance_social", 0.40),
       ("ax_somatic", 0.45)],
      min_n=2, min_sev=0.30,
      profile={"oxytocin": -0.5, "threat_reactivity": 0.5, "hpa_axis": 0.5},
      curability=0.22, perf="separation", min_turns=6,
      note="对依恋对象分离的过度恐惧，可见于成人"),

    D("6B06", "选择性缄默", "Selective mutism", "anxiety",
      [("ax_selective_mutism", 0.95), ("ax_avoidance_social", 0.70), ("ax_somatic", 0.35)],
      min_n=2, min_sev=0.35,
      profile={"gaba": -0.4, "threat_reactivity": 0.6},
      curability=0.20, perf="mutism", min_turns=8,
      note="在特定社交场合持续无法说话，其他场合语言正常"),

    # =====================================================================
    # 06 章 · 强迫及相关障碍 (6B20–6B2Z)
    # =====================================================================
    D("6B20", "强迫症", "Obsessive-compulsive disorder", "ocd",
      [("oc_obsession_contamination", 0.85), ("oc_obsession_harm", 0.80),
       ("oc_obsession_symmetry", 0.70), ("oc_compulsion_checking", 0.85),
       ("oc_compulsion_washing", 0.75), ("oc_mental_ritual", 0.65),
       ("oc_insight", 0.55), ("ax_worry", 0.55)],
      min_n=2, min_sev=0.35,
      profile={"serotonin": -0.9, "striatal_gain": 1.0, "prefrontal_control": -0.5,
               "gaba": -0.3},
      curability=0.04, perf="ocd", min_turns=10,
      note="反复侵入的强迫思维与/或仪式行为，耗时或引起显著痛苦"),

    D("6B21", "躯体变形障碍", "Body dysmorphic disorder", "ocd",
      [("oc_body_dysmorphic", 0.95), ("oc_compulsion_checking", 0.60),
       ("tr_shame", 0.65), ("ax_avoidance_social", 0.55), ("md_depressed_mood", 0.45)],
      min_n=2, min_sev=0.35,
      profile={"serotonin": -0.7, "striatal_gain": 0.6, "interoception": 0.6},
      curability=0.06, perf="dysmorphic", min_turns=12,
      note="对想象的外观缺陷过度先占，反复检查或修饰"),

    D("6B22", "嗅觉参照障碍", "Olfactory reference syndrome", "ocd",
      [("oc_body_dysmorphic", 0.60), ("ps_delusion_reference", 0.75),
       ("ax_avoidance_social", 0.65), ("tr_shame", 0.80)],
      min_n=2, min_sev=0.35,
      profile={"serotonin": -0.5, "striatal_gain": 0.5},
      curability=0.06, perf="olfactory", min_turns=12,
      note="坚信自己散发异味并因此羞耻、回避"),

    D("6B23", "疑病症（疾病焦虑障碍）", "Hypochondriasis (health anxiety disorder)", "ocd",
      [("oc_health_anxiety", 0.95), ("so_health_preoccupation", 0.85),
       ("so_somatic_complaint", 0.60), ("ax_worry", 0.60), ("oc_compulsion_checking", 0.55)],
      min_n=2, min_sev=0.33,
      profile={"interoception": 0.9, "serotonin": -0.5, "hpa_axis": 0.4},
      curability=0.10, perf="health_anxiety", min_turns=10,
      note="持续担心患重病，反复检查或求医， reassurance 只能短暂缓解"),

    D("6B24", "囤积障碍", "Hoarding disorder", "ocd",
      [("oc_hoarding", 0.95), ("oc_obsession_symmetry", 0.45), ("pd_anankastia", 0.50)],
      min_n=2, min_sev=0.30,
      profile={"striatal_gain": 0.4, "anankastia": 0.7},
      curability=0.05, perf="hoarding", min_turns=30,
      note="持续难以丢弃物品，导致生活空间拥挤与功能受损"),

    D("6B25.0", "拔毛障碍", "Trichotillomania", "ocd",
      [("oc_trichotillomania", 0.95), ("ax_restlessness", 0.45), ("tr_shame", 0.55)],
      min_n=2, min_sev=0.30,
      profile={"striatal_gain": 0.6, "serotonin": -0.4},
      curability=0.08, perf="bfrb", min_turns=6,
      note="反复拔除毛发，多次尝试停止失败"),

    D("6B25.1", "皮肤搔抓障碍", "Excoriation (skin-picking) disorder", "ocd",
      [("oc_skin_picking", 0.95), ("ax_restlessness", 0.40), ("tr_shame", 0.55)],
      min_n=2, min_sev=0.30,
      profile={"striatal_gain": 0.6, "serotonin": -0.4},
      curability=0.08, perf="bfrb", min_turns=6,
      note="反复抠抓皮肤致组织损伤"),

    # =====================================================================
    # 06 章 · 应激相关障碍 (6B40–6B4Z)
    # =====================================================================
    D("6B40", "创伤后应激障碍", "Post-traumatic stress disorder", "stress",
      [("tr_flashback", 0.95), ("tr_intrusion", 0.90), ("tr_nightmare", 0.80),
       ("tr_avoidance", 0.85), ("tr_hyperarousal", 0.85), ("tr_startle", 0.75),
       ("tr_negative_cognition", 0.65), ("ax_hypervigilance", 0.70)],
      min_n=3, min_sev=0.35,
      profile={"threat_reactivity": 1.0, "prefrontal_control": -0.6,
               "hippocampal_integrity": -0.7, "norepinephrine": 0.8,
               "hpa_axis": -0.3, "autonomic_flex": -0.7},
      curability=0.06, perf="ptsd", min_turns=6,
      note="暴露于创伤事件后出现侵入、回避、负性认知与唤醒增高，持续 ≥1 个月"),

    D("6B41", "复杂性创伤后应激障碍", "Complex PTSD", "stress",
      [("tr_flashback", 0.85), ("tr_emotional_dysregulation", 0.90),
       ("tr_identity_diffusion", 0.85), ("tr_abandonment_fear", 0.75),
       ("tr_shame", 0.80), ("tr_avoidance", 0.70), ("pd_emptiness", 0.60),
       ("di_depersonalization", 0.55)],
      min_n=3, min_sev=0.35,
      profile={"threat_reactivity": 0.9, "prefrontal_control": -0.7,
               "hippocampal_integrity": -0.6, "oxytocin": -0.6, "allostatic_load": 0.7},
      curability=0.04, perf="cptsd", min_turns=20,
      note="PTSD 核心症状 + 情感调节困难、自我认同弥散、人际关系障碍"),

    D("6B42", "延长哀伤障碍", "Prolonged grief disorder", "stress",
      [("ot_bereavement", 0.95), ("tr_grief", 0.90), ("md_depressed_mood", 0.65),
       ("ng_asociality", 0.55), ("tr_identity_diffusion", 0.50)],
      min_n=2, min_sev=0.32,
      profile={"serotonin": -0.5, "hpa_axis": 0.5, "default_mode": 0.6},
      curability=0.12, perf="grief", min_turns=24,
      note="丧失后持续 ≥6 个月的强烈思念与功能受损"),

    D("6B43", "适应障碍", "Adjustment disorder", "stress",
      [("ax_worry", 0.75), ("md_depressed_mood", 0.75), ("md_insomnia", 0.55),
       ("md_concentration", 0.50), ("tr_emotional_dysregulation", 0.45)],
      min_n=2, min_sev=0.22,
      caps={"md_depressed_mood": 0.68, "ax_worry": 0.68},
      profile={"hpa_axis": 0.5, "norepinephrine": 0.4},
      curability=0.35, perf="adjustment", min_turns=2,
      excludes=["6B00", "6A70", "6A71", "6B20"], acute=True,
      note="对可识别的应激源产生情绪与行为反应，通常在 6 个月内缓解；预后最好"),

    D("6B44", "反应性依恋障碍", "Reactive attachment disorder", "stress",
      [("pd_detachment", 0.85), ("tr_emotional_dysregulation", 0.70),
       ("ng_asociality", 0.80), ("ax_separation", 0.40)],
      min_n=2, min_sev=0.35,
      profile={"oxytocin": -0.9, "detachment": 0.9},
      curability=0.05, perf="attachment", min_turns=40,
      note="早期严重忽视后形成的持续退缩与情绪抑制"),

    D("6B45", "脱抑制性社会参与障碍", "Disinhibited social engagement disorder", "stress",
      [("pd_disinhibition", 0.80), ("nd_social_communication", 0.55),
       ("pd_intimacy_deficit", 0.60), ("tr_emotional_dysregulation", 0.50)],
      min_n=2, min_sev=0.30,
      profile={"oxytocin": -0.5, "prefrontal_control": -0.6},
      curability=0.05, perf="attachment", min_turns=40,
      note="对陌生人过度亲近、缺乏边界"),

    # =====================================================================
    # 06 章 · 分离障碍 (6B60–6B6Z)
    # =====================================================================
    D("6B60", "分离性神经症状障碍", "Dissociative neurological symptom disorder", "dissociative",
      [("di_conversion", 0.95), ("di_trance", 0.45), ("ax_somatic", 0.50),
       ("cg_memory_deficit", 0.35)],
      min_n=2, min_sev=0.35,
      profile={"prefrontal_control": -0.6, "autonomic_flex": -0.4},
      curability=0.12, perf="conversion", min_turns=4,
      note="无器质性基础的的运动/感觉/抽搐症状，与心理因素相关"),

    D("6B61", "分离性遗忘", "Dissociative amnesia", "dissociative",
      [("di_amnesia", 0.95), ("cg_memory_deficit", 0.60), ("di_depersonalization", 0.40)],
      min_n=2, min_sev=0.40,
      profile={"hippocampal_integrity": -0.4, "prefrontal_control": -0.4},
      curability=0.14, perf="amnesia", min_turns=3,
      note="无法回忆重要个人信息，非普通遗忘，常与创伤相关"),

    D("6B62", "出神障碍", "Trance disorder", "dissociative",
      [("di_trance", 0.95), ("di_derealization", 0.55), ("ng_attention_deficit", 0.45)],
      min_n=2, min_sev=0.40,
      profile={"dmn": 0.7, "prefrontal_control": -0.5},
      curability=0.10, perf="trance", min_turns=4,
      note="短暂的意识状态改变，对外界刺激反应性下降"),

    D("6B64", "分离性身份障碍", "Dissociative identity disorder", "dissociative",
      [("di_identity_fragmentation", 0.95), ("di_amnesia", 0.80),
       ("tr_identity_diffusion", 0.75), ("di_depersonalization", 0.60),
       ("pd_identity_problems", 0.65)],
      min_n=3, min_sev=0.40,
      profile={"hippocampal_integrity": -0.6, "prefrontal_control": -0.6, "allostatic_load": 0.6},
      curability=0.03, perf="did", min_turns=30,
      note="两个或多个身份状态交替接管，伴反复遗忘"),

    D("6B66", "人格解体-现实解体障碍", "Depersonalization-derealization disorder", "dissociative",
      [("di_depersonalization", 0.95), ("di_derealization", 0.95),
       ("ax_hypervigilance", 0.45), ("md_anhedonia", 0.40)],
      min_n=2, min_sev=0.35,
      profile={"interoception": -0.8, "insula": -0.5, "threat_reactivity": 0.5},
      curability=0.08, perf="depersonalization", min_turns=6,
      note="持续的自我感丧失与不真实感，现实检验完整"),

    # =====================================================================
    # 06 章 · 喂食与进食障碍 (6B80–6B8Z)
    # =====================================================================
    D("6B80", "神经性厌食", "Anorexia nervosa", "eating",
      [("ea_restriction", 0.95), ("ea_body_image_distortion", 0.90), ("ea_low_weight", 0.85),
       ("ea_fear_weight_gain", 0.85), ("ea_purge", 0.45), ("oc_obsession_symmetry", 0.40)],
      min_n=2, min_sev=0.35,
      profile={"serotonin": -0.6, "leptin": -0.8, "striatal_gain": 0.6, "anankastia": 0.8},
      curability=0.03, perf="anorexia", min_turns=20,
      note="显著低体重 + 强烈怕胖 + 体像扭曲；死亡率在精神障碍中最高"),

    D("6B81", "神经性贪食", "Bulimia nervosa", "eating",
      [("ea_binge", 0.90), ("ea_purge", 0.90), ("ea_body_image_distortion", 0.70),
       ("tr_shame", 0.65), ("md_depressed_mood", 0.50)],
      min_n=2, min_sev=0.33,
      profile={"serotonin": -0.7, "dopamine": -0.3, "striatal_gain": 0.5},
      curability=0.06, perf="bulimia", min_turns=12,
      note="反复暴食与补偿行为（催吐/泻药/过度运动）"),

    D("6B82", "暴食障碍", "Binge eating disorder", "eating",
      [("ea_binge", 0.95), ("md_depressed_mood", 0.50), ("tr_shame", 0.55),
       ("md_appetite_gain", 0.45)],
      min_n=2, min_sev=0.30,
      profile={"serotonin": -0.5, "dopamine": -0.3},
      curability=0.10, perf="binge", min_turns=8,
      note="反复暴食但无规律性补偿行为"),

    D("6B83", "回避-限制性摄食障碍", "Avoidant-restrictive food intake disorder", "eating",
      [("ea_restriction", 0.85), ("ea_low_weight", 0.55), ("nd_sensory_hyper", 0.55),
       ("ea_fear_weight_gain", 0.20)],
      min_n=2, min_sev=0.28,
      caps={"ea_fear_weight_gain": 0.30, "ea_body_image_distortion": 0.25},
      profile={"interoception": 0.4},
      curability=0.12, perf="arfid", min_turns=8,
      note="因感官/恐惧/兴趣缺乏而限制进食，不伴体像扭曲"),

    # =====================================================================
    # 06 章 · 躯体痛苦与躯体体验障碍 (6C20–6C2Z)
    # =====================================================================
    D("6C20", "躯体痛苦障碍", "Bodily distress disorder", "bodily",
      [("so_somatic_complaint", 0.95), ("so_medically_unexplained", 0.80),
       ("so_health_preoccupation", 0.75), ("ax_worry", 0.65), ("md_depressed_mood", 0.40)],
      min_n=2, min_sev=0.30,
      profile={"interoception": 0.9, "hpa_axis": 0.5, "inflammation": 0.5},
      curability=0.10, perf="bodily", min_turns=10,
      note="多系统躯体主诉与对健康的过度关注，医学检查无法充分解释"),

    D("6C21", "身体完整性烦恼", "Body integrity dysphoria", "bodily",
      [("oc_body_dysmorphic", 0.55), ("ot_personality_change", 0.30), ("md_depressed_mood", 0.40)],
      min_n=1, min_sev=0.30,
      profile={"interoception": -0.6},
      curability=0.05, perf="bodily", min_turns=20,
      note="对自身身体某部分持续不适，渴望其缺失或改变"),

    # =====================================================================
    # 06 章 · 物质使用与成瘾行为 (6C40–6C5Z)
    # =====================================================================
    D("6C40", "酒精使用障碍", "Alcohol use disorder", "substance",
      [("su_craving", 0.90), ("su_control_loss", 0.90), ("su_tolerance", 0.80),
       ("su_withdrawal", 0.80), ("su_continue_harm", 0.75), ("su_intoxication", 0.55)],
      min_n=3, min_sev=0.33,
      profile={"gaba": -0.6, "glutamate": 0.5, "dopamine": -0.4, "inflammation": 0.5},
      curability=0.03, perf="substance", min_turns=20,
      note="酒精依赖：耐受、戒断、失控、明知有害仍继续"),

    D("6C43", "阿片类使用障碍", "Opioid use disorder", "substance",
      [("su_craving", 0.95), ("su_tolerance", 0.90), ("su_withdrawal", 0.90),
       ("su_control_loss", 0.85), ("su_continue_harm", 0.70)],
      min_n=3, min_sev=0.36,
      profile={"endorphin": -0.8, "dopamine": -0.5},
      curability=0.02, perf="substance", min_turns=20,
      note="耐受与戒断极显著，渴求强烈"),

    D("6C46", "兴奋剂使用障碍", "Stimulant use disorder", "substance",
      [("su_craving", 0.90), ("su_tolerance", 0.80), ("su_control_loss", 0.80),
       ("ma_elevated_mood", 0.55), ("ps_delusion_persecutory", 0.55), ("su_withdrawal", 0.70)],
      min_n=3, min_sev=0.33,
      profile={"dopamine": 0.8, "norepinephrine": 0.8, "gating": -0.6},
      curability=0.03, perf="substance", min_turns=15,
      note="可致中毒性精神病性症状与戒断性抑郁"),

    D("6C4A", "尼古丁使用障碍", "Nicotine use disorder", "substance",
      [("su_craving", 0.85), ("su_withdrawal", 0.80), ("su_control_loss", 0.60),
       ("su_tolerance", 0.55)],
      min_n=2, min_sev=0.25,
      profile={"acetylcholine": 0.5, "dopamine": 0.2},
      curability=0.04, perf="substance", min_turns=15,
      note="依赖性强，戒断以易激惹与注意下降为主"),

    # =====================================================================
    # 06 章 · 冲动控制障碍 (6C70–6C7Z)
    # =====================================================================
    D("6C50", "赌博障碍", "Gambling disorder", "impulse",
      [("ic_gambling", 0.95), ("ma_impulsivity", 0.65), ("md_depressed_mood", 0.50),
       ("pd_disinhibition", 0.55), ("md_hopelessness", 0.40)],
      min_n=2, min_sev=0.32,
      profile={"dopamine": 0.7, "prefrontal_control": -0.5, "serotonin": -0.3},
      curability=0.05, perf="gambling", min_turns=10,
      note="反复赌博、追损、失控，导致财务与人际损害"),

    D("6C51", "游戏障碍", "Gaming disorder", "impulse",
      [("ic_gaming", 0.95), ("sl_circadian_shift", 0.65), ("ng_asociality", 0.60),
       ("nd_inattention", 0.50), ("md_depressed_mood", 0.45)],
      min_n=2, min_sev=0.30,
      profile={"dopamine": 0.5, "prefrontal_control": -0.4},
      curability=0.08, perf="gaming", min_turns=12,
      note="游戏优先于其他生活兴趣，持续 ≥12 个月并造成显著损害"),

    D("6C72", "强迫性性行为障碍", "Compulsive sexual behaviour disorder", "impulse",
      [("ic_compulsive_sexual", 0.95), ("tr_shame", 0.65), ("ma_impulsivity", 0.50),
       ("md_depressed_mood", 0.40)],
      min_n=2, min_sev=0.32,
      profile={"dopamine": 0.6, "prefrontal_control": -0.5},
      curability=0.06, perf="compulsive_sexual", min_turns=12,
      note="反复无法控制的性行为，成为生活重心并造成损害"),

    D("6C73", "间歇性暴怒障碍", "Intermittent explosive disorder", "impulse",
      [("ic_anger_outburst", 0.95), ("pd_rage", 0.80), ("ma_irritability", 0.65),
       ("pd_disinhibition", 0.55)],
      min_n=2, min_sev=0.35,
      profile={"serotonin": -0.7, "prefrontal_control": -0.6, "testosterone": 0.5},
      curability=0.08, perf="anger", min_turns=6,
      note="反复的冲动性攻击爆发，与刺激不成比例，事后后悔"),

    # =====================================================================
    # 06 章 · 人格障碍及相关特质 (6D10–6D11)
    # =====================================================================
    D("6D10.0", "人格障碍（轻度）", "Personality disorder, mild", "personality",
      [("pd_identity_problems", 0.55), ("pd_self_direction_deficit", 0.50),
       ("pd_intimacy_deficit", 0.50), ("pd_empathy_deficit", 0.35),
       ("tr_emotional_dysregulation", 0.40)],
      min_n=2, min_sev=0.25,
      profile={"allostatic_load": 0.3},
      curability=0.03, perf="personality", min_turns=60,
      note="人格功能轻度受损，在部分领域可维持适应"),

    D("6D10.1", "人格障碍（中度）", "Personality disorder, moderate", "personality",
      [("pd_identity_problems", 0.75), ("pd_self_direction_deficit", 0.70),
       ("pd_intimacy_deficit", 0.70), ("pd_empathy_deficit", 0.55),
       ("tr_emotional_dysregulation", 0.60)],
      min_n=3, min_sev=0.32,
      profile={"allostatic_load": 0.5},
      curability=0.02, perf="personality", min_turns=60,
      note="多个领域人格功能显著受损"),

    D("6D10.2", "人格障碍（重度）", "Personality disorder, severe", "personality",
      [("pd_identity_problems", 0.90), ("pd_self_direction_deficit", 0.85),
       ("pd_intimacy_deficit", 0.85), ("pd_empathy_deficit", 0.75),
       ("tr_emotional_dysregulation", 0.80), ("pd_emptiness", 0.70)],
      min_n=4, min_sev=0.38,
      profile={"allostatic_load": 0.7, "prefrontal_control": -0.5},
      curability=0.01, perf="personality", min_turns=60,
      note="人格功能全面严重受损，社会角色难以维持"),

    D("6D11.0", "显著负性情感特质", "Prominent negative affectivity", "personality",
      [("pd_negative_affectivity", 0.95), ("ax_worry", 0.65), ("md_depressed_mood", 0.55),
       ("tr_emotional_dysregulation", 0.55)],
      min_n=2, min_sev=0.30,
      profile={"serotonin": -0.5, "hpa_axis": 0.5, "threat_reactivity": 0.6},
      curability=0.04, perf="trait_na", min_turns=40,
      note="长期焦虑、抑郁、自我贬低、敌意"),

    D("6D11.1", "显著疏离特质", "Prominent detachment", "personality",
      [("pd_detachment", 0.95), ("ng_asociality", 0.70), ("pd_intimacy_deficit", 0.65)],
      min_n=2, min_sev=0.30,
      profile={"oxytocin": -0.7, "dopamine": -0.4},
      curability=0.03, perf="trait_det", min_turns=40,
      note="情感冷淡、社交回避、亲密关系困难"),

    D("6D11.2", "显著反社会特质", "Prominent dissociality", "personality",
      [("pd_dissociality", 0.95), ("pd_empathy_deficit", 0.80), ("pd_manipulativeness", 0.65),
       ("ma_impulsivity", 0.50)],
      min_n=2, min_sev=0.32,
      profile={"prefrontal_control": -0.6, "oxytocin": -0.6, "testosterone": 0.5},
      curability=0.01, perf="trait_dissocial", min_turns=40,
      note="无视他人权利与感受，缺乏悔意"),

    D("6D11.3", "显著解抑制特质", "Prominent disinhibition", "personality",
      [("pd_disinhibition", 0.95), ("ma_impulsivity", 0.70), ("ic_anger_outburst", 0.50)],
      min_n=2, min_sev=0.30,
      profile={"prefrontal_control": -0.7, "dopamine": 0.4},
      curability=0.03, perf="trait_dis", min_turns=40,
      note="冲动、冒险、不顾后果、计划性差"),

    D("6D11.4", "显著强迫性特质", "Prominent anankastia", "personality",
      [("pd_anankastia", 0.95), ("oc_obsession_symmetry", 0.60), ("oc_compulsion_ordering", 0.55)],
      min_n=2, min_sev=0.30,
      profile={"striatal_gain": 0.5, "serotonin": -0.3},
      curability=0.03, perf="trait_anank", min_turns=40,
      note="完美主义、刻板、控制他人、难以变通"),

    D("6D11.5", "边缘型模式", "Borderline pattern", "personality",
      [("pd_borderline_pattern", 0.95), ("tr_abandonment_fear", 0.90),
       ("pd_emptiness", 0.80), ("pd_idealize_devalue", 0.75), ("pd_rage", 0.70),
       ("pd_self_harm_urge", 0.75), ("tr_identity_diffusion", 0.70)],
      min_n=3, min_sev=0.35,
      profile={"serotonin": -0.8, "threat_reactivity": 0.8, "prefrontal_control": -0.6,
               "oxytocin": -0.7, "allostatic_load": 0.6},
      curability=0.02, perf="borderline", min_turns=40,
      note="关系、自我、情绪极度不稳定 + 冲动 + 被抛弃恐惧；可伴自伤（叙事不描写方式）"),

    # =====================================================================
    # 06 章 · 神经发育障碍 (6A00–6A0Z)
    # =====================================================================
    D("6A02", "孤独症谱系障碍", "Autism spectrum disorder", "neurodev",
      [("nd_social_communication", 0.95), ("nd_restricted_repetitive", 0.90),
       ("nd_sensory_hyper", 0.75), ("pd_empathy_deficit", 0.50)],
      min_n=2, min_sev=0.32,
      profile={"oxytocin": -0.5, "salience": 0.3, "prefrontal_control": -0.2},
      curability=0.01, perf="asd", min_turns=100,
      note="社交沟通缺陷 + 限制重复行为/兴趣，发育早期起病"),

    D("6A05", "注意缺陷多动障碍", "Attention deficit hyperactivity disorder", "neurodev",
      [("nd_inattention", 0.90), ("nd_hyperactivity", 0.80), ("nd_impulsivity", 0.80),
       ("cg_executive_deficit", 0.55)],
      min_n=2, min_sev=0.30,
      profile={"dopamine": -0.6, "norepinephrine": -0.4, "prefrontal_control": -0.8},
      curability=0.02, perf="adhd", min_turns=100,
      note="持续注意困难与/或多动冲动，跨情境存在"),

    # =====================================================================
    # 06 章 · 神经认知障碍 (6D70–6E0Z)
    # =====================================================================
    D("6D70", "谵妄", "Delirium", "neurocognitive",
      [("cg_consciousness_fluctuation", 0.95), ("cg_disorientation", 0.90),
       ("ps_hallucination_visual", 0.70), ("cg_processing_speed", 0.70),
       ("sl_hypersomnia", 0.55)],
      min_n=2, min_sev=0.40,
      profile={"inflammation": 1.0, "acetylcholine": -0.8, "allostatic_load": 0.8},
      curability=0.25, perf="delirium", min_turns=0, max_turns=40, acute=True,
      note="急性起病、注意与意识水平波动，常由感染/药物/代谢紊乱所致"),

    D("6D80", "痴呆", "Dementia", "neurocognitive",
      [("cg_memory_deficit", 0.95), ("cg_executive_deficit", 0.85),
       ("cg_processing_speed", 0.80), ("cg_disorientation", 0.60),
       ("ot_personality_change", 0.55)],
      min_n=3, min_sev=0.38,
      profile={"hippocampal_integrity": -1.0, "acetylcholine": -0.8, "inflammation": 0.6},
      curability=0.01, perf="dementia", min_turns=100,
      note="进行性认知衰退，足以影响日常生活"),

    # =====================================================================
    # 07 章 · 睡眠-觉醒障碍 (7A00–7A2Z)
    # =====================================================================
    D("7A00", "失眠障碍", "Insomnia disorder", "sleep",
      [("sl_insomnia", 0.95), ("md_fatigue", 0.65), ("md_concentration", 0.50),
       ("ax_worry", 0.55)],
      min_n=2, min_sev=0.28,
      profile={"norepinephrine": 0.4, "gaba": -0.4, "arousal": 0.5},
      curability=0.22, perf="insomnia", min_turns=10,
      note="入睡/维持睡眠困难，每周 ≥3 次并持续 ≥3 个月，伴日间损害"),

    D("7A01", "嗜睡障碍", "Hypersomnolence disorder", "sleep",
      [("sl_hypersomnia", 0.95), ("md_fatigue", 0.70), ("md_concentration", 0.50)],
      min_n=2, min_sev=0.30,
      profile={"orexin": -0.7, "adenosine": 0.6},
      curability=0.15, perf="hypersomnia", min_turns=10,
      note="日间过度嗜睡，尽管夜间睡眠充足"),

    D("7A20", "昼夜节律睡眠-觉醒障碍", "Circadian rhythm sleep-wake disorder", "sleep",
      [("sl_circadian_shift", 0.95), ("sl_insomnia", 0.60), ("sl_hypersomnia", 0.50)],
      min_n=2, min_sev=0.28,
      profile={"melatonin": -0.6, "orexin": 0.3},
      curability=0.20, perf="circadian", min_turns=10,
      note="睡眠时相与社会作息显著错位"),

    # =====================================================================
    # 06 章 · 做作性障碍 (6D50–6D5Z) / 其他
    # =====================================================================
    D("6D50", "做作性障碍", "Factitious disorder imposed on self", "other",
      [("ot_factitious", 0.95), ("so_somatic_complaint", 0.70), ("su_control_loss", 0.20),
       ("pd_manipulativeness", 0.55)],
      min_n=2, min_sev=0.32,
      profile={"interoception": 0.3},
      curability=0.03, perf="factitious", min_turns=15,
      note="故意制造或夸大症状以获取医疗关注，非为外部获益"),
]


# ---------------------------------------------------------------------------
# 核心（病理特异性 / pathognomonic）症状：至少命中一条，否则该诊断不成立。
# 用于防止"用疲乏和注意力下降诊断嗜睡障碍"这类跨域误判。
# ---------------------------------------------------------------------------
CORE: Dict[str, List[str]] = {
    "6A20": ["ps_delusion_persecutory", "ps_hallucination_auditory", "ps_formal_thought_disorder"],
    "6A21": ["ps_delusion_persecutory", "ps_hallucination_auditory"],
    "6A22": ["pd_psychoticism", "ps_delusion_reference"],
    "6A23": ["ps_hallucination_auditory", "ps_delusion_persecutory", "ps_reality_testing_impair"],
    "6A24": ["ps_delusion_persecutory", "ps_delusion_jealousy", "ps_delusion_erotomanic",
             "ps_delusion_somatic", "ps_delusion_grandiose", "ps_delusion_nihilistic"],
    "6A25": ["ps_hallucination_visual", "cg_consciousness_fluctuation"],
    "6A40": ["cg_stupor", "cg_waxy_flexibility", "cg_negativism"],
    "6A2Z-UHR": ["pd_psychoticism", "ps_delusion_reference", "di_derealization"],
    # 双相谱系的标记性症状只能是「心境高涨/活动增多」——
    # 睡眠减少与抑郁心境在单相抑郁、失眠、焦虑里都有，拿它们当核心会把
    # 「被骂 20 轮的健康人」判成双相 II。
    "6A60": ["ma_elevated_mood"],
    "6A61": ["ma_elevated_mood"],
    "6A62": ["ma_elevated_mood"],
    "6A70": ["md_depressed_mood", "md_anhedonia"],
    "6A71": ["md_depressed_mood", "md_anhedonia"],
    "6A72": ["md_depressed_mood"],
    "6A73": ["md_depressed_mood", "ax_worry"],
    "6B00": ["ax_worry"],
    "6B01": ["ax_panic_attack"],
    "6B02": ["ax_avoidance_agora"],
    "6B03": ["ax_avoidance_specific"],
    "6B04": ["ax_avoidance_social"],
    "6B05": ["ax_separation"],
    "6B06": ["ax_selective_mutism"],
    "6B20": ["oc_obsession_contamination", "oc_obsession_harm", "oc_obsession_symmetry",
             "oc_compulsion_checking", "oc_compulsion_washing", "oc_mental_ritual"],
    "6B21": ["oc_body_dysmorphic"],
    "6B22": ["oc_body_dysmorphic", "ps_delusion_reference"],
    "6B23": ["oc_health_anxiety"],
    "6B24": ["oc_hoarding"],
    "6B25.0": ["oc_trichotillomania"],
    "6B25.1": ["oc_skin_picking"],
    "6B40": ["tr_intrusion", "tr_flashback", "tr_avoidance"],
    "6B41": ["tr_emotional_dysregulation", "tr_identity_diffusion", "tr_flashback"],
    "6B42": ["ot_bereavement", "tr_grief"],
    "6B44": ["pd_detachment"],
    "6B45": ["pd_disinhibition"],
    "6B60": ["di_conversion"],
    "6B61": ["di_amnesia"],
    "6B62": ["di_trance"],
    "6B64": ["di_identity_fragmentation"],
    "6B66": ["di_depersonalization", "di_derealization"],
    "6B80": ["ea_restriction", "ea_low_weight"],
    "6B81": ["ea_binge", "ea_purge"],
    "6B82": ["ea_binge"],
    "6B83": ["ea_restriction"],
    "6A80": ["ma_irritability", "md_appetite_gain"],
    "6C20": ["so_somatic_complaint"],
    "6C40": ["su_craving", "su_control_loss"],
    "6C43": ["su_craving", "su_withdrawal"],
    "6C46": ["su_craving", "su_tolerance"],
    "6C4A": ["su_craving"],
    "6C50": ["ic_gambling"],
    "6C51": ["ic_gaming"],
    "6C72": ["ic_compulsive_sexual"],
    "6C73": ["ic_anger_outburst"],
    "6A02": ["nd_social_communication", "nd_restricted_repetitive"],
    "6A05": ["nd_inattention", "nd_hyperactivity"],
    "6D70": ["cg_consciousness_fluctuation", "cg_disorientation"],
    "6D80": ["cg_memory_deficit"],
    "7A00": ["sl_insomnia"],
    "7A01": ["sl_hypersomnia"],
    "7A20": ["sl_circadian_shift"],
    "6D50": ["ot_factitious"],
}

# 快速索引
BY_CODE = {d["code"]: d for d in DISORDERS}

# 诊断族 → 谈话治疗可及性（0~1），dynamics 会乘到治疗增益上
GROUP_TALKABILITY = {
    "psychotic": 0.10,
    "bipolar": 0.16,
    "mood": 0.70,
    "anxiety": 0.80,
    "ocd": 0.30,
    "stress": 0.55,
    "dissociative": 0.35,
    "eating": 0.20,
    "bodily": 0.35,
    "substance": 0.12,
    "impulse": 0.25,
    "personality": 0.08,
    "neurodev": 0.05,
    "neurocognitive": 0.05,
    "sleep": 0.65,
    "other": 0.30,
}
