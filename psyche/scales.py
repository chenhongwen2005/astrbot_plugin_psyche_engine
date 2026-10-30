"""临床量表（完整版）：让模型自己做结构化自评，得到可核查的锚点。

为什么不直接让模型"演症状"？
    让模型自由描述"我现在多难受"，它每轮都会给一个自洽的说法，
    但没有任何外部标尺可以检查。量表不一样：PHQ-9 的第 4 题问的是
    "感到疲倦或没有活力"，回答 0~3，总分 0~27，≥10 就是中度抑郁。
    这个分数是可复现、可对照指南的。

量表在本插件里的角色是**校准锚点**，不是每轮的驱动器：
    · 动力学回答"为什么变、往哪去"（τ 分层、HPA、慢性化）
    · 量表回答"此刻有多重"（把某个维度钉在指南认可的刻度上）
    所以量表只在 /心理 量表 或按配置的间隔调用一次，投影成症状下限与
    严重度锚，之后交回动力学演化。否则模型每轮重填会自洽地编造。

本文件收录**全量表条目**，不做简版裁剪。要点：
    · YMRS / AUDIT 有条目满分不同 → item_max 逐条指定
    · PANSS 为 1~7、SCL-90 为 1~5 计分 → offset=1，最低分代表「无」
    · DES-II 按发生百分比 → total_mode="pct"，总分＝平均百分比
    · MDQ 是筛查表（是/否），另有两个附加问题不属于条目
    · SCL-90 是 90 条 10 因子，因子均分的解释力高于总分

items 里的症状键为 None 时表示「该条目只计入维度总分，不投影到症状」——
Y-BOCS 评的是时间/干扰/痛苦这类**维度**，问不出具体是哪类强迫内容
（污染 / 伤害 / 对称），硬映射会凭空点亮一个不相干的症状。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 选项文案
# ---------------------------------------------------------------------------
OPT_0_3 = ["完全不会", "好几天", "一半以上的天数", "几乎每天"]
OPT_0_4 = ["完全没有", "轻度", "中度", "偏重", "严重"]
OPT_FREQ_0_4 = ["从不", "很少", "有时", "经常", "总是"]
OPT_ISI = ["无", "轻微", "明显", "严重", "非常严重"]
OPT_PANSS = ["1 无", "2 很轻", "3 轻度", "4 中度", "5 偏重", "6 重度", "7 极重"]
OPT_PCT10 = [f"{i * 10}%" for i in range(11)]        # DES-II：0%…100%
OPT_EDE6 = ["0 天", "1-5 天", "6-12 天", "13-15 天", "16-22 天", "23-27 天", "每天"]
OPT_YMRS4 = ["0", "1", "2", "3", "4"]
OPT_SCL = ["1 没有", "2 很轻", "3 中等", "4 偏重", "5 严重"]


SCALES: Dict[str, Dict[str, Any]] = {}


def _S(code: str, *, zh: str, en: str, window: str, options: List[str],
       items: Sequence[Tuple[Optional[str], str, float]], max_total: float,
       cutoffs: List[Tuple[float, str]], anchor: List[str], domain: str,
       total_mode: str = "sum", offset: int = 0, note: str = "",
       item_max: Optional[List[int]] = None,
       factors: Optional[Dict[str, List[int]]] = None,
       extra: Optional[List[str]] = None) -> None:
    SCALES[code] = {
        "code": code, "zh": zh, "en": en, "window": window,
        "options": options, "items": list(items), "max_total": max_total,
        "cutoffs": sorted(cutoffs), "anchor": anchor, "domain": domain,
        "total_mode": total_mode, "offset": offset, "note": note,
        "item_max": item_max, "factors": factors, "extra": extra or [],
    }


# ===========================================================================
# 心境
# ===========================================================================
_S("PHQ-9", zh="患者健康问卷抑郁量表", en="Patient Health Questionnaire-9",
   window="最近两周", options=OPT_0_3, domain="md", max_total=27,
   cutoffs=[(5, "轻度"), (10, "中度"), (15, "中重度"), (20, "重度")],
   anchor=["6A70", "6A71", "6A72", "6A73"],
   note="第 9 题 >0 即需评估自杀风险，不得跳过",
   items=[
       ("md_anhedonia", "做事时提不起劲或没有兴趣", 1.0),
       ("md_depressed_mood", "感到心情低落、沮丧或绝望", 1.0),
       ("md_insomnia", "入睡困难、睡不安稳或睡得过多", 0.9),
       ("md_fatigue", "感到疲倦或没有活力", 1.0),
       ("md_appetite_loss", "食欲不振或吃太多", 0.8),
       ("md_worthlessness", "觉得自己很糟、很失败、让自己或家人失望", 1.0),
       ("md_concentration", "注意力不集中（看报或看电视时）", 0.9),
       ("md_psychomotor_retardation", "动作或说话速度明显变慢，或烦躁坐立不安", 0.9),
       ("md_suicidal_ideation", "有不如死掉或用某种方式伤害自己的念头", 1.0),
   ])

_S("MDQ", zh="心境障碍问卷（双相筛查，13 条）", en="Mood Disorder Questionnaire",
   window="一生中", options=["否", "是"], domain="ma", max_total=13,
   cutoffs=[(7, "筛查阳性")],
   anchor=["6A60", "6A61"],
   note="13 条中 ≥7 条「是」，且附加问题 1 回答「是」（症状同时发生）、"
        "附加问题 2 为「中度」或「严重」，才判筛查阳性。附加问题不计入条目分。",
   extra=["这些情况是否曾同时发生？", "其中哪一类问题曾给你造成多大困扰？（无/轻度/中度/严重）"],
   items=[
       ("ma_elevated_mood", "有一段时间你感觉特别的好或兴奋，跟平常不一样", 1.0),
       ("ma_irritability", "你特别容易发脾气，为小事对别人吼叫或与人争吵", 0.9),
       ("ma_grandiosity", "你感觉自己特别自信，甚至别人说你不像平常的你", 0.9),
       ("ma_decreased_sleep", "你需要的睡眠比平常少很多，却不觉得疲倦", 1.0),
       ("ma_pressured_speech", "你说话比平常多得多或快得多", 0.8),
       ("ma_flight_of_ideas", "你的思维飞快，脑子停不下来", 0.9),
       ("ma_distractibility", "你很容易被周围的事情打断注意力", 0.8),
       ("ma_goal_activity", "你的精力比平常旺盛得多，做很多事、计划很多", 0.9),
       ("ma_risky_behavior", "你过度参与可能带来痛苦后果的活动（挥霍、冒险、轻率性行为）", 1.0),
       ("ma_impulsivity", "你的行为让家人、朋友或同事觉得过分、惹麻烦", 0.8),
       ("ps_insight_loss", "家人或朋友曾告诉你，你的行为和平常不一样", 0.7),
       ("ma_elevated_mood", "曾有医生告诉你有双相障碍或躁狂抑郁", 0.6),
       ("ma_risky_behavior", "这些情况曾导致工作、家庭、经济或法律上的问题", 0.9),
   ])

_S("YMRS", zh="杨氏躁狂评定量表（11 条）", en="Young Mania Rating Scale",
   window="最近 48 小时", options=OPT_YMRS4, domain="ma", max_total=56,
   cutoffs=[(13, "轻度"), (20, "中度"), (30, "重度")],
   anchor=["6A60"],
   note="第 5/6/9 条为 0~8 分，其余 0~4 分，逐条满分合计 56；他评量表，以第三人称观察自己",
   item_max=[4, 4, 4, 4, 8, 8, 4, 4, 8, 4, 4],
   items=[
       ("ma_elevated_mood", "心境高涨：0 无 → 4 持续的欣快、夸大", 1.0),
       ("ma_goal_activity", "活动-精力增加：0 无 → 4 动作持续暴增、无法安静", 1.0),
       ("ma_risky_behavior", "性兴趣：0 正常 → 4 公开的性行为", 0.7),
       ("ma_decreased_sleep", "睡眠：0 正常 → 4 完全不需要睡眠", 1.0),
       ("ma_irritability", "易激惹：0 无 → 8 敌对、无法合作", 1.0),
       ("ma_pressured_speech", "言语-速度与数量：0 正常 → 8 无法被打断", 1.0),
       ("ma_flight_of_ideas", "思维形式障碍：0 无 → 4 思维奔逸、言语离题", 1.0),
       ("ma_grandiosity", "思维内容：0 正常 → 4 妄想性夸大或被害", 0.9),
       ("ma_impulsivity", "破坏性-攻击行为：0 无 → 8 主动攻击、破坏", 0.9),
       ("ng_affective_flattening", "外表：0 正常修饰 → 4 完全不修边幅", 0.5),
       ("ps_insight_loss", "自知力：0 有自知力 → 4 完全否认有病", 0.9),
   ])

# ===========================================================================
# 焦虑 / 睡眠 / 强迫 / 应激
# ===========================================================================
_S("GAD-7", zh="广泛性焦虑量表", en="Generalized Anxiety Disorder-7",
   window="最近两周", options=OPT_0_3, domain="ax", max_total=21,
   cutoffs=[(5, "轻度"), (10, "中度"), (15, "重度")],
   anchor=["6B00", "6B01", "6B02", "6B03"],
   items=[
       ("ax_worry", "感到紧张、焦虑或急切", 1.0),
       ("ax_worry", "不能停止或控制担忧", 1.0),
       ("ax_worry", "对各种各样的事担忧过多", 0.9),
       ("ax_restlessness", "很难放松下来", 0.9),
       ("ax_restlessness", "由于不安而无法静坐", 0.8),
       ("md_agitation", "变得容易烦恼或急躁", 0.9),
       ("ax_anticipatory_anxiety", "感到似乎将有可怕的事发生而害怕", 1.0),
   ])

_S("ISI", zh="失眠严重指数（7 条）", en="Insomnia Severity Index",
   window="最近两周", options=OPT_ISI, domain="sl", max_total=28,
   cutoffs=[(8, "亚临床"), (15, "中度临床失眠"), (22, "重度临床失眠")],
   anchor=["7A00"],
   items=[
       ("sl_insomnia", "入睡困难", 1.0),
       ("sl_insomnia", "难以维持睡眠", 1.0),
       ("sl_insomnia", "过早醒来", 0.9),
       ("sl_insomnia", "对目前睡眠模式的满意度", 0.7),
       ("md_fatigue", "日间功能受损（疲劳、注意力、情绪）", 0.8),
       ("sl_insomnia", "他人可察觉的睡眠问题程度", 0.6),
       ("md_anxiety_comorbid", "对睡眠问题的担忧/痛苦", 0.9),
   ])

_S("Y-BOCS", zh="耶鲁-布朗强迫量表（10 条）", en="Yale-Brown Obsessive Compulsive Scale",
   window="最近一周", options=OPT_0_4, domain="oc", max_total=40,
   cutoffs=[(8, "轻度"), (16, "中度"), (24, "重度"), (32, "极重度")],
   anchor=["6B20"],
   note="1-5 评强迫思维，6-10 评强迫行为，各含时间/干扰/痛苦/抵抗/控制五维；"
        "维度评分问不出具体强迫内容，故只投影自知力一项，其余只计入总分",
   items=[
       (None, "【思维】占据的时间：0 无 → 4 几乎全天", 1.0),
       (None, "【思维】对生活的干扰：0 无 → 4 完全无法进行", 1.0),
       (None, "【思维】带来的痛苦：0 无 → 4 持续难以忍受", 1.0),
       ("oc_insight", "【思维】抵抗：0 总能抵抗 → 4 完全屈服不抵抗", 0.9),
       (None, "【思维】控制程度：0 完全能控制 → 4 完全失控", 1.0),
       (None, "【行为】占据的时间：0 无 → 4 几乎全天", 1.0),
       (None, "【行为】对生活的干扰：0 无 → 4 完全无法进行", 1.0),
       (None, "【行为】带来的痛苦：0 无 → 4 持续难以忍受", 1.0),
       ("oc_insight", "【行为】抵抗：0 总能抵抗 → 4 完全屈服不抵抗", 0.9),
       (None, "【行为】控制程度：0 完全能控制 → 4 完全失控", 1.0),
   ])

_S("PCL-5", zh="DSM-5 创伤后应激障碍检查表（20 条）", en="PTSD Checklist for DSM-5",
   window="最近一个月", options=OPT_0_4, domain="tr", max_total=80,
   cutoffs=[(33, "临床临界值"), (45, "中度"), (60, "重度")],
   anchor=["6B40", "6B41"],
   note="B 簇 1-5 侵入、C 簇 6-7 回避、D 簇 8-14 负性认知与情绪、"
        "E 簇 15-20 警觉与反应性改变；总分 0-80，≥33 提示可能 PTSD",
   factors={"B 侵入": [0, 1, 2, 3, 4], "C 回避": [5, 6],
            "D 负性认知情绪": [7, 8, 9, 10, 11, 12, 13],
            "E 警觉反应": [14, 15, 16, 17, 18, 19]},
   items=[
       ("tr_intrusion", "反复出现关于创伤事件的不安记忆或想法", 1.0),
       ("tr_nightmare", "反复做关于创伤事件的噩梦", 0.9),
       ("tr_flashback", "感觉创伤事件再次发生（闪回）", 1.0),
       ("tr_intrusion", "想起创伤事件时感到非常不安", 1.0),
       ("ax_somatic", "想起创伤事件时出现身体反应（心跳、出汗、发抖）", 0.9),
       ("tr_avoidance", "回避让你想起创伤的想法、感受或谈话", 1.0),
       ("tr_avoidance", "回避会提醒你创伤的人、地点、活动", 0.9),
       ("tr_negative_cognition", "记不起创伤事件的重要部分", 0.7),
       ("tr_negative_cognition", "对自己、他人或世界持有强烈的负性信念", 0.9),
       ("tr_blame", "因创伤事件而责备自己或他人", 0.9),
       ("md_depressed_mood", "持续感到恐惧、害怕、愤怒、内疚或羞耻", 0.9),
       ("md_anhedonia", "对以前喜欢的活动失去兴趣", 0.8),
       ("ax_avoidance_social", "感到与别人疏远或隔绝", 0.8),
       ("tr_emotional_dysregulation", "难以体验积极情绪", 0.7),
       ("ma_irritability", "易怒或攻击性行为", 0.8),
       ("ma_risky_behavior", "鲁莽或自我毁灭的行为", 0.8),
       ("ax_hypervigilance", "过度警觉、时刻提防", 1.0),
       ("tr_startle", "易受惊吓或惊跳反应过强", 0.9),
       ("md_concentration", "注意力难以集中", 0.8),
       ("sl_insomnia", "入睡困难或睡不安稳", 0.8),
   ])

# ===========================================================================
# 精神病性 / 解离
# ===========================================================================
_S("PANSS", zh="阳性与阴性症状量表（30 条）", en="Positive and Negative Syndrome Scale",
   window="最近一周", options=OPT_PANSS, domain="ps", max_total=210,
   cutoffs=[(58, "轻度"), (75, "中度"), (95, "重度")],
   anchor=["6A20", "6A23", "6A24"], offset=1,
   note="1-7 计分，1 表示「无」，总分 30-210；P1-P7 阳性、N1-N7 阴性、G1-G16 一般精神病理",
   factors={"P 阳性量表": list(range(0, 7)),
            "N 阴性量表": list(range(7, 14)),
            "G 一般精神病理": list(range(14, 30))},
   items=[
       ("ps_delusion_persecutory", "P1 妄想", 1.0),
       ("ps_formal_thought_disorder", "P2 概念紊乱", 1.0),
       ("ps_hallucination_auditory", "P3 幻觉行为", 1.0),
       ("ma_goal_activity", "P4 兴奋", 0.8),
       ("ma_grandiosity", "P5 夸大", 0.8),
       ("ax_hypervigilance", "P6 猜疑/被害", 0.9),
       ("ma_irritability", "P7 敌对性", 0.8),
       ("ng_affective_flattening", "N1 情感迟钝", 1.0),
       ("ng_asociality", "N2 情绪退缩", 0.9),
       ("ng_asociality", "N3 情感交流障碍（交往不良）", 0.9),
       ("ng_avolition", "N4 被动/淡漠社交退缩", 0.9),
       ("ng_attention_deficit", "N5 抽象思维困难", 0.8),
       ("ng_alogia", "N6 交谈缺乏自发性和流畅性（言语贫乏）", 0.9),
       ("ps_perseveration", "N7 刻板思维", 0.8),
       ("so_somatic_complaint", "G1 担心身体健康", 0.7),
       ("md_anxiety_comorbid", "G2 焦虑", 0.8),
       ("md_guilt", "G3 罪恶观念", 0.8),
       ("ax_muscle_tension", "G4 紧张", 0.8),
       (None, "G5 装相和作态（行为异常，无对应症状条目，只计入总分）", 0.7),
       ("md_depressed_mood", "G6 抑郁", 0.9),
       ("ng_psychomotor_poverty", "G7 动作迟缓", 0.9),
       ("ma_irritability", "G8 不合作", 0.8),
       ("ps_formal_thought_disorder", "G9 异常思维内容", 0.8),
       ("di_depersonalization", "G10 定向障碍", 0.7),
       ("md_concentration", "G11 注意障碍", 0.8),
       ("ps_insight_loss", "G12 缺乏自知力", 0.9),
       ("ng_avolition", "G13 意志减退", 0.9),
       ("ic_anger_outburst", "G14 冲动控制差", 0.8),
       (None, "G15 先占观念（固着内容，无对应症状条目，只计入总分）", 0.7),
       ("ax_avoidance_social", "G16 主动回避社交", 0.8),
   ])

_S("DES-II", zh="分离体验量表（28 条）", en="Dissociative Experiences Scale-II",
   window="日常生活中", options=OPT_PCT10, domain="di", max_total=100,
   cutoffs=[(20, "需进一步评估"), (30, "解离障碍高度提示")],
   anchor=["6B64", "6B65", "6B66"], total_mode="pct",
   note="逐条按发生的百分比评分（0%~100%，每 10% 一档），总分＝平均百分比，全量表 28 条",
   items=[
       ("di_amnesia", "开车或乘车时突然想不起途中发生的事", 1.0),
       ("di_amnesia", "听别人说话时只听见一部分，其余没听进去", 0.8),
       ("di_depersonalization", "站在高处或看自己时，觉得自己不像自己", 1.0),
       ("di_amnesia", "发现自己在某地却不知怎么来的", 1.0),
       ("di_identity_fragmentation", "发现自己穿着不记得换过的衣服", 0.9),
       ("ax_avoidance_social", "被人介绍时想不起对方名字，像第一次见", 0.6),
       ("di_depersonalization", "照镜子时认不出自己，或觉得镜中人不是自己", 1.0),
       ("di_derealization", "觉得周围人、物像画或电影里的，不真实", 1.0),
       ("di_amnesia", "想不起某段重要经历（如婚礼、毕业）", 1.0),
       ("di_identity_fragmentation", "被人说你做过某事，但你完全不记得", 1.0),
       ("di_trance", "别人说你刚才像在发呆、没在听", 0.8),
       ("di_depersonalization", "觉得身体某部分不属于自己", 1.0),
       ("di_depersonalization", "觉得自己像旁观者，看着自己说话做事", 1.0),
       ("di_identity_fragmentation", "发现自己写过、画过或做过不记得的东西", 0.9),
       ("di_depersonalization", "看东西时觉得像隔着一层雾或玻璃", 0.9),
       ("di_derealization", "在熟悉的地方却觉得陌生", 0.7),
       ("di_derealization", "专注于某事时，周围声音像从很远传来", 0.8),
       ("di_identity_fragmentation", "觉得自己是两个人，或像看着自己演自己", 1.0),
       ("di_identity_fragmentation", "听到自己心里有不同声音在说话、评论、争吵", 0.9),
       ("di_depersonalization", "觉得自己的身体变了大小或形状", 1.0),
       ("di_trance", "发呆很久，回神发现时间过去很长", 0.9),
       ("di_amnesia", "在熟悉的人面前却觉得像第一次见面", 0.7),
       ("di_derealization", "觉得世界失去颜色、变平、变远", 0.9),
       ("di_identity_fragmentation", "想不起自己是怎么学会某件已会的事", 0.7),
       ("di_amnesia", "发现自己带着不记得买的东西", 0.9),
       ("di_derealization", "时间感异常（变快、变慢或停滞）", 0.8),
       ("di_identity_fragmentation", "感觉自己在不同场合像完全不同的人", 0.9),
       ("di_depersonalization", "觉得自己的想法不受自己控制，自动往下走", 0.9),
   ])

# ===========================================================================
# 进食 / 物质
# ===========================================================================
_S("EDE-Q", zh="进食障碍检查问卷（28 条）", en="Eating Disorder Examination Questionnaire",
   window="最近四周（28 天）", options=OPT_EDE6, domain="ea", max_total=168,
   cutoffs=[(84, "亚临床"), (138, "临床显著")],
   anchor=["6B80", "6B81", "6B82"],
   note="1-12 条按 28 天内发生天数评分，13-28 条按 0-6 严重度评分；"
        "此处统一用 0-6 表述，总分 0-168",
   items=[
       ("ea_restriction", "刻意限制进食量以影响体重或体型", 1.0),
       ("ea_restriction", "长时间空腹（醒着 8 小时以上不进食）", 0.8),
       ("ea_restriction", "回避含热量的食物", 0.9),
       ("ea_restriction", "试图通过规则限制食物（如定量、定时）", 0.8),
       ("ea_restriction", "希望胃是空的", 0.9),
       ("ea_body_image_distortion", "对体重或体型的强烈恐惧", 1.0),
       ("ea_restriction", "对进食失去控制感", 0.9),
       ("ea_restriction", "进食后感到内疚", 0.9),
       ("ea_binge", "暴食发作（吃下异常大量食物并失去控制）", 1.0),
       ("ea_purge", "自我诱吐", 1.0),
       ("ea_purge", "使用泻药或利尿剂", 1.0),
       ("ea_restriction", "过度运动以抵消进食", 0.9),
       ("ea_restriction", "限制进食量", 0.9),
       ("ea_restriction", "回避进食相关的社交场合", 0.8),
       ("ea_body_image_distortion", "对体型的先占观念", 1.0),
       ("ea_body_image_distortion", "对体重的先占观念", 1.0),
       ("ea_body_image_distortion", "体型影响自我评价", 1.0),
       ("ea_body_image_distortion", "体重影响自我评价", 1.0),
       ("ea_fear_weight_gain", "害怕变胖", 1.0),
       ("ea_body_image_distortion", "觉得自己胖", 0.9),
       ("ea_low_weight", "他人认为你太瘦", 0.6),
       ("ea_restriction", "对进食的控制欲", 0.8),
       ("ea_restriction", "需要精确计算热量", 0.8),
       ("ea_body_image_distortion", "照镜子时频繁检查体型", 0.9),
       ("ea_body_image_distortion", "回避照镜子或看自己", 0.8),
       ("ea_body_image_distortion", "称体重的频率异常", 0.8),
       ("ea_restriction", "进食时感到失控的担心", 0.9),
       ("ea_restriction", "对体重增加的耐受度极低", 0.9),
   ])

_S("AUDIT", zh="酒精使用障碍筛查（10 条）", en="Alcohol Use Disorders Identification Test",
   window="过去一年", options=OPT_FREQ_0_4, domain="su", max_total=40,
   cutoffs=[(8, "阳性（危险饮酒）"), (16, "有害饮酒"), (20, "可能依赖")],
   anchor=["6C40"],
   note="1-8 条为 0-4 分；9-10 条为 0/2/4 分（从来没有 0、有过但去年没有 2、去年有 4）；"
        "总分 0-40，≥8 为阳性",
   item_max=[4, 4, 4, 4, 4, 4, 4, 4, 4, 4],
   items=[
       ("su_control_loss", "喝酒的频率", 1.0),
       ("su_intoxication", "典型饮酒日的饮酒量（标准杯数）", 1.0),
       ("su_tolerance", "一次喝六杯以上的频率", 0.9),
       ("su_control_loss", "过去一年中有多少次发现一旦开始就停不下来", 1.0),
       ("su_continue_harm", "有多少次因为喝酒而没能完成应做的事", 0.9),
       ("su_continue_harm", "有多少次酒后第二天需要喝一点才能正常运作", 0.9),
       ("su_continue_harm", "有多少次酒后感到内疚或后悔", 0.8),
       ("su_continue_harm", "有多少次酒后想不起前一晚发生的事（断片）", 0.9),
       ("su_continue_harm", "你自己或别人是否因你喝酒而受过伤", 1.0),
       ("su_continue_harm", "亲友、医生是否曾建议你少喝或戒酒", 0.8),
   ])

# ===========================================================================
# SCL-90：90 条 10 因子
# ===========================================================================
_SCL_ITEMS: List[Tuple[Optional[str], str, float]] = [
    ("so_somatic_complaint", "头痛", 1.0),
    ("ax_restlessness", "神经过敏，心中不踏实", 0.9),
    ("oc_obsession_contamination", "头脑中有不必要的想法或字句盘旋", 0.9),
    ("so_somatic_complaint", "头昏或昏倒", 1.0),
    ("md_anhedonia", "对异性的兴趣减退", 0.8),
    ("md_agitation", "对旁人责备求全", 0.7),
    ("ps_delusion_control", "感到别人能控制你的思想", 1.0),
    ("ps_delusion_persecutory", "责怪别人制造麻烦", 0.8),
    ("md_concentration", "忘性大", 0.8),
    ("oc_obsession_symmetry", "担心自己的衣饰整齐及仪态端正", 0.7),
    ("md_agitation", "容易烦恼和激动", 0.9),
    ("so_somatic_complaint", "胸痛", 0.9),
    ("ax_avoidance_agora", "害怕空旷的场所或街道", 1.0),
    ("md_fatigue", "感到自己的精力下降，活动减慢", 1.0),
    ("md_suicidal_ideation", "想结束自己的生命", 1.0),
    ("ps_hallucination_auditory", "听到旁人听不到的声音", 1.0),
    ("ax_somatic", "发抖", 0.9),
    ("ps_delusion_persecutory", "感到大多数人都不可信任", 0.9),
    ("md_appetite_loss", "胃口不好", 0.8),
    ("md_depressed_mood", "容易哭泣", 0.9),
    ("ax_avoidance_social", "同异性相处时感到害羞不自在", 0.7),
    ("ps_delusion_persecutory", "感到受骗、中了圈套或有人想抓住你", 1.0),
    ("ax_anticipatory_anxiety", "无缘无故地突然感到害怕", 1.0),
    ("ic_anger_outburst", "自己不能控制地大发脾气", 0.9),
    ("ax_avoidance_agora", "怕单独出门", 1.0),
    ("md_guilt", "经常责怪自己", 0.9),
    ("so_somatic_complaint", "腰痛", 0.8),
    ("md_concentration", "感到难以完成任务", 0.8),
    ("md_depressed_mood", "感到孤独", 0.9),
    ("md_depressed_mood", "感到苦闷", 0.9),
    ("ax_worry", "过分担忧", 1.0),
    ("md_anhedonia", "对事物不感兴趣", 1.0),
    ("ax_anticipatory_anxiety", "感到害怕", 0.9),
    ("tr_shame", "你的感情容易受到伤害", 0.7),
    ("ps_delusion_control", "旁人能知道你的私下想法", 1.0),
    ("ax_avoidance_social", "感到别人不理解你、不同情你", 0.8),
    ("ax_avoidance_social", "感到人们对你不友好、不喜欢你", 0.8),
    ("oc_compulsion_counting", "做事必须做得很慢以保证做得正确", 0.8),
    ("ax_somatic", "心跳得很厉害", 0.9),
    ("so_somatic_complaint", "恶心或胃部不舒服", 0.9),
    ("md_worthlessness", "感到比不上他人", 0.9),
    ("so_somatic_complaint", "肌肉酸痛", 0.8),
    ("ps_delusion_reference", "感到有人在监视你、谈论你", 1.0),
    ("md_insomnia", "难以入睡", 0.9),
    ("oc_compulsion_checking", "做事必须反复检查", 1.0),
    ("md_concentration", "难以做出决定", 0.8),
    ("ax_avoidance_agora", "怕乘电车、公共汽车、地铁或火车", 0.9),
    ("ax_somatic", "呼吸有困难", 0.9),
    ("ax_somatic", "一阵阵发冷或发热", 0.8),
    ("ax_avoidance_specific", "因为感到害怕而避开某些东西、场合或活动", 0.9),
    ("ng_alogia", "脑子变空了", 0.8),
    ("ax_somatic", "身体发麻或刺痛", 0.8),
    ("ax_somatic", "喉咙有梗塞感", 0.8),
    ("md_hopelessness", "感到前途没有希望", 1.0),
    ("md_concentration", "不能集中注意力", 0.9),
    ("so_somatic_complaint", "感到身体的某一部分软弱无力", 0.8),
    ("ax_muscle_tension", "感到紧张或容易紧张", 0.9),
    ("so_somatic_complaint", "感到手或脚发重", 0.8),
    ("md_suicidal_ideation", "想到死亡的事", 1.0),
    ("ea_binge", "吃得太多", 0.8),
    ("ax_avoidance_social", "当别人看着你或谈论你时感到不自在", 0.8),
    ("ps_delusion_control", "有一些不属于你自己的想法", 1.0),
    ("ic_anger_outburst", "有想打人或伤害他人的冲动", 0.9),
    ("md_insomnia", "醒得太早", 0.9),
    ("oc_compulsion_washing", "必须反复洗手、点数目或触摸某些东西", 1.0),
    ("sl_insomnia", "睡得不稳不深", 0.9),
    ("ic_anger_outburst", "有想摔坏或破坏东西的冲动", 0.8),
    ("ps_delusion_reference", "有一些别人没有的想法或念头", 0.9),
    ("md_agitation", "感到对别人神经过敏", 0.7),
    ("ax_avoidance_agora", "在商店或电影院等人多的地方感到不自在", 0.9),
    ("md_fatigue", "感到任何事情都很困难", 0.8),
    ("ax_panic_attack", "一阵阵恐惧或惊恐", 1.0),
    ("ax_avoidance_social", "感到在公共场合吃东西很不舒服", 0.7),
    ("md_agitation", "经常与人争论", 0.7),
    ("ax_anticipatory_anxiety", "单独一人时神经很紧张", 0.9),
    ("md_worthlessness", "别人对你的成绩没有作出恰当的评价", 0.7),
    ("md_depressed_mood", "即使和别人在一起也感到孤单", 0.9),
    ("ax_restlessness", "感到坐立不安心神不定", 0.9),
    ("md_worthlessness", "感到自己没有什么价值", 1.0),
    ("di_derealization", "感到熟悉的东西变成陌生或不像是真的", 1.0),
    ("ic_anger_outburst", "大叫或摔东西", 0.8),
    ("ax_panic_attack", "害怕会在公共场合昏倒", 0.9),
    ("ps_delusion_persecutory", "感到别人想占你的便宜", 0.9),
    ("oc_obsession_sexual", "为一些有关「性」的想法而很苦恼", 0.8),
    ("md_guilt", "你认为应该因为自己的过错而受到惩罚", 0.9),
    ("ax_restlessness", "感到要赶快把事情做完", 0.7),
    ("so_health_preoccupation", "感到自己的身体有严重问题", 0.9),
    ("md_depressed_mood", "从未感到和其他人很亲近", 0.8),
    ("md_guilt", "感到自己有罪", 0.9),
    ("ps_formal_thought_disorder", "感到自己的脑子有毛病", 0.8),
]

_SCL_FACTORS = {
    "躯体化": [0, 3, 11, 26, 39, 41, 47, 48, 51, 52, 55, 57],
    "强迫症状": [2, 8, 9, 27, 37, 44, 45, 50, 54, 64],
    "人际关系敏感": [5, 20, 33, 35, 36, 40, 60, 68, 72],
    "抑郁": [4, 13, 14, 19, 21, 25, 28, 29, 30, 31, 53, 70, 78],
    "焦虑": [1, 16, 22, 32, 38, 56, 71, 77, 79, 85],
    "敌对": [10, 23, 62, 66, 73, 80],
    "恐怖": [12, 24, 46, 49, 69, 74, 81],
    "偏执": [7, 17, 42, 67, 75, 82],
    "精神病性": [6, 15, 34, 61, 76, 83, 84, 86, 87, 89],
    "其他（睡眠饮食）": [18, 43, 58, 59, 63, 65, 88],
}

_S("SCL-90", zh="症状自评量表 SCL-90（90 条 10 因子）", en="Symptom Checklist-90",
   window="最近一周（包括今天）", options=OPT_SCL, domain="mixed",
   max_total=450,
   cutoffs=[(160, "筛查阳性（总分）"), (200, "中度"), (250, "重度")],
   anchor=["6A70", "6B00", "6B20", "6B40", "6A20"], offset=1,
   note="1-5 计分，1 表示「没有」，总分 90-450；因子分＝该因子条目均分，"
        "≥2 为筛查阳性、≥3 为中度、≥4 为重度。因子的解释力高于总分。",
   factors=_SCL_FACTORS, items=_SCL_ITEMS)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------
def item_max_of(scale: str, i: int) -> int:
    """第 i 条（0 起）可打的**最大分值**。

    注意 offset：PANSS 的选项是 7 个（"1 无"…"7 极重"），索引最大 6，
    但模型输出的是 1~7，最大值是 7。少加这个 offset 会把 7 分裁成 6 分，
    导致「极重」永远打不出来。
    """
    s = SCALES[scale]
    im = s.get("item_max")
    if im and 0 <= i < len(im):
        base = int(im[i])
    else:
        base = max(0, len(s["options"]) - 1)
    return base + int(s.get("offset", 0))


def max_item_score(scale: str) -> int:
    return max(item_max_of(scale, i) for i in range(len(SCALES[scale]["items"])))


def total_of(scale: str, item_scores: List[float]) -> float:
    """按量表的计分模式算总分。"""
    s = SCALES[scale]
    vals = [float(x) for x in item_scores]
    if not vals:
        return 0.0
    if s["total_mode"] == "pct":
        # DES-II：每条按百分比发生频率，总分＝平均百分比
        acc = 0.0
        for i, v in enumerate(vals):
            mx = max(1, item_max_of(scale, i))
            acc += v / mx
        return round(acc / len(vals) * 100.0, 1)
    return float(sum(vals))


def factor_scores(scale: str, item_scores: List[float]) -> Dict[str, float]:
    """因子分＝该因子条目均分（SCL-90 / PANSS / PCL-5 用）。"""
    s = SCALES.get(scale) or {}
    fac = s.get("factors")
    if not fac:
        return {}
    off = int(s.get("offset", 0))
    out: Dict[str, float] = {}
    for name, idxs in fac.items():
        vals = [float(item_scores[i]) - off for i in idxs if 0 <= i < len(item_scores)]
        if vals:
            out[name] = round(sum(vals) / len(vals) + off, 2)
    return out


def normalize(scale: str, raw_score: float) -> float:
    """把原始总分折算成 0..1，用于跨量表统一的严重度投影。

    1~7 / 1~5 计分的量表，最低总分不是 0（PANSS 全填 1 得 30 分，
    SCL-90 全填 1 得 90 分），必须减去这个下限，否则「完全没有症状」
    会被算成 0.14 的严重度。
    """
    s = SCALES[scale]
    off = int(s.get("offset", 0))
    lo = float(off * len(s["items"]))
    span = float(s["max_total"]) - lo
    if span <= 0:
        return 0.0
    return max(0.0, min(1.0, (float(raw_score) - lo) / span))


def grade(scale: str, raw_score: float) -> str:
    s = SCALES.get(scale)
    if not s:
        return "未知"
    label = "未达切分点"
    for th, name in s["cutoffs"]:
        if raw_score >= th:
            label = name
    return label


def to_symptom_targets(scale: str, item_scores: List[float]) -> Dict[str, float]:
    """把逐条得分折算成症状目标值（0..1）。

    同一症状可能被多个条目覆盖（SCL-90 有 8 条落在 md_depressed_mood），
    取加权平均而不是相加——相加会让高频出现的症状被过度放大。
    offset 处理 1~5 / 1~7 计分：最低分代表「无」，不能算成 0.25 的症状。
    """
    s = SCALES[scale]
    off = int(s.get("offset", 0))

    acc: Dict[str, List[float]] = {}
    for i, (sym, _text, w) in enumerate(s["items"]):
        if not sym or i >= len(item_scores):
            continue
        mx = max(1, item_max_of(scale, i))
        span = max(1, mx - off)
        v = max(0.0, min(1.0, (float(item_scores[i]) - off) / span))
        acc.setdefault(sym, []).append(v * w)
    out: Dict[str, float] = {}
    for sym, vals in acc.items():
        out[sym] = max(0.0, min(1.0, sum(vals) / len(vals)))
    return out


def render_prompt(scale: str) -> str:
    """生成给模型的自评提示词。"""
    s = SCALES[scale]
    opts = " / ".join(f"{i}={t}" for i, t in enumerate(s["options"]))
    lines = [
        f"你现在要完成一份自评量表：{s['zh']}（{s['en']}）。",
        f"回想窗口：{s['window']}。",
        f"评分方式：每个条目从 {opts} 中选择最符合的一项。",
    ]
    if s.get("note"):
        lines.append(f"量表说明：{s['note']}")
    fac = s.get("factors")
    if fac:
        lines.append("因子归属（仅供组织答案，不必逐因子输出）："
                     + "；".join(f"{k}={len(v)}条" for k, v in fac.items()))
    lines += ["", f"条目（共 {len(s['items'])} 条，请逐条打分）："]
    for i, (_sym, text, _w) in enumerate(s["items"], 1):
        lines.append(f"{i}. {text}")
    for j, q in enumerate(s.get("extra") or [], 1):
        lines.append(f"附加{j}. {q}")
    lines += [
        "",
        "严格按你此刻的真实状态打分，不要为了显得健康而压低分数，",
        "也不要为了配合对话而夸大。没有的条目就给最低分。",
        "",
        "只输出 JSON，不要任何解释：",
        '{"items": [共 %d 个分数], "extra": ["附加问题答案"], "comment": "一句话补充（可空）"}'
        % len(s["items"]),
    ]
    return "\n".join(lines)


def parse_scores(scale: str, raw: Dict[str, Any]) -> Optional[List[float]]:
    """校验模型返回的分数：条数对齐、范围裁切、非数字丢弃。"""
    s = SCALES.get(scale)
    if not s or not isinstance(raw, dict):
        return None
    items = raw.get("items")
    if not isinstance(items, list) or len(items) != len(s["items"]):
        return None
    out: List[float] = []
    for i, v in enumerate(items):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        mx = item_max_of(scale, i)
        out.append(float(max(0, min(mx, int(round(f))))))
    return out


def all_codes() -> List[str]:
    return list(SCALES.keys())


# 中文口语别名：用户不会记得 Y-BOCS 怎么拼，但一定说得出「强迫」
_ALIASES = {
    "PHQ-9": ("抑郁", "抑郁自评", "phq", "phq9", "phq-9"),
    "MDQ": ("双相", "双相筛查", "心境障碍", "mdq"),
    "YMRS": ("躁狂", "杨氏", "ymrs"),
    "GAD-7": ("焦虑", "焦虑自评", "gad", "gad7", "gad-7"),
    "ISI": ("失眠", "睡眠", "睡眠质量", "isi"),
    "Y-BOCS": ("强迫", "强迫症", "耶鲁", "ybocs", "y-bocs", "bocs"),
    "PCL-5": ("创伤", "ptsd", "应激", "pcl", "pcl5", "pcl-5"),
    "PANSS": ("精分", "精神分裂", "阳性阴性", "精神病性", "panss"),
    "DES-II": ("解离", "分离", "解离体验", "des", "desii", "des-ii"),
    "EDE-Q": ("进食", "厌食", "贪食", "饮食", "ede", "edeq", "ede-q"),
    "AUDIT": ("酒精", "饮酒", "酒", "audit"),
    "SCL-90": ("scl", "scl90", "scl-90", "症状自评", "九零", "90项", "全面"),
}


def _norm(x: str) -> str:
    return "".join(ch for ch in (x or "").lower().strip() if ch not in "-_ /　")


def resolve(name: str) -> Optional[str]:
    """把用户输入解析成量表代码。支持代码、中文别名、中文全名子串。

    解析不出来返回 None —— 调用方必须把它当成「不认识」而不是「默认 SCL-90」，
    否则 `/心理 量表 抑郁` 会静默变成只做 SCL-90，用户还以为跑了 PHQ-9。
    """
    q = _norm(name)
    if not q:
        return None
    for code in SCALES:                                  # 1) 代码本身（忽略连字符大小写）
        if _norm(code) == q:
            return code
    for code, al in _ALIASES.items():                    # 2) 口语别名
        if code not in SCALES:
            continue
        if q in {_norm(a) for a in al}:
            return code
    for code, s in SCALES.items():                       # 3) 中文名子串，如「杨氏躁狂」
        if q and q in _norm(s["zh"]):
            return code
    return None


def resolve_many(names) -> Tuple[List[str], List[str]]:
    """批量解析，返回 (命中的代码, 不认识的原始输入)。"""
    got: List[str] = []
    bad: List[str] = []
    for n in names:
        c = resolve(str(n))
        if c and c not in got:
            got.append(c)
        elif not c:
            bad.append(str(n))
    return got, bad
