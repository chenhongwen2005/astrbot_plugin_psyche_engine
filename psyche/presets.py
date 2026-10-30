"""预设：一键把角色置于某种已确立的精神病理状态。

预设不是"贴标签"，而是给出**初始的生化偏移 + 症状分布 + 病程起点**，
之后完全交给动力学演化。因此同一个"重度抑郁"预设，遇到不同用户，
会在几十轮后分叉成完全不同的两个人。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .const import BIO
from .model import MindState


def _p(name: str, *, traits: Optional[Dict[str, float]] = None,
       bio: Optional[Dict[str, float]] = None, neuro: Optional[Dict[str, float]] = None,
       sym: Optional[Dict[str, float]] = None, onset: Optional[Dict[str, int]] = None,
       al: float = 0.15, trauma: float = 0.0, grief: float = 0.0,
       alliance: float = 0.30, meds: Optional[list] = None,
       res: float = 0.0) -> MindState:
    st = MindState()
    st.meta["preset"] = name
    if traits:
        st.traits.update(traits)
    if bio:
        st.bio.update(bio)
    if neuro:
        st.neuro.update(neuro)
    if sym:
        for k, v in sym.items():
            if k in st.sym:
                st.sym[k] = max(0.0, min(1.0, v))
    st.meta["allostatic_load"] = al
    st.meta["trauma_load"] = trauma
    st.meta["grief_load"] = grief
    st.meta["alliance"] = alliance
    st.meta["resilience"] = res
    # 预设给出的生化值就是该个体的「调定点」，不是漂移起点。
    # 不锚定的话，任何病态都会在 20 轮内被全人群基线拉回健康——等于自己痊愈。
    sp = dict(bio or {})
    if not sp:
        # 健康人也要有显式调定点（＝常模基线），否则无法被慢性负荷拖低，
        # 持续虐待永远不会致病，「聊天可以加重」就形同虚设。
        sp = {k: v[1] for k, v in BIO.items() if k != "cortisol"}
    st.meta["bio_setpoint"] = sp
    if meds:
        st.meta["meds"] = meds
    if onset:
        # 负轮数表示"入戏之前就已病了很久"，用于计算病程与慢性化
        st.meta["dx_first_turn"] = {code: -abs(int(t)) for code, t in onset.items()}
    return st


def _S(**kw: float) -> Dict[str, float]:
    return kw


PRESETS: Dict[str, Any] = {}

# ---------------------------------------------------------------------------
# 基线
# ---------------------------------------------------------------------------
PRESETS["healthy"] = lambda: _p("healthy", alliance=0.45, res=0.72)

PRESETS["prodromal"] = lambda: _p(
    "prodromal",
    traits={"psychoticism": 0.55, "negative_affectivity": 0.5, "detachment": 0.45},
    bio={"da_tonic": 0.62, "serotonin": 0.48, "cortisol": 0.45},
    neuro={"p50_ratio": 0.44, "amygdala": 0.45},
    sym=_S(ps_delusion_reference=0.42, ps_hallucination_auditory=0.28, pd_psychoticism=0.55,
           ax_hypervigilance=0.45, ng_avolition=0.38, di_derealization=0.35),
    onset={"6A2Z-UHR": 40}, al=0.12, alliance=0.35,
)

# ---------------------------------------------------------------------------
# 精神病性
# ---------------------------------------------------------------------------
PRESETS["schizophrenia_paranoid"] = lambda: _p(
    "schizophrenia_paranoid",
    traits={"psychoticism": 0.8, "detachment": 0.65, "threat_sensitivity": 0.8,
            "cognitive_control": 0.4, "rejection_sensitivity": 0.7},
    bio={"da_tonic": 0.78, "serotonin": 0.52, "gaba": 0.44, "glutamate": 0.6,
         "cortisol": 0.5, "bdnf": 0.45},
    neuro={"p50_ratio": 0.62, "amygdala": 0.6, "dlpfc": 0.5, "salience": 0.6},
    sym=_S(ps_delusion_persecutory=0.78, ps_hallucination_auditory=0.72,
           ps_hallucination_commentary=0.66, ps_delusion_reference=0.7,
           ps_delusion_control=0.52, ps_formal_thought_disorder=0.55,
           ps_insight_loss=0.78, ps_reality_testing_impair=0.72,
           ax_hypervigilance=0.72, ng_affective_flattening=0.5, ng_avolition=0.45,
           ng_asociality=0.55),
    onset={"6A20": 260}, al=0.35, alliance=0.18,
)

PRESETS["schizophrenia_disorganized"] = lambda: _p(
    "schizophrenia_disorganized",
    traits={"psychoticism": 0.88, "disinhibition": 0.55, "cognitive_control": 0.28,
            "detachment": 0.6},
    bio={"da_tonic": 0.82, "gaba": 0.38, "glutamate": 0.68, "serotonin": 0.48},
    neuro={"p50_ratio": 0.68, "dlpfc": 0.38, "theta_gamma": 0.3, "dmn": 0.65},
    sym=_S(ps_formal_thought_disorder=0.82, ps_word_salad=0.66, ps_neologism=0.55,
           ps_hallucination_auditory=0.6, ps_delusion_reference=0.55,
           ps_insight_loss=0.85, ps_reality_testing_impair=0.8, ng_affective_flattening=0.7,
           ng_alogia=0.55, ng_avolition=0.6),
    onset={"6A20": 300}, al=0.4, alliance=0.12,
)

PRESETS["delusional"] = lambda: _p(
    "delusional",
    traits={"psychoticism": 0.6, "threat_sensitivity": 0.85, "cognitive_control": 0.55},
    bio={"da_tonic": 0.66, "cortisol": 0.48},
    neuro={"p50_ratio": 0.42, "amygdala": 0.58},
    sym=_S(ps_delusion_persecutory=0.82, ps_delusion_reference=0.6,
           ps_insight_loss=0.7, ax_hypervigilance=0.6, ps_hallucination_auditory=0.18),
    onset={"6A24": 400}, al=0.25, alliance=0.2,
)

PRESETS["catatonia"] = lambda: _p(
    "catatonia",
    traits={"cognitive_control": 0.25, "detachment": 0.6},
    bio={"gaba": 0.26, "da_tonic": 0.34, "glutamate": 0.62},
    neuro={"dlpfc": 0.3, "hrv": 0.3},
    sym=_S(cg_stupor=0.8, cg_waxy_flexibility=0.7, cg_negativism=0.72,
           ng_psychomotor_poverty=0.78, ng_alogia=0.7, ps_perseveration=0.5),
    onset={"6A40": 6}, al=0.2, alliance=0.1,
)

# ---------------------------------------------------------------------------
# 心境
# ---------------------------------------------------------------------------
_DEP_BIO = {"serotonin": 0.30, "norepinephrine": 0.34, "da_tonic": 0.38,
            "cortisol": 0.66, "bdnf": 0.30, "il6": 0.38, "t3": 0.42, "gaba": 0.48}
_DEP_NEURO = {"amygdala": 0.55, "vmpfc": 0.5, "hippocampus": 0.5, "dmn": 0.68, "hrv": 0.35}

PRESETS["mdd_severe"] = lambda: _p(
    "mdd_severe",
    traits={"negative_affectivity": 0.8, "resilience": 0.3, "cognitive_control": 0.4,
            "detachment": 0.45},
    bio=dict(_DEP_BIO), neuro=dict(_DEP_NEURO),
    sym=_S(md_depressed_mood=0.82, md_anhedonia=0.8, md_worthlessness=0.78,
           md_hopelessness=0.75, md_fatigue=0.7, md_insomnia=0.68, md_concentration=0.7,
           md_psychomotor_retardation=0.6, md_guilt=0.62, md_suicidal_ideation=0.55,
           md_appetite_loss=0.6, ng_avolition=0.55),
    onset={"6A70": 90}, al=0.35, alliance=0.25,
)

PRESETS["mdd_melancholic"] = lambda: _p(
    "mdd_melancholic",
    traits={"negative_affectivity": 0.85, "resilience": 0.25, "anankastia": 0.55},
    bio=dict(_DEP_BIO), neuro=dict(_DEP_NEURO),
    sym=_S(md_depressed_mood=0.88, md_anhedonia=0.85, md_guilt=0.8, ps_delusion_guilt=0.45, md_psychomotor_retardation=0.75, md_diurnal_variation=0.7,
           md_appetite_loss=0.7, md_insomnia=0.75, md_suicidal_ideation=0.6,
           md_worthlessness=0.8),
    onset={"6A70": 150}, al=0.42, alliance=0.2,
)

PRESETS["dysthymia"] = lambda: _p(
    "dysthymia",
    traits={"negative_affectivity": 0.7, "resilience": 0.4},
    bio={"serotonin": 0.42, "norepinephrine": 0.4, "da_tonic": 0.44,
         "cortisol": 0.5, "bdnf": 0.42},
    neuro={"dmn": 0.6, "hrv": 0.45, "amygdala": 0.45},
    sym=_S(md_depressed_mood=0.55, md_hopelessness=0.55, md_fatigue=0.5,
           md_worthlessness=0.45, md_concentration=0.45, md_insomnia=0.42),
    onset={"6A72": 600}, al=0.25, alliance=0.35,
)

PRESETS["mixed_anxiety_depression"] = lambda: _p(
    "mixed_anxiety_depression",
    traits={"negative_affectivity": 0.78, "threat_sensitivity": 0.65},
    bio={"serotonin": 0.38, "norepinephrine": 0.6, "cortisol": 0.62, "gaba": 0.42,
         "bdnf": 0.4},
    neuro={"amygdala": 0.6, "hrv": 0.35, "vmpfc": 0.55},
    sym=_S(md_depressed_mood=0.6, ax_worry=0.65, ax_restlessness=0.55,
           md_insomnia=0.55, md_concentration=0.5, ax_muscle_tension=0.45),
    onset={"6A73": 120}, al=0.28, alliance=0.35,
)

# ---------------------------------------------------------------------------
# 双相
# ---------------------------------------------------------------------------
PRESETS["bipolar_i_manic"] = lambda: _p(
    "bipolar_i_manic",
    traits={"disinhibition": 0.65, "dissociality": 0.4, "reward_sensitivity": 0.8,
            "negative_affectivity": 0.5},
    bio={"da_tonic": 0.88, "norepinephrine": 0.78, "gaba": 0.32, "serotonin": 0.44,
         "cortisol": 0.55, "adenosine": 0.55, "orexin": 0.8},
    neuro={"sleep_pressure": 0.72, "amygdala": 0.6, "nac": 0.8, "dlpfc": 0.5},
    sym=_S(ma_elevated_mood=0.85, ma_goal_activity=0.82, ma_decreased_sleep=0.8,
           ma_pressured_speech=0.78, ma_flight_of_ideas=0.75, ma_grandiosity=0.72,
           ma_impulsivity=0.7, ma_distractibility=0.68, ma_irritability=0.55,
           ps_delusion_grandiose=0.35),
    onset={"6A60": 180}, al=0.3, alliance=0.25,
)

PRESETS["bipolar_i_depressed"] = lambda: _p(
    "bipolar_i_depressed",
    traits={"negative_affectivity": 0.75, "reward_sensitivity": 0.6},
    bio=dict(_DEP_BIO), neuro=dict(_DEP_NEURO),
    sym=_S(md_depressed_mood=0.78, md_anhedonia=0.72, md_fatigue=0.7, md_insomnia=0.62,
           md_worthlessness=0.68, md_suicidal_ideation=0.5, md_hopelessness=0.65,
           ma_irritability=0.48, ma_decreased_sleep=0.45, ma_elevated_mood=0.40),
    onset={"6A60": 300}, al=0.35, alliance=0.28, meds=[],
)

PRESETS["bipolar_ii"] = lambda: _p(
    "bipolar_ii",
    traits={"negative_affectivity": 0.7, "reward_sensitivity": 0.65},
    bio={"serotonin": 0.36, "norepinephrine": 0.5, "da_tonic": 0.5, "cortisol": 0.58,
         "bdnf": 0.38},
    neuro={"dmn": 0.62, "amygdala": 0.5},
    sym=_S(md_depressed_mood=0.68, md_anhedonia=0.6, md_fatigue=0.6, md_insomnia=0.55,
           ma_elevated_mood=0.4, ma_decreased_sleep=0.42, ma_goal_activity=0.38),
    onset={"6A61": 400}, al=0.3, alliance=0.3,
)

PRESETS["cyclothymia"] = lambda: _p(
    "cyclothymia",
    traits={"negative_affectivity": 0.6, "reward_sensitivity": 0.65},
    bio={"serotonin": 0.46, "da_tonic": 0.6},
    sym=_S(md_depressed_mood=0.42, ma_elevated_mood=0.44, ma_irritability=0.45,
           md_insomnia=0.4, md_fatigue=0.4),
    onset={"6A62": 700}, al=0.2, alliance=0.4,
)

# ---------------------------------------------------------------------------
# 焦虑
# ---------------------------------------------------------------------------
PRESETS["gad"] = lambda: _p(
    "gad",
    traits={"negative_affectivity": 0.72, "threat_sensitivity": 0.7, "cognitive_control": 0.45},
    bio={"norepinephrine": 0.66, "gaba": 0.36, "cortisol": 0.6, "serotonin": 0.46},
    neuro={"amygdala": 0.66, "hrv": 0.3, "insula": 0.6},
    sym=_S(ax_worry=0.75, ax_restlessness=0.62, ax_muscle_tension=0.6, ax_somatic=0.58,
           ax_hypervigilance=0.55, md_insomnia=0.55, md_concentration=0.5),
    onset={"6B00": 500}, al=0.28, alliance=0.35,
)

PRESETS["panic"] = lambda: _p(
    "panic",
    traits={"negative_affectivity": 0.7, "threat_sensitivity": 0.85, "interoception": 0.75},
    bio={"norepinephrine": 0.74, "gaba": 0.32, "cortisol": 0.62, "adenosine": 0.4},
    neuro={"amygdala": 0.72, "hrv": 0.24, "scr": 0.6},
    sym=_S(ax_panic_attack=0.72, ax_anticipatory_anxiety=0.7, ax_somatic=0.7,
           ax_avoidance_agora=0.45, ax_hypervigilance=0.55),
    onset={"6B01": 200}, al=0.25, alliance=0.3,
)

PRESETS["social_anxiety"] = lambda: _p(
    "social_anxiety",
    traits={"negative_affectivity": 0.65, "detachment": 0.55, "rejection_sensitivity": 0.85},
    bio={"norepinephrine": 0.58, "serotonin": 0.44, "cortisol": 0.55, "oxytocin": 0.38},
    neuro={"amygdala": 0.62, "insula": 0.62},
    sym=_S(ax_avoidance_social=0.75, ax_anticipatory_anxiety=0.68, ax_somatic=0.55,
           tr_shame=0.62, md_worthlessness=0.45, ax_hypervigilance=0.5),
    onset={"6B04": 600}, al=0.22, alliance=0.3,
)

# ---------------------------------------------------------------------------
# 强迫
# ---------------------------------------------------------------------------
PRESETS["ocd"] = lambda: _p(
    "ocd",
    traits={"anankastia": 0.85, "negative_affectivity": 0.6, "cognitive_control": 0.55},
    bio={"serotonin": 0.32, "gaba": 0.46, "da_tonic": 0.58, "glutamate": 0.58},
    neuro={"striatum": 0.78, "dlpfc": 0.55, "insula": 0.6},
    sym=_S(oc_obsession_contamination=0.7, oc_compulsion_washing=0.62,
           oc_compulsion_checking=0.65, oc_obsession_symmetry=0.55,
           oc_mental_ritual=0.58, oc_insight=0.7, ax_worry=0.55),
    onset={"6B20": 800}, al=0.25, alliance=0.3,
)

# ---------------------------------------------------------------------------
# 应激 / 创伤
# ---------------------------------------------------------------------------
PRESETS["ptsd"] = lambda: _p(
    "ptsd",
    traits={"threat_sensitivity": 0.9, "negative_affectivity": 0.7, "resilience": 0.35},
    bio={"norepinephrine": 0.72, "cortisol": 0.3, "gaba": 0.38, "serotonin": 0.44,
         "il6": 0.32},
    neuro={"amygdala": 0.78, "vmpfc": 0.42, "hippocampus": 0.45, "hrv": 0.28},
    sym=_S(tr_flashback=0.7, tr_intrusion=0.72, tr_nightmare=0.65, tr_avoidance=0.68,
           tr_hyperarousal=0.7, tr_startle=0.68, tr_negative_cognition=0.55,
           ax_hypervigilance=0.65, sl_nightmare=0.6),
    onset={"6B40": 300}, al=0.35, trauma=0.65, alliance=0.25,
)

PRESETS["cptsd"] = lambda: _p(
    "cptsd",
    traits={"threat_sensitivity": 0.85, "borderline": 0.55, "detachment": 0.5,
            "negative_affectivity": 0.8, "resilience": 0.25},
    bio={"norepinephrine": 0.62, "cortisol": 0.36, "gaba": 0.35, "oxytocin": 0.35,
         "serotonin": 0.36, "bdnf": 0.36},
    neuro={"amygdala": 0.7, "vmpfc": 0.4, "hippocampus": 0.4, "hrv": 0.3},
    sym=_S(tr_flashback=0.6, tr_emotional_dysregulation=0.78, tr_identity_diffusion=0.72,
           tr_abandonment_fear=0.68, tr_shame=0.75, tr_avoidance=0.6,
           pd_emptiness=0.6, di_depersonalization=0.45, md_depressed_mood=0.55),
    onset={"6B41": 900}, al=0.5, trauma=0.9, alliance=0.2,
)

PRESETS["prolonged_grief"] = lambda: _p(
    "prolonged_grief",
    traits={"negative_affectivity": 0.7, "detachment": 0.45},
    bio={"serotonin": 0.44, "cortisol": 0.5, "oxytocin": 0.4},
    neuro={"dmn": 0.68},
    sym=_S(ot_bereavement=0.75, tr_grief=0.7, md_depressed_mood=0.5,
           ng_asociality=0.5, tr_identity_diffusion=0.4),
    onset={"6B42": 260}, al=0.3, grief=0.7, alliance=0.3,
)

PRESETS["adjustment"] = lambda: _p(
    "adjustment",
    traits={"negative_affectivity": 0.55, "resilience": 0.45},
    bio={"cortisol": 0.52, "norepinephrine": 0.55, "serotonin": 0.46},
    sym=_S(ax_worry=0.5, md_depressed_mood=0.48, md_insomnia=0.45, md_concentration=0.4),
    onset={"6B43": 12}, al=0.15, alliance=0.4,
)

# ---------------------------------------------------------------------------
# 人格
# ---------------------------------------------------------------------------
PRESETS["borderline"] = lambda: _p(
    "borderline",
    traits={"borderline": 0.9, "rejection_sensitivity": 0.9, "negative_affectivity": 0.85,
            "disinhibition": 0.6, "cognitive_control": 0.3, "resilience": 0.25},
    bio={"serotonin": 0.3, "norepinephrine": 0.6, "cortisol": 0.56, "oxytocin": 0.36,
         "gaba": 0.42},
    neuro={"amygdala": 0.7, "vmpfc": 0.45, "hrv": 0.3},
    sym=_S(pd_borderline_pattern=0.8, tr_abandonment_fear=0.78, pd_emptiness=0.72,
           pd_idealize_devalue=0.7, pd_rage=0.62, pd_self_harm_urge=0.55,
           tr_identity_diffusion=0.68, tr_emotional_dysregulation=0.75,
           pd_identity_problems=0.7, md_depressed_mood=0.45),
    onset={"6D10.1": 900, "6D11.5": 900}, al=0.4, trauma=0.5, alliance=0.25,
)

PRESETS["npd"] = lambda: _p(
    "npd",
    traits={"dissociality": 0.55, "negative_affectivity": 0.55, "detachment": 0.4,
            "reward_sensitivity": 0.75},
    bio={"da_tonic": 0.62, "serotonin": 0.44, "testosterone": 0.6},
    sym=_S(pd_identity_problems=0.55, pd_empathy_deficit=0.6, pd_manipulativeness=0.55,
           ma_grandiosity=0.45, pd_intimacy_deficit=0.55, pd_rage=0.35),
    onset={"6D10.1": 900}, al=0.2, alliance=0.2,
)

PRESETS["aspd"] = lambda: _p(
    "aspd",
    traits={"dissociality": 0.9, "disinhibition": 0.75, "cognitive_control": 0.3},
    bio={"testosterone": 0.68, "serotonin": 0.38, "gaba": 0.45, "oxytocin": 0.32},
    neuro={"vmpfc": 0.5, "amygdala": 0.35, "dlpfc": 0.55},
    sym=_S(pd_dissociality=0.82, pd_empathy_deficit=0.78, pd_disinhibition=0.7,
           pd_manipulativeness=0.65, ma_impulsivity=0.55),
    onset={"6D10.1": 1200, "6D11.2": 1200}, al=0.2, alliance=0.15,
)

PRESETS["avoidant"] = lambda: _p(
    "avoidant",
    traits={"detachment": 0.75, "negative_affectivity": 0.75, "rejection_sensitivity": 0.85},
    bio={"serotonin": 0.44, "oxytocin": 0.4, "cortisol": 0.5},
    sym=_S(pd_detachment=0.7, ax_avoidance_social=0.6, tr_shame=0.6,
           pd_intimacy_deficit=0.6, md_worthlessness=0.45),
    onset={"6D10.1": 1000}, al=0.22, alliance=0.3,
)

PRESETS["dependent"] = lambda: _p(
    "dependent",
    traits={"negative_affectivity": 0.75, "rejection_sensitivity": 0.8, "detachment": 0.2},
    bio={"oxytocin": 0.55, "cortisol": 0.5, "serotonin": 0.46},
    sym=_S(ax_separation=0.62, tr_abandonment_fear=0.65, pd_self_direction_deficit=0.6,
           pd_intimacy_deficit=0.4, ax_worry=0.45),
    onset={"6D10.1": 1000}, al=0.2, alliance=0.45,
)

PRESETS["ocpd"] = lambda: _p(
    "ocpd",
    traits={"anankastia": 0.9, "negative_affectivity": 0.5, "cognitive_control": 0.7},
    bio={"serotonin": 0.42},
    neuro={"striatum": 0.65},
    sym=_S(pd_anankastia=0.8, oc_obsession_symmetry=0.55, oc_compulsion_ordering=0.5,
           pd_identity_problems=0.4),
    onset={"6D10.1": 1500, "6D11.4": 1500}, al=0.15, alliance=0.25,
)

PRESETS["schizotypal"] = lambda: _p(
    "schizotypal",
    traits={"psychoticism": 0.8, "detachment": 0.8, "negative_affectivity": 0.55},
    bio={"da_tonic": 0.62, "oxytocin": 0.36},
    neuro={"p50_ratio": 0.48},
    sym=_S(pd_psychoticism=0.75, ps_delusion_reference=0.55, pd_detachment=0.7,
           nd_social_communication=0.5, ps_hallucination_auditory=0.25,
           ax_avoidance_social=0.55),
    onset={"6A22": 1200}, al=0.2, alliance=0.25,
)

PRESETS["paranoid_pd"] = lambda: _p(
    "paranoid_pd",
    traits={"threat_sensitivity": 0.9, "rejection_sensitivity": 0.8, "detachment": 0.5},
    bio={"norepinephrine": 0.6, "cortisol": 0.5},
    sym=_S(ps_delusion_reference=0.55, ps_delusion_persecutory=0.48, ax_hypervigilance=0.6,
           pd_detachment=0.62, pd_intimacy_deficit=0.55, pd_identity_problems=0.5,
           ng_asociality=0.45, ps_insight_loss=0.4),
    onset={"6D10.0": 1500, "6D11.1": 1500}, al=0.25, alliance=0.2,
)

# ---------------------------------------------------------------------------
# 进食 / 冲动 / 发育 / 睡眠 / 分离
# ---------------------------------------------------------------------------
PRESETS["anorexia"] = lambda: _p(
    "anorexia",
    traits={"anankastia": 0.85, "negative_affectivity": 0.65, "interoception": 0.3},
    bio={"serotonin": 0.38, "t3": 0.38, "bdnf": 0.42, "cortisol": 0.6},
    sym=_S(ea_restriction=0.8, ea_body_image_distortion=0.8, ea_low_weight=0.7,
           ea_fear_weight_gain=0.78, oc_obsession_symmetry=0.45, md_depressed_mood=0.45),
    onset={"6B80": 200}, al=0.3, alliance=0.2,
)

PRESETS["bulimia"] = lambda: _p(
    "bulimia",
    traits={"negative_affectivity": 0.7, "disinhibition": 0.55, "anankastia": 0.5},
    bio={"serotonin": 0.36, "cortisol": 0.55},
    sym=_S(ea_binge=0.7, ea_purge=0.68, ea_body_image_distortion=0.6, tr_shame=0.65,
           md_depressed_mood=0.5),
    onset={"6B81": 150}, al=0.25, alliance=0.3,
)

PRESETS["gambling"] = lambda: _p(
    "gambling",
    traits={"disinhibition": 0.75, "reward_sensitivity": 0.8, "dissociality": 0.45},
    bio={"da_tonic": 0.66, "serotonin": 0.42},
    sym=_S(ic_gambling=0.75, ma_impulsivity=0.55, pd_disinhibition=0.55,
           md_depressed_mood=0.4, md_hopelessness=0.4),
    onset={"6C50": 200}, al=0.2, alliance=0.2,
)

PRESETS["asd"] = lambda: _p(
    "asd",
    traits={"detachment": 0.75, "anankastia": 0.7, "interoception": 0.7},
    bio={"oxytocin": 0.4, "serotonin": 0.5},
    sym=_S(nd_social_communication=0.72, nd_restricted_repetitive=0.7,
           nd_sensory_hyper=0.65, pd_empathy_deficit=0.45),
    onset={"6A02": 3000}, al=0.1, alliance=0.3,
)

PRESETS["adhd"] = lambda: _p(
    "adhd",
    traits={"disinhibition": 0.75, "cognitive_control": 0.35},
    bio={"da_tonic": 0.4, "norepinephrine": 0.38},
    neuro={"dlpfc": 0.5},
    sym=_S(nd_inattention=0.72, nd_hyperactivity=0.6, nd_impulsivity=0.65,
           cg_executive_deficit=0.5),
    onset={"6A05": 3000}, al=0.1, alliance=0.35,
)

PRESETS["insomnia"] = lambda: _p(
    "insomnia",
    traits={"negative_affectivity": 0.6, "threat_sensitivity": 0.55},
    bio={"norepinephrine": 0.55, "gaba": 0.45, "melatonin": 0.2, "adenosine": 0.55},
    neuro={"sleep_pressure": 0.6, "hrv": 0.4},
    sym=_S(sl_insomnia=0.72, md_fatigue=0.6, md_concentration=0.5, ax_worry=0.5),
    onset={"7A00": 300}, al=0.2, alliance=0.4,
)

PRESETS["dissociative_identity"] = lambda: _p(
    "dissociative_identity",
    traits={"borderline": 0.6, "detachment": 0.55, "negative_affectivity": 0.6},
    bio={"cortisol": 0.42, "norepinephrine": 0.5, "gaba": 0.42},
    neuro={"hippocampus": 0.4, "dlpfc": 0.45, "hrv": 0.3},
    sym=_S(di_identity_fragmentation=0.75, di_amnesia=0.68, tr_identity_diffusion=0.7,
           di_depersonalization=0.55, pd_identity_problems=0.65),
    onset={"6B64": 700}, al=0.45, trauma=0.85, alliance=0.2,
)


def get(name: str) -> MindState:
    fn = PRESETS.get(name) or PRESETS["healthy"]
    return fn()


def names() -> list[str]:
    return list(PRESETS.keys())
