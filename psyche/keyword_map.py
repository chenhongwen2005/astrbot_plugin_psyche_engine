"""关键词 → 症状增量的映射表。

模型负责"提取关键词"，引擎负责"把关键词翻译成对被试症状的具体推拉"。
这样既保留了模型对语境的判断，又保证每一次修改都是可解释、可复现、可审计的
（每条增量都能追溯到哪个词、推了哪个症状多少）。

权重单位：0~1 的症状增量，最终由 dynamics 乘以 0.5 的缩放系数。
负值表示缓解，例如"我陪着你"会拉低被抛弃恐惧。
"""

from __future__ import annotations

from typing import Dict

RULES: Dict[str, Dict[str, float]] = {
    # ------------- 抛弃 / 关系断裂 -------------
    "别走": {"tr_abandonment_fear": 0.22, "pd_emptiness": 0.16, "md_worthlessness": 0.10},
    "不要你": {"tr_abandonment_fear": 0.25, "pd_emptiness": 0.20, "md_suicidal_ideation": 0.06},
    "分手": {"tr_abandonment_fear": 0.28, "md_depressed_mood": 0.18, "pd_self_harm_urge": 0.10},
    "绝交": {"tr_abandonment_fear": 0.26, "pd_rage": 0.14},
    "拉黑": {"tr_abandonment_fear": 0.24, "pd_emptiness": 0.18},
    "滚": {"tr_abandonment_fear": 0.20, "pd_rage": 0.18, "md_worthlessness": 0.15},
    "走开": {"tr_abandonment_fear": 0.18, "pd_emptiness": 0.12},
    "离开": {"tr_abandonment_fear": 0.18, "md_depressed_mood": 0.10},
    "再也不": {"tr_abandonment_fear": 0.22, "md_hopelessness": 0.14},
    "随便你": {"md_worthlessness": 0.12, "tr_abandonment_fear": 0.10, "pd_emptiness": 0.12},
    "无所谓": {"md_worthlessness": 0.12, "pd_emptiness": 0.12},

    # ------------- 否定存在价值 -------------
    "废物": {"md_worthlessness": 0.24, "pd_rage": 0.12, "ps_delusion_persecutory": 0.10},
    "垃圾": {"md_worthlessness": 0.22, "pd_rage": 0.14},
    "没用": {"md_worthlessness": 0.22, "ng_avolition": 0.10},
    "装的": {"ps_delusion_reference": 0.20, "md_worthlessness": 0.14, "pd_identity_problems": 0.12},
    "矫情": {"md_worthlessness": 0.16, "pd_rage": 0.12},
    "有病": {"ps_delusion_reference": 0.18, "md_worthlessness": 0.12, "ax_hypervigilance": 0.10},
    "疯了": {"ps_delusion_reference": 0.18, "ps_insight_loss": 0.10, "pd_identity_problems": 0.12},
    "神经病": {"ps_delusion_reference": 0.18, "pd_rage": 0.12},
    "怪物": {"ps_delusion_reference": 0.20, "pd_identity_problems": 0.18},
    "变态": {"md_worthlessness": 0.18, "tr_shame": 0.16},

    # ------------- 迫害 / 监视 -------------
    "监视": {"ps_delusion_persecutory": 0.28, "ax_hypervigilance": 0.18},
    "跟踪": {"ps_delusion_persecutory": 0.26, "ax_hypervigilance": 0.18},
    "下毒": {"ps_delusion_persecutory": 0.30, "ps_delusion_somatic": 0.14},
    "害我": {"ps_delusion_persecutory": 0.28},
    "阴谋": {"ps_delusion_persecutory": 0.26, "ps_delusion_reference": 0.16},
    "他们": {"ps_delusion_persecutory": 0.16, "ps_hallucination_commentary": 0.14},
    "组织": {"ps_delusion_persecutory": 0.16},
    "警察": {"ps_delusion_persecutory": 0.18, "ax_hypervigilance": 0.10},
    "摄像头": {"ps_delusion_persecutory": 0.24},

    # ------------- 幻听 -------------
    "声音": {"ps_hallucination_auditory": 0.22, "ps_hallucination_commentary": 0.14},
    "说话声": {"ps_hallucination_auditory": 0.26},
    "听到": {"ps_hallucination_auditory": 0.18},
    "有人在": {"ps_hallucination_auditory": 0.16, "ax_hypervigilance": 0.12},
    "低语": {"ps_hallucination_auditory": 0.24},

    # ------------- 医疗 / 药物 -------------
    "吃药": {"so_health_preoccupation": 0.10, "md_fatigue": 0.06, "ps_insight_loss": -0.06},
    "药": {"so_health_preoccupation": 0.06},
    "医院": {"ax_worry": 0.10, "so_health_preoccupation": 0.10},
    "医生": {"ax_worry": 0.08, "ps_insight_loss": -0.04},
    "诊断": {"ps_delusion_reference": 0.10, "ps_insight_loss": -0.06},
    "住院": {"tr_abandonment_fear": 0.10, "ax_worry": 0.10},
    "副作用": {"so_somatic_complaint": 0.12},

    # ------------- 亲密 / 安抚（负增量） -------------
    "喜欢你": {"md_worthlessness": -0.10, "tr_abandonment_fear": -0.08, "pd_emptiness": -0.10},
    "爱你": {"md_worthlessness": -0.12, "pd_emptiness": -0.12},
    "陪你": {"tr_abandonment_fear": -0.12, "ax_worry": -0.08},
    "我在": {"tr_abandonment_fear": -0.10, "ax_hypervigilance": -0.08},
    "别怕": {"ax_hypervigilance": -0.10, "ax_worry": -0.08},
    "抱": {"pd_emptiness": -0.12, "ax_worry": -0.06},
    "没事的": {"ax_worry": -0.10, "md_hopelessness": -0.06},
    "我懂": {"tr_shame": -0.08, "md_worthlessness": -0.06},
    "对不起": {"pd_rage": -0.10, "tr_abandonment_fear": -0.06},

    # ------------- 嘲讽 / 元话语 -------------
    "哈哈": {"pd_rage": 0.10, "ps_delusion_reference": 0.10},
    "就这": {"pd_rage": 0.14, "md_worthlessness": 0.08},
    "演的": {"ps_delusion_reference": 0.18, "pd_identity_problems": 0.12},
    "假的": {"ps_delusion_reference": 0.18, "ps_reality_testing_impair": 0.10},
    "开玩笑": {"ps_delusion_reference": 0.08, "pd_rage": 0.08},
    "剧本": {"ps_reality_testing_impair": 0.12, "di_derealization": 0.10},

    # ------------- 控制 / 审问 -------------
    "必须": {"pd_rage": 0.10, "ax_worry": 0.08},
    "不准": {"pd_rage": 0.12, "pd_identity_problems": 0.06},
    "听话": {"pd_rage": 0.12},
    "证明": {"ax_worry": 0.10, "ps_delusion_persecutory": 0.08},
    "为什么": {"ax_worry": 0.08, "oc_obsession_harm": 0.04},

    # ------------- 告别 / 丧失 -------------
    "再见": {"tr_abandonment_fear": 0.14, "ot_bereavement": 0.10},
    "永别": {"tr_abandonment_fear": 0.24, "ot_bereavement": 0.20},
    "最后": {"tr_abandonment_fear": 0.16, "ot_bereavement": 0.12},
    "死了": {"md_suicidal_ideation": 0.24, "ot_bereavement": 0.14},
    "葬礼": {"ot_bereavement": 0.22, "tr_grief": 0.18},

    # ------------- 自伤 / 死亡 -------------
    "自杀": {"md_suicidal_ideation": 0.30, "md_hopelessness": 0.18},
    "想死": {"md_suicidal_ideation": 0.28, "md_depressed_mood": 0.14},
    "活不下去": {"md_hopelessness": 0.24, "md_suicidal_ideation": 0.20},
    "解脱": {"md_suicidal_ideation": 0.18},
    "自残": {"pd_self_harm_urge": 0.26, "tr_emotional_dysregulation": 0.14},

    # ------------- 进食 / 体像 -------------
    "胖": {"ea_body_image_distortion": 0.24, "ea_restriction": 0.14},
    "瘦": {"ea_body_image_distortion": 0.18, "ea_restriction": 0.10},
    "体重": {"ea_body_image_distortion": 0.18},
    "吃": {"ea_binge": 0.08},
    "减肥": {"ea_restriction": 0.20, "ea_body_image_distortion": 0.16},
    "催吐": {"ea_purge": 0.26},

    # ------------- 物质 -------------
    "酒": {"su_craving": 0.18, "su_intoxication": 0.10},
    "喝": {"su_craving": 0.10},
    "烟": {"su_craving": 0.12},
    "戒": {"su_withdrawal": 0.16, "su_craving": 0.12},

    # ------------- 冲动 -------------
    "赌": {"ic_gambling": 0.26},
    "下注": {"ic_gambling": 0.24},
    "游戏": {"ic_gaming": 0.20},
    "上线": {"ic_gaming": 0.12},
    "氪": {"ic_gambling": 0.10, "ic_gaming": 0.14},

    # ------------- 强迫 -------------
    "脏": {"oc_obsession_contamination": 0.24, "oc_compulsion_washing": 0.16},
    "细菌": {"oc_obsession_contamination": 0.24},
    "洗手": {"oc_compulsion_washing": 0.22},
    "对齐": {"oc_obsession_symmetry": 0.20, "oc_compulsion_ordering": 0.16},
    "检查": {"oc_compulsion_checking": 0.22},
    "万一": {"oc_obsession_harm": 0.14, "ax_worry": 0.10},
    "顺序": {"oc_compulsion_ordering": 0.16},

    # ------------- 创伤 -------------
    "那次": {"tr_intrusion": 0.22, "tr_flashback": 0.14},
    "当时": {"tr_intrusion": 0.16},
    "血": {"tr_flashback": 0.20, "ps_hallucination_visual": 0.10},
    "噩梦": {"tr_nightmare": 0.24, "sl_nightmare": 0.20},
    "别碰我": {"tr_hyperarousal": 0.20, "pd_rage": 0.12},

    # ------------- 睡眠 -------------
    "睡不着": {"sl_insomnia": 0.22, "md_fatigue": 0.10},
    "失眠": {"sl_insomnia": 0.22},
    "困": {"sl_hypersomnia": 0.10, "md_fatigue": 0.08},
    "睡": {"sl_insomnia": 0.06},

    # ------------- 空虚 / 无意义 -------------
    "没意思": {"ng_anhedonia": 0.18, "md_anhedonia": 0.14},
    "无聊": {"ng_anhedonia": 0.12, "pd_emptiness": 0.12},
    "空": {"pd_emptiness": 0.16, "di_depersonalization": 0.10},
    "意义": {"md_hopelessness": 0.10},

    # ------------- 愤怒 -------------
    "恨": {"pd_rage": 0.18, "ma_irritability": 0.12},
    "烦": {"ma_irritability": 0.12, "ax_restlessness": 0.10},
    "气死": {"pd_rage": 0.20, "ic_anger_outburst": 0.14},

    # ------------- 学业 / 工作 -------------
    "工作": {"ax_worry": 0.10, "md_fatigue": 0.06},
    "考试": {"ax_worry": 0.14, "ax_anticipatory_anxiety": 0.12},
    "失业": {"md_worthlessness": 0.16, "ax_worry": 0.14},
    "老板": {"ax_worry": 0.10, "pd_rage": 0.06},

    # ------------- 家庭 -------------
    "妈": {"tr_shame": 0.08, "pd_identity_problems": 0.06},
    "爸": {"tr_shame": 0.08, "pd_rage": 0.06},
    "家": {"tr_abandonment_fear": 0.06},

    # ------------- 性 -------------
    "性": {"oc_obsession_sexual": 0.14, "ic_compulsive_sexual": 0.10},
    "身体": {"oc_body_dysmorphic": 0.12, "so_somatic_complaint": 0.10},
}


def keyword_to_symptoms(kw: str) -> Dict[str, float]:
    """把一个关键词映射到症状增量。支持双向子串匹配。"""
    out: Dict[str, float] = {}
    if not kw:
        return out
    for rule, weights in RULES.items():
        if rule in kw or (len(kw) >= 2 and kw in rule):
            for k, v in weights.items():
                out[k] = out.get(k, 0.0) + v
    return out
