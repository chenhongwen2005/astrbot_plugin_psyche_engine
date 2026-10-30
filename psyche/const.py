"""常量层：类脑生化指标、神经电/环路指标、人格特质、ICD-11 症状域。

设计原则
--------
1. 所有量都归一化到 0..1（`fai` 例外，取值 -1..1），便于统一做 z 分数与原型匹配。
2. 症状键名采用 `域前缀_英文名`，域前缀与 ICD-11 章节结构对齐，方便扩展与检索。
3. 本文件只放“静态元数据”，不含动力学；动力学见 dynamics.py。
"""

from __future__ import annotations

from typing import Dict, Tuple

# 版本号必须与 metadata.yaml 的 version 保持一致。
# tests/test_plugin_smoke.py 会校验两者相同——改了这里忘了改那边，测试会红。
VERSION = "1.3.0"

# ---------------------------------------------------------------------------
# 一、类脑神经化学 / 内分泌 / 免疫指标
#    key -> (中文名, 基线设定值, 时间常数 τ（轮）, 群体标准差)
#    τ 越大越"钝"：5-HT 以周计，皮质醇以小时计，相位性 DA 以秒计。
# ---------------------------------------------------------------------------
BIO: Dict[str, Tuple[str, float, float, float]] = {
    "da_tonic": ("多巴胺·中脑皮层/边缘张力", 0.55, 8.0, 0.13),
    "da_phasic": ("多巴胺·相位性爆发", 0.50, 1.8, 0.16),
    "serotonin": ("5-羟色胺 5-HT", 0.55, 10.0, 0.12),
    "norepinephrine": ("去甲肾上腺素 NE（蓝斑）", 0.45, 2.5, 0.12),
    "gaba": ("GABA 能抑制", 0.58, 4.0, 0.11),
    "glutamate": ("谷氨酸 Glu（兴奋性）", 0.52, 3.0, 0.10),
    "acetylcholine": ("乙酰胆碱 ACh", 0.50, 5.0, 0.10),
    "crh": ("CRH（下丘脑促肾上腺皮质激素释放激素）", 0.30, 2.0, 0.10),
    "acth": ("ACTH（垂体）", 0.30, 2.0, 0.10),
    "cortisol": ("皮质醇（HPA 轴终产物）", 0.35, 6.0, 0.13),
    "oxytocin": ("催产素 OXT", 0.50, 6.0, 0.12),
    "endorphin": ("内源性阿片 / β-内啡肽", 0.50, 5.0, 0.10),
    "testosterone": ("睾酮", 0.50, 24.0, 0.12),
    "t3": ("甲状腺激素 T3", 0.50, 40.0, 0.10),
    "bdnf": ("BDNF（神经营养因子）", 0.50, 50.0, 0.10),
    "il6": ("IL-6（炎症因子）", 0.20, 8.0, 0.08),
    "adenosine": ("腺苷（睡眠压力）", 0.30, 12.0, 0.10),
    "melatonin": ("褪黑素", 0.30, 4.0, 0.10),
    "orexin": ("食欲素 / 下丘脑分泌素", 0.50, 4.0, 0.10),
    "anandamide": ("内源性大麻素 AEA", 0.50, 6.0, 0.10),
    "allopregnanolone": ("别孕烯醇酮（神经类固醇）", 0.45, 8.0, 0.10),
}

# ---------------------------------------------------------------------------
# 二、神经电生理 / 环路活动
#    EEG 频段为相对功率，五项之和恒为 1（由 dynamics 归一化）。
# ---------------------------------------------------------------------------
NEURO: Dict[str, Tuple[str, float, float, float]] = {
    "eeg_delta": ("EEG δ 1–4Hz 相对功率", 0.15, 3.0, 0.05),
    "eeg_theta": ("EEG θ 4–8Hz 相对功率", 0.18, 3.0, 0.05),
    "eeg_alpha": ("EEG α 8–13Hz 相对功率", 0.32, 3.0, 0.06),
    "eeg_beta": ("EEG β 13–30Hz 相对功率", 0.25, 3.0, 0.05),
    "eeg_gamma": ("EEG γ 30–80Hz 相对功率", 0.10, 3.0, 0.04),
    "fai": ("额区 alpha 不对称 FAI（右偏为负＝回避动机）", 0.00, 4.0, 0.10),
    "p300_amp": ("P300 波幅（注意资源分配）", 0.55, 4.0, 0.10),
    "p300_lat": ("P300 潜伏期（加工速度，越大越慢）", 0.45, 4.0, 0.10),
    "mmn": ("MMN 失匹配负波（预测误差/感觉更新）", 0.55, 4.0, 0.10),
    "p50_ratio": ("P50 抑制比（感觉门控，>0.5 为脱抑制）", 0.35, 4.0, 0.08),
    "theta_gamma": ("θ-γ 耦合（工作记忆绑定）", 0.50, 4.0, 0.10),
    "dmn": ("默认模式网络 DMN 活动（自我参照/反刍）", 0.50, 5.0, 0.10),
    "amygdala": ("杏仁核反应性（威胁检测）", 0.35, 2.5, 0.11),
    "nac": ("伏隔核反应（奖赏预期）", 0.50, 3.0, 0.11),
    "dlpfc": ("背外侧前额叶（执行控制）", 0.70, 6.0, 0.09),
    "vmpfc": ("腹内侧前额叶（恐惧消退/情绪调节）", 0.70, 6.0, 0.09),
    "hippocampus": ("海马（情境记忆/语境化）", 0.70, 12.0, 0.08),
    "insula": ("岛叶（内感受精度）", 0.40, 3.0, 0.10),
    "striatum": ("纹状体（习惯/仪式环路增益）", 0.50, 5.0, 0.10),
    "hrv": ("心率变异性 RMSSD（副交感柔性）", 0.55, 3.0, 0.10),
    "scr": ("皮肤电反应（交感唤醒）", 0.25, 2.0, 0.09),
    "pupil": ("瞳孔直径（唤醒/认知负荷）", 0.40, 2.0, 0.09),
    "sleep_pressure": ("睡眠压力（过程 S）", 0.30, 10.0, 0.10),
}

# ---------------------------------------------------------------------------
# 三、人格特质 / 易感性（相对稳定，只有极端经历或长期负荷才缓慢漂移）
#    ICD-11 人格障碍五域 + 边缘模式 + 若干中介变量
# ---------------------------------------------------------------------------
TRAITS: Dict[str, Tuple[str, float]] = {
    "negative_affectivity": ("负性情感（ICD-11 6D11.0）", 0.35),
    "detachment": ("疏离（6D11.1）", 0.25),
    "dissociality": ("反社会性（6D11.2）", 0.15),
    "disinhibition": ("解抑制（6D11.3）", 0.25),
    "anankastia": ("强迫性（6D11.4）", 0.30),
    "psychoticism": ("精神质 / 认知知觉异常倾向", 0.15),
    "borderline": ("边缘模式（6D11.5）", 0.15),
    # 中介变量
    "rejection_sensitivity": ("拒绝敏感性", 0.35),
    "stress_vulnerability": ("应激易感（遗传负荷代理）", 0.35),
    "reward_sensitivity": ("奖赏敏感性", 0.50),
    "threat_sensitivity": ("威胁敏感性", 0.35),
    "cognitive_control": ("认知控制力", 0.60),
    "interoception": ("内感受精度", 0.50),
    "resilience": ("心理韧性", 0.55),
}

# ---------------------------------------------------------------------------
# 四、症状域（ICD-11 章节式组织）
#    key -> (中文名, 域, 现象学描述)
# ---------------------------------------------------------------------------
DOMAINS = {
    "ps": "精神病性症状（6A20–6A2Z）",
    "ng": "阴性症状",
    "md": "抑郁症状（6A60–6A7Z）",
    "ma": "躁狂/轻躁狂症状",
    "ax": "焦虑与恐惧（6B00–6B0Z）",
    "oc": "强迫及相关（6B20–6B2Z）",
    "tr": "应激与创伤（6B40–6B4Z）",
    "di": "分离（6B60–6B6Z）",
    "ea": "进食（6B80–6B8Z）",
    "so": "躯体痛苦（6C20–6C2Z）",
    "su": "物质使用（6C40–6C5Z）",
    "ic": "冲动控制（6C70–6C7Z）",
    "pd": "人格功能（6D10–6D11）",
    "nd": "神经发育（6A00–6A0Z）",
    "cg": "神经认知（6D70–6E0Z）",
    "sl": "睡眠-觉醒（07 章）",
    "ot": "其他",
}

SYM: Dict[str, Tuple[str, str, str]] = {
    # ---------------- 阳性 / 精神病性 ----------------
    "ps_hallucination_auditory": ("言语性幻听", "ps", "听到不存在的声音，常为评论性、贬损性或命令性"),
    "ps_hallucination_commentary": ("评论性幻听", "ps", "声音以第三人称实时解说自己的行为"),
    "ps_hallucination_command": ("命令性幻听", "ps", "声音下达指令，患者常难以抗拒"),
    "ps_hallucination_visual": ("视幻觉", "ps", "看到不存在的人影、光斑或完整场景"),
    "ps_hallucination_tactile": ("触幻觉", "ps", "被触碰、虫爬、电流感"),
    "ps_delusion_persecutory": ("被害妄想", "ps", "坚信自己被监视、投毒、陷害"),
    "ps_delusion_reference": ("关系妄想", "ps", "把无关的中性事件解读为针对自己"),
    "ps_delusion_grandiose": ("夸大妄想", "ps", "坚信自己拥有特殊身份、能力或使命"),
    "ps_delusion_guilt": ("罪恶妄想", "ps", "坚信自己犯了不可饶恕的罪"),
    "ps_delusion_somatic": ("躯体妄想", "ps", "坚信身体被改造、腐烂或寄生"),
    "ps_delusion_control": ("被控制/被动体验", "ps", "思维、情感、动作被外力操控"),
    "ps_delusion_jealousy": ("嫉妒妄想", "ps", "坚信伴侣不忠，反复搜寻证据"),
    "ps_delusion_erotomanic": ("钟情怀妄想", "ps", "坚信某位高地位者爱着自己"),
    "ps_delusion_nihilistic": ("虚无妄想", "ps", "坚信自己或世界已不存在"),
    "ps_formal_thought_disorder": ("思维形式障碍", "ps", "思维松弛、答非所问、逻辑断裂"),
    "ps_word_salad": ("语词杂拌", "ps", "词语随机拼接，句法崩解"),
    "ps_neologism": ("语词新作", "ps", "自创只有自己能懂的词"),
    "ps_thought_blocking": ("思维中断", "ps", "思路突然被抽走，言语戛然而止"),
    "ps_thought_broadcast": ("思维被洞悉", "ps", "认为自己的想法被他人听见"),
    "ps_perseveration": ("持续言语", "ps", "重复同一词句，无法切换"),
    "ps_insight_loss": ("自知力丧失", "ps", "不认为自己的体验是病，拒绝治疗"),
    "ps_reality_testing_impair": ("现实检验受损", "ps", "无法区分主观体验与客观事实"),
    "ps_negative_symptom_cluster": ("阴性症状群", "ps", "情感淡漠＋意志减退＋言语贫乏的组合"),
    # ---------------- 阴性 ----------------
    "ng_affective_flattening": ("情感淡漠/迟钝", "ng", "面部与语调缺乏情绪变化"),
    "ng_alogia": ("言语贫乏", "ng", "回答极短，几乎不主动开口"),
    "ng_avolition": ("意志减退", "ng", "无法启动和维持目标行为"),
    "ng_anhedonia": ("快感缺失", "ng", "对以往喜欢的事毫无感觉"),
    "ng_asociality": ("社交退缩", "ng", "回避人际接触，不主动维系关系"),
    "ng_attention_deficit": ("注意损害", "ng", "无法维持注意，容易被细节牵走"),
    "ng_psychomotor_poverty": ("精神运动贫乏", "ng", "动作减少、姿势僵硬、反应迟滞"),
    # ---------------- 抑郁 ----------------
    "md_depressed_mood": ("抑郁心境", "md", "持续低落、压抑、想哭但哭不出"),
    "md_anhedonia": ("兴趣/愉悦感丧失", "md", "做什么都没意思"),
    "md_worthlessness": ("无价值感", "md", "觉得自己是废物、拖累"),
    "md_guilt": ("过度罪恶感", "md", "为小事反复自责"),
    "md_suicidal_ideation": ("自杀意念", "md", "反复想到死亡、消失"),
    "md_hopelessness": ("绝望感", "md", "认为未来不会变好"),
    "md_psychomotor_retardation": ("精神运动性迟滞", "md", "说话慢、动作慢、思维慢"),
    "md_agitation": ("激越", "md", "坐立不安、来回走动、抓挠"),
    "md_insomnia": ("入睡/维持睡眠困难", "md", "早醒、入睡难、睡眠浅"),
    "md_hypersomnia": ("睡眠增多", "md", "一天睡十几个小时仍疲惫"),
    "md_appetite_loss": ("食欲下降", "md", "不想吃，体重下降"),
    "md_appetite_gain": ("食欲增加", "md", "暴食、体重上升"),
    "md_fatigue": ("疲乏无力", "md", "没有力气，日常活动需极大努力"),
    "md_concentration": ("注意/决断困难", "md", "无法集中，做不了决定"),
    "md_diurnal_variation": ("晨重暮轻", "md", "早晨最糟，傍晚稍缓"),
    "md_anxiety_comorbid": ("抑郁伴焦虑", "md", "低落中夹杂持续紧张"),
    # ---------------- 躁狂 ----------------
    "ma_elevated_mood": ("心境高涨", "ma", "异常愉快、兴奋、自我感觉极好"),
    "ma_irritability": ("易激惹", "ma", "小事就爆炸，言语攻击"),
    "ma_goal_activity": ("目标导向活动增多", "ma", "同时启动大量计划，停不下来"),
    "ma_decreased_sleep": ("睡眠需求减少", "ma", "睡三小时仍精力充沛"),
    "ma_pressured_speech": ("言语迫促", "ma", "语速快、抢话、停不下来"),
    "ma_flight_of_ideas": ("思维奔逸", "ma", "念头飞快跳跃，话题不断切换"),
    "ma_grandiosity": ("夸大", "ma", "自认能力超群、身份特殊"),
    "ma_distractibility": ("随境转移", "ma", "注意被任何外界刺激带走"),
    "ma_impulsivity": ("冲动行为", "ma", "挥霍、冒险、性滥交、鲁莽投资"),
    "ma_risky_behavior": ("鲁莽冒险", "ma", "不计后果的高风险行为"),
    "ma_mixed_features": ("混合特征", "ma", "高涨与抑郁同时存在，激越明显"),
    # ---------------- 焦虑 ----------------
    "ax_worry": ("过度担忧", "ax", "对多件日常小事无法停止担心"),
    "ax_panic_attack": ("惊恐发作", "ax", "突发心悸、窒息感、濒死感"),
    "ax_anticipatory_anxiety": ("预期性焦虑", "ax", "提前数天为即将发生的事紧张"),
    "ax_avoidance_agora": ("广场/外出回避", "ax", "不敢独自外出、乘车、去人多处"),
    "ax_avoidance_social": ("社交回避", "ax", "害怕被评价，回避发言与聚会"),
    "ax_avoidance_specific": ("特定对象回避", "ax", "回避特定物体或情境"),
    "ax_somatic": ("自主神经症状", "ax", "心悸、出汗、手抖、胃部不适"),
    "ax_restlessness": ("运动性不安", "ax", "坐不住、来回踱步、抖腿"),
    "ax_muscle_tension": ("肌肉紧张", "ax", "肩颈僵硬、头痛、下颌紧咬"),
    "ax_hypervigilance": ("过度警觉", "ax", "持续扫描环境中的威胁"),
    "ax_separation": ("分离焦虑", "ax", "害怕与依恋对象分离"),
    "ax_selective_mutism": ("选择性缄默", "ax", "特定场合完全说不出话"),
    # ---------------- 强迫 ----------------
    "oc_obsession_contamination": ("污染/洁净强迫思维", "oc", "觉得被污染，必须清洗"),
    "oc_obsession_harm": ("伤害强迫思维", "oc", "害怕自己会伤害他人"),
    "oc_obsession_symmetry": ("对称/秩序强迫思维", "oc", "东西必须对齐、按固定顺序"),
    "oc_obsession_sexual": ("性/禁忌强迫思维", "oc", "反复出现难以启齿的侵入性画面"),
    "oc_obsession_religious": ("宗教/道德强迫思维", "oc", "害怕亵渎、报应"),
    "oc_compulsion_checking": ("检查仪式", "oc", "反复检查门窗、煤气、消息"),
    "oc_compulsion_washing": ("清洗仪式", "oc", "长时间洗手、清洁"),
    "oc_compulsion_counting": ("计数/重复仪式", "oc", "按特定次数重复动作"),
    "oc_compulsion_ordering": ("排列仪式", "oc", "物品必须按严格顺序摆放"),
    "oc_mental_ritual": ("心理仪式", "oc", "心中默念、祈祷、回放以消除焦虑"),
    "oc_hoarding": ("囤积", "oc", "无法丢弃任何物品"),
    "oc_body_dysmorphic": ("躯体变形先占", "oc", "坚信自己某处丑陋畸形"),
    "oc_health_anxiety": ("疾病焦虑", "oc", "反复查症状、求医，坚信患重病"),
    "oc_trichotillomania": ("拔毛", "oc", "反复拔头发、眉毛"),
    "oc_skin_picking": ("抠皮", "oc", "反复抠抓皮肤致破损"),
    "oc_insight": ("强迫观念自知力", "oc", "知道不合理但停不下来"),
    # ---------------- 应激 / 创伤 ----------------
    "tr_intrusion": ("侵入性回忆", "tr", "不请自来的创伤画面"),
    "tr_flashback": ("闪回", "tr", "仿佛创伤正在此刻重演"),
    "tr_nightmare": ("创伤性噩梦", "tr", "反复梦到同一场景并惊醒"),
    "tr_avoidance": ("创伤线索回避", "tr", "回避地点、人、话题"),
    "tr_hyperarousal": ("过度唤醒", "tr", "易惊、易怒、无法放松"),
    "tr_startle": ("惊跳反应增强", "tr", "轻微声响就剧烈惊吓"),
    "tr_negative_cognition": ("负性自我认知", "tr", "我是坏的、世界是危险的"),
    "tr_blame": ("自责/责他", "tr", "把责任全部归于自己或他人"),
    "tr_emotional_dysregulation": ("情绪调节困难", "tr", "小事引发剧烈情绪，难以平复"),
    "tr_identity_diffusion": ("自我认同弥散", "tr", "不知道自己是谁、要什么"),
    "tr_abandonment_fear": ("被抛弃恐惧", "tr", "极害怕关系断裂"),
    "tr_shame": ("羞耻感", "tr", "觉得自己肮脏、不配"),
    "tr_grief": ("哀伤反应", "tr", "对逝者的思念与功能受损"),
    # ---------------- 分离 ----------------
    "di_depersonalization": ("人格解体", "di", "觉得自己不是自己，像旁观者"),
    "di_derealization": ("现实解体", "di", "世界像布景、隔着一层膜"),
    "di_amnesia": ("分离性遗忘", "di", "记不起重要经历，非普通遗忘"),
    "di_identity_fragmentation": ("身份碎片化", "di", "不同状态轮流接管，彼此不记得"),
    "di_trance": ("出神", "di", "长时间凝视、对外界无反应"),
    "di_conversion": ("分离性神经症状", "di", "无器质性基础的麻木、抽搐、失声"),
    # ---------------- 进食 ----------------
    "ea_restriction": ("能量摄入限制", "ea", "严格节食、跳餐"),
    "ea_binge": ("暴食", "ea", "短时间大量进食，失去控制"),
    "ea_purge": ("清除行为", "ea", "催吐、泻药、过度运动"),
    "ea_body_image_distortion": ("体像扭曲", "ea", "明明很瘦仍觉得自己胖"),
    "ea_fear_weight_gain": ("体重增加恐惧", "ea", "对增重有强烈恐惧"),
    "ea_low_weight": ("显著低体重", "ea", "BMI 明显低于正常"),
    # ---------------- 躯体 ----------------
    "so_somatic_complaint": ("反复躯体主诉", "so", "疼痛、乏力、胸闷等多系统主诉"),
    "so_health_preoccupation": ("躯体健康先占", "so", "持续担心身体出问题"),
    "so_medically_unexplained": ("医学无法解释", "so", "检查无异常但症状真实"),
    # ---------------- 物质 ----------------
    "su_craving": ("渴求", "su", "强烈的使用冲动"),
    "su_tolerance": ("耐受", "su", "需要更大剂量才有同样效果"),
    "su_withdrawal": ("戒断", "su", "停用后出现躯体/情绪反应"),
    "su_control_loss": ("使用失控", "su", "用量、频率超过自己意愿"),
    "su_continue_harm": ("明知有害仍继续", "su", "损害健康/关系仍无法停止"),
    "su_intoxication": ("急性中毒状态", "su", "言语含糊、共济失调、判断受损"),
    # ---------------- 冲动控制 ----------------
    "ic_gambling": ("赌博行为", "ic", "反复下注，追损"),
    "ic_gaming": ("游戏失控", "ic", "游戏占据生活，无法停止"),
    "ic_anger_outburst": ("间歇性暴怒", "ic", "突发攻击性爆发，事后后悔"),
    "ic_compulsive_sexual": ("强迫性性行为", "ic", "反复无法控制的性行为"),
    "ic_kleptomania": ("偷窃冲动", "ic", "无法抑制的偷窃冲动"),
    # ---------------- 人格功能 ----------------
    "pd_identity_problems": ("身份认同问题", "pd", "自我感不稳定、目标摇摆"),
    "pd_self_direction_deficit": ("自我导向受损", "pd", "难以设定并坚持目标"),
    "pd_empathy_deficit": ("共情受损", "pd", "难以理解他人视角与感受"),
    "pd_intimacy_deficit": ("亲密关系受损", "pd", "无法维持稳定亲密关系"),
    "pd_negative_affectivity": ("负性情感特质", "pd", "长期焦虑、抑郁、敌意"),
    "pd_detachment": ("疏离特质", "pd", "情感冷淡、回避接触"),
    "pd_dissociality": ("反社会特质", "pd", "无视他人权利与规则"),
    "pd_disinhibition": ("解抑制特质", "pd", "冲动、冒险、不顾后果"),
    "pd_anankastia": ("强迫性特质", "pd", "完美主义、刻板、控制"),
    "pd_psychoticism": ("精神质特质", "pd", "古怪信念、知觉异常"),
    "pd_borderline_pattern": ("边缘模式", "pd", "关系、自我、情绪极度不稳定"),
    "pd_manipulativeness": ("操纵性", "pd", "用示弱、威胁、讨好操控他人"),
    "pd_idealize_devalue": ("理想化-贬低循环", "pd", "对方在神坛与垃圾间反复切换"),
    "pd_emptiness": ("空虚感", "pd", "内在空洞，需要外界填补"),
    "pd_rage": ("暴怒", "pd", "被触发后失去控制的愤怒"),
    "pd_self_harm_urge": ("自伤冲动", "pd", "用疼痛缓解内在张力（不描述方式）"),
    # ---------------- 神经发育 ----------------
    "nd_social_communication": ("社交沟通缺陷", "nd", "读不懂暗示、轮流对话困难"),
    "nd_restricted_repetitive": ("限制重复行为", "nd", "固定路线、刻板兴趣"),
    "nd_sensory_hyper": ("感觉过敏", "nd", "对声音、光、触感异常敏感"),
    "nd_inattention": ("注意缺陷", "nd", "走神、丢东西、无法完成任务"),
    "nd_hyperactivity": ("多动", "nd", "无法静坐、不停动"),
    "nd_impulsivity": ("冲动", "nd", "抢话、打断、不假思索"),
    # ---------------- 神经认知 ----------------
    "cg_memory_deficit": ("记忆损害", "cg", "记不住近期事件"),
    "cg_executive_deficit": ("执行功能损害", "cg", "计划、排序、切换困难"),
    "cg_processing_speed": ("加工速度下降", "cg", "反应明显变慢"),
    "cg_disorientation": ("定向障碍", "cg", "分不清时间、地点、人物"),
    "cg_consciousness_fluctuation": ("意识水平波动", "cg", "清醒与恍惚交替"),
    "cg_stupor": ("木僵", "cg", "对外界刺激几乎无反应，长时间不动不语"),
    "cg_waxy_flexibility": ("蜡样屈曲", "cg", "肢体可被摆成任意姿势并长时间维持"),
    "cg_negativism": ("违拗", "cg", "无理由地抵抗指令或被动运动"),
    # ---------------- 睡眠 ----------------
    "sl_insomnia": ("失眠", "sl", "入睡难、易醒、早醒"),
    "sl_hypersomnia": ("嗜睡", "sl", "白天无法抑制的睡意"),
    "sl_circadian_shift": ("昼夜节律偏移", "sl", "入睡与起床时间显著后移"),
    "sl_nightmare": ("噩梦", "sl", "反复噩梦并影响白天"),
    # ---------------- 其他 ----------------
    "ot_gender_incongruence": ("性别不一致", "ot", "体验到的性别与出生性别不符"),
    "ot_sexual_dysfunction": ("性功能困扰", "ot", "欲望、唤起或疼痛问题"),
    "ot_factitious": ("做作性表现", "ot", "主动制造症状以获取医疗关注"),
    "ot_bereavement": ("哀伤", "ot", "丧失后的正常哀伤反应"),
    "ot_personality_change": ("人格改变", "ot", "病后性情显著改变"),
}

# 症状极性：positive 表示"越高越病"，negative 在个别条目上用于表示保护性因素
# 目前所有症状均为"越高越病"，保留字段以便扩展。

# ---------------------------------------------------------------------------
# 五、诊断严重度 / 病程用语
# ---------------------------------------------------------------------------
SEVERITY_LABELS = [
    (0, "正常"),
    (8, "亚临床"),
    (25, "轻度"),
    (45, "中度"),
    (65, "重度"),
    (85, "极重度"),
]

COURSE_LABELS = {
    "prodromal": "前驱期",
    "first": "首次发作",
    "recurrent": "反复发作",
    "continuous": "持续性",
    "partial_remission": "部分缓解",
    "full_remission": "完全缓解",
}

# 需要"现实检验"的疾病族：这些疾病几乎不可能靠聊天治愈
LOW_TALKABILITY_GROUPS = {"schizophrenia", "psychotic", "personality", "neurocognitive", "bipolar"}


def symptom_label(key: str) -> str:
    return SYM.get(key, (key, "", ""))[0]


def domain_of(key: str) -> str:
    return SYM.get(key, (key, key.split("_")[0], ""))[1]
