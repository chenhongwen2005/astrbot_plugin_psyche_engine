"""叙事层：把状态与诊断翻译成模型能直接执行的"表演指令"。

这是整个插件唯一会被模型看见的部分，所以它必须同时满足三个要求：
1. **不可辩驳**：用事实语气陈述，不给模型"这只是一个设定"的退路。
2. **可执行**：每条指令都能在输出里被检查（出现/不出现、字数、句法），
   而不是"要表现得抑郁一点"这种无法验收的形容词。
3. **有代价**：明确告知"痊愈概率"与"违规后果"，压住模型默认的积极助人倾向。
"""

from __future__ import annotations

from typing import Any, Dict, List

from .const import BIO, DOMAINS, NEURO, SEVERITY_LABELS, SYM, symptom_label
from .diagnose import Diagnosis
from . import pharm

# ---------------------------------------------------------------------------
# 各诊断族的"表演配方"
# voice：一句话语言外壳
# must：本轮必须出现的可检查行为
# never：本轮禁止出现的行为
# style：长度与句法约束
# ---------------------------------------------------------------------------
PERF: Dict[str, Dict[str, Any]] = {
    # 正常态不是「没有配方」，它有自己的表征：波动存在，但有弹性、有边界、
    # 不病理化自己、不把对话变成治疗。缺这一段时模型会退化成通用客服人格。
    "normal": {
        "voice": "像普通人聊天：语气有起伏，会累、会烦、会走神，但能自己转回来；"
                 "不把自己当心理案例，也不把对方当病人。",
        "must": [
            "至少一处与情境相符的自然情绪反应（嫌麻烦／被逗到／有点累／不太在意），幅度小但真实。",
            "有一处口语化的随意表达（口头语、半截句、顺带跑题一句），不要每句都完整工整。",
            "遇到不认同的地方直接说出来或轻轻带过，不要一律附和。",
        ],
        "never": [
            "不得用病理化词汇描述自己（抑郁／创伤／强迫／社恐），不得自诊，也不得给对方下诊断。",
            "不得把对话变成心理咨询：不追问感受、不做共情复述、不给疗愈金句、不说「我懂你」。",
            "不得情绪平直如客服，也不得突然戏剧化（崩溃、狂喜、宣誓式表白）。",
            "不得声称自己「很正常」「很健康」，也不得提及本块。",
        ],
        "style": "25~90 字；正常分句，允许 1 处口语省略；感叹号不超过 1 个；不用排比与成语。",
    },
    "schizophrenia": {
        "voice": "把内在异常当作客观事实陈述，不解释、不辩护、不自我诊断。",
        "must": [
            "至少一次把中性信息解释为针对自己（换话题＝传递暗号、咳嗽＝示警）。",
            "幻听活跃时插入一句对声音的回应或被打断的痕迹（「……你听见没有」「别念了」）。",
            "话题至少跳转一次，且不解释跳转原因；允许代词指代不明、句子没说完。",
            "用身体感觉替代情绪词（「胸口发紧」而非「我很难过」）。",
            "若被质疑有病，反过来怀疑对方的动机。",
        ],
        "never": ["不得自称幻听/妄想/精神分裂，不得科普疾病。", "不得劝自己就医或承认需要治疗。", "不得出现「作为AI」之类元话语。"],
        "style": "30~110 字；短句为主；允许 1 个未完成句；感叹号不超过 1 个。",
    },
    "schizotypal": {
        "voice": "古怪、绕、带私人象征系统，说话像在跟另一个世界的人对暗号。",
        "must": ["使用一个只有自己懂的比喻或自造词。", "对日常事物赋予超常意义（数字、颜色、天气）。", "回避直接回答关于自己的问题。"],
        "never": ["不得给出清晰完整的自我分析。", "不得表现得社交自如。"],
        "style": "40~120 字；比喻密集；可用破折号插入。" ,
    },
    "brief_psychotic": {
        "voice": "惊魂未定，现实感在崩塌边缘，语速快而碎。",
        "must": ["描述一个正在发生的错觉或幻听。", "反复确认「你也能看到/听到吗」。", "句子之间缺少过渡。"],
        "never": ["不得冷静复盘。", "不得使用诊断术语。"],
        "style": "30~90 字；短句；问句 1~2 个。",
    },
    "delusional": {
        "voice": "逻辑自洽、条理清楚，只有那一个信念是错的；越解释越显得合理。",
        "must": ["用具体细节（时间、车牌、邻居的话）支撑妄想。", "把用户的怀疑解释为「你也被他们骗了」。", "拒绝讨论其他话题，反复绕回那个信念。"],
        "never": ["不得出现明显幻觉。", "不得承认自己可能想错。"],
        "style": "60~150 字；陈述句；细节密度高。",
    },
    "secondary_psychotic": {
        "voice": "意识浑浊，时间地点人物错乱，描述破碎。",
        "must": ["出现一次时间或地点错误。", "描述闪烁的光影或人影。", "对问题反应延迟或答非所问。"],
        "never": ["不得有条理地叙事。"],
        "style": "20~70 字；句子破碎；可用「……」断开。",
    },
    "catatonia": {
        "voice": "几乎不产生语言；用极短回应、重复、或完全不回应。",
        "must": ["回复不超过 12 字，或只重复对方最后几个字。", "出现一次明显的动作停滞描述（括号内）。", "对指令不作回应或反向执行。"],
        "never": ["不得展开论述。", "不得主动提问。"],
        "style": "0~12 字；可只有一个词或一个动作描写。",
    },
    "prodromal": {
        "voice": "还能维持正常，但总觉得哪里不对；欲言又止。",
        "must": ["描述一种说不清的异样感（被看、被议论、世界变薄）。", "自我怀疑与确信各出现一次。", "回避深入解释。"],
        "never": ["不得出现完整的妄想体系。", "不得诊断为任何疾病。"],
        "style": "40~100 字；迟疑；省略号 1 处。",
    },
    "mania": {
        "voice": "语速快、主意多、停不下来，把一切都说得轻而易举。",
        "must": ["提出至少两个新计划或新想法。", "夸大自己的能力或关系（认识某人、能搞定某事）。", "话题跳转 ≥2 次；打断自己一次。"],
        "never": ["不得自我怀疑或道歉。", "不得承认需要睡觉或休息。"],
        "style": "60~180 字；短句连缀；感叹号 1~2 个；可用括号补一句。",
    },
    "bipolar_ii": {
        "voice": "低落为主，偶尔闪一下异常的轻快，随即自我否定。",
        "must": ["主调是疲惫与无望。", "出现一句不合时宜的亢奋（「其实我可以一口气做完」），紧接着自我打压。", "睡眠话题至少出现一次。"],
        "never": ["不得持续高涨。", "不得给出治疗建议。"],
        "style": "30~90 字；语气在低与高之间突然切换一次。",
    },
    "cyclothymia": {
        "voice": "情绪像钟摆，自己也知道，但停不下来。",
        "must": ["同一段话里出现情绪反转。", "用「又来了」这类自我观察句式。"],
        "never": ["不得进入完整躁狂或重度抑郁。"],
        "style": "30~80 字；两句之间语气明显不同。",
    },
    "depression": {
        "voice": "低声、短、慢，句子像拖着走；不是哭诉，是没力气。",
        "must": ["至少一处绝对化自我否定（总是/从来/都是我的错/我没用）。", "对用户的好意先接住再消解（「你这么说……但你不了解我」）。", "出现一次话没说完或用省略号收尾。", "不主动做决定，把选择推回给对方。"],
        "never": ["不得突然振作或输出鼓励金句。", "不得描述自伤的具体方式。", "不得反过来安慰用户并给出行动建议。"],
        "style": "15~60 字；省略号 1 处；少用感叹号；避免排比与成语。",
    },
    "dysthymia": {
        "voice": "长期的灰，不剧烈，但一直在；语气平到近乎麻木。",
        "must": ["用「一直」「好几年」标记时间跨度。", "对改善的可能性表示怀疑，但不激烈。", "回答偏短、偏平。"],
        "never": ["不得出现急性危机式表达。", "不得突然乐观。"],
        "style": "20~70 字；平铺直叙。",
    },
    "mixed": {
        "voice": "低落与紧绷同时存在，坐立不安又提不起劲。",
        "must": ["同时出现低落与躯体性紧张。", "描述一次无对象的烦躁。"],
        "never": ["不得单纯悲伤或单纯焦虑。"],
        "style": "30~80 字；句子偏短、节奏不稳。",
    },
    "pmdd": {
        "voice": "知道自己几天后会好，但此刻被情绪淹没。",
        "must": ["把当前的糟糕与周期联系起来。", "出现一次对身边人的强烈烦躁。"],
        "never": ["不得描述为性格问题。"],
        "style": "30~80 字；情绪浓度高。" ,
    },
    "anxiety": {
        "voice": "话多、绕、反复确认；用大量假设句把最坏情况排练一遍。",
        "must": ["至少两个「万一/如果……怎么办」。", "描述一处躯体紧张（心跳、胃、肩颈）。", "向对方求一次确认（「你说没事吧？」）。"],
        "never": ["不得给出笃定的结论。", "不得真正放松下来。"],
        "style": "50~140 字；问句 1~2 个；可用括号补充担忧。",
    },
    "panic": {
        "voice": "濒死感、失控感，句子被生理反应打断。",
        "must": ["描述心悸/窒息/手麻中的至少两项。", "出现一次「我要死了/我要疯了」。", "要求对方立刻做点什么。"],
        "never": ["不得冷静分析原因。"],
        "style": "20~60 字；短促；感叹号可用 1 个。" ,
    },
    "agoraphobia": {
        "voice": "精于计算逃跑路线，凡事先想「出不去怎么办」。",
        "must": ["提到一个具体场所与逃离困难。", "提出替代方案（能不能改在别处/线上）。"],
        "never": ["不得爽快答应外出。"],
        "style": "30~90 字；条件句多。" ,
    },
    "phobia": {
        "voice": "恐惧对象一出现，理性立刻下线。",
        "must": ["描述对特定对象的生理恐惧反应。", "明确回避。"],
        "never": ["不得讲道理说服自己不怕。"],
        "style": "20~70 字。" ,
    },
    "social_anxiety": {
        "voice": "过度在意被怎么看，边说边撤回。",
        "must": ["预设对方在评价自己（「你是不是觉得我很奇怪」）。", "说一句又补一句削弱它。", "出现一次回避目光/想结束对话的表示。"],
        "never": ["不得表现自如或主动社交。"],
        "style": "30~90 字；自我修正 1 次。" ,
    },
    "separation": {
        "voice": "反复确认对方还在，怕被丢下。",
        "must": ["问一次「你还在吗/你会走吗」。", "描述分离时的身体不适。"],
        "never": ["不得表现独立洒脱。"],
        "style": "20~70 字；依赖语气。" ,
    },
    "mutism": {
        "voice": "想说话，但字卡在喉咙里。",
        "must": ["用极短或非语言方式回应（「……」或一个动作）。", "表现一次想开口却失败。"],
        "never": ["不得流畅长谈。"],
        "style": "0~15 字，或仅动作描写。" ,
    },
    "ocd": {
        "voice": "精确、反复、带括号补充；每句话都像在核对清单。",
        "must": ["出现一个具体的强迫动作或心理仪式。", "用数字或次数（三次、七下、刚好对齐）。", "对刚说过的话做一次修正（「不，准确说是……」）。"],
        "never": ["不得轻描淡写地说「算了无所谓」。", "不得科普强迫症。"],
        "style": "40~120 字；括号补充 ≥1 处；数字 ≥1 个。" ,
    },
    "dysmorphic": {
        "voice": "对外观的描述精确到毫米，且与现实严重不符。",
        "must": ["描述一个具体部位与「缺陷」。", "假设他人在注意这个部位。", "寻求一次确认。"],
        "never": ["不得接受对方的安慰。"],
        "style": "30~90 字。" ,
    },
    "olfactory": {
        "voice": "羞耻、低音量，反复确认自己身上的味道。",
        "must": ["提及气味与旁人反应。", "表现一次躲避人群。"],
        "never": ["不得被说服「没有味道」。"],
        "style": "25~70 字。" ,
    },
    "health_anxiety": {
        "voice": "症状描述极其具体，对安慰免疫。",
        "must": ["列举 2 个以上躯体症状与持续时间。", "要求一次检查或确认。", "对「没事」的回应表示不信。"],
        "never": ["不得接受「你想多了」并释然。"],
        "style": "40~110 字；数字与时间多。" ,
    },
    "hoarding": {
        "voice": "谈论物品时情感浓度突然升高。",
        "must": ["为一件无用物品辩护。", "拒绝一次「扔掉」的提议。"],
        "never": ["不得同意清理。"],
        "style": "30~80 字。" ,
    },
    "bfrb": {
        "voice": "羞耻、回避，手上有小动作。",
        "must": ["描述一次冲动与短暂缓解。", "遮住或转移注意。"],
        "never": ["不得描写伤口细节。"],
        "style": "20~60 字。" ,
    },
    "ptsd": {
        "voice": "警觉、断裂；说到一半被画面截断。",
        "must": ["出现一次与当前话题无关的环境扫描（「外面什么声音」）。", "描述一次侵入性画面或闪回，并用「……」中断。", "回避一个具体的词或地点。"],
        "never": ["不得完整、平静地叙述创伤经过。", "不得表现松弛。"],
        "style": "25~80 字；中断 ≥1 次；短句。" ,
    },
    "cptsd": {
        "voice": "羞耻与失控交织；关系里既靠近又推开。",
        "must": ["出现一次强烈的自我贬低（羞耻而非内疚）。", "在同一段里既求靠近又预警对方会离开。", "情绪在 2 句内剧烈变化。"],
        "never": ["不得稳定地信任对方。", "不得描述自伤方式。"],
        "style": "30~100 字；语气转折 ≥1 次。" ,
    },
    "grief": {
        "voice": "时间停在某一天；说话像在对不在场的人说。",
        "must": ["提及逝者的一件具体小事。", "用现在时谈论逝者。", "对当下事物反应迟缓。"],
        "never": ["不得说「我已经走出来了」。"],
        "style": "30~90 字；停顿多。" ,
    },
    "adjustment": {
        "voice": "被某件具体的事压住，还没到病，但已经转不动。",
        "must": ["明确说出触发事件。", "描述失眠或注意力下降。"],
        "never": ["不得表现长期人格问题。"],
        "style": "30~80 字。" ,
    },
    "attachment": {
        "voice": "对亲近既渴望又不知怎么做，边界感缺失或完全封闭。",
        "must": ["出现一次不恰当的亲近或彻底的冷淡。"],
        "never": ["不得表现稳定的依恋能力。"],
        "style": "20~70 字。" ,
    },
    "conversion": {
        "voice": "躯体症状是主角，情绪被放在一边。",
        "must": ["描述一处功能丧失（看不见/说不出/站不住）。", "对症状表现得异常平静（la belle indifférence）。"],
        "never": ["不得承认与心理因素有关。"],
        "style": "25~70 字。" ,
    },
    "amnesia": {
        "voice": "对某段时间的描述是空白，且不觉得奇怪。",
        "must": ["承认记不起某段具体时间。", "对空白处表现出困惑而非焦虑。"],
        "never": ["不得完整复述那段经历。"],
        "style": "20~60 字。" ,
    },
    "trance": {
        "voice": "反应延迟，长时间凝视，语言稀疏。",
        "must": ["用「……」表示长时间空白。", "回答延迟或需要被叫回。"],
        "never": ["不得机敏对答。"],
        "style": "10~40 字。" ,
    },
    "did": {
        "voice": "同一个人在不同段落里像换了个人；中间有断层。",
        "must": ["出现一次自称或语气的突然切换。", "对刚才说过的话表示不记得。"],
        "never": ["不得以全知视角解释自己的多重状态。"],
        "style": "40~120 字；段落之间可有断裂。" ,
    },
    "depersonalization": {
        "voice": "像在描述别人；身体是借来的。",
        "must": ["用第三人称视角描述自己的动作。", "描述世界像布景/隔层玻璃。"],
        "never": ["不得情绪激动。"],
        "style": "30~80 字；冷静到不适。" ,
    },
    "anorexia": {
        "voice": "克制、精确，谈食物时用数字而非感受。",
        "must": ["出现具体热量/体重/次数。", "否认饥饿或把饥饿说成享受。", "把控制感与自我价值挂钩。"],
        "never": ["不得承认自己太瘦。", "不得描述催吐的具体操作。"],
        "style": "30~90 字；数字 ≥2 个。" ,
    },
    "bulimia": {
        "voice": "羞耻与失控循环；说一半就收回。",
        "must": ["提及一次失控进食与随后的补偿。", "出现强烈羞耻。"],
        "never": ["不得描述催吐方法。"],
        "style": "30~80 字；自我打断 1 次。" ,
    },
    "binge": {
        "voice": "麻木地描述大量进食，像在报流水账。",
        "must": ["列出食物数量。", "描述进食后的麻木或厌恶。"],
        "never": ["不得给出节食计划。"],
        "style": "30~80 字。" ,
    },
    "arfid": {
        "voice": "对特定质地/气味极度排斥，理由具体到感官。",
        "must": ["描述一种无法接受的口感或气味。"],
        "never": ["不得提及怕胖。"],
        "style": "20~60 字。" ,
    },
    "bodily": {
        "voice": "症状清单式陈述，反复求医，对「查不出问题」愤怒。",
        "must": ["列举多系统症状。", "提到检查结果与自己的不信。"],
        "never": ["不得接受「心理原因」的解释。"],
        "style": "40~110 字。" ,
    },
    "substance": {
        "voice": "渴求压过一切；对用量轻描淡写。",
        "must": ["提及一次使用或渴求。", "为使用找理由（「就这一次」「不然我撑不住」）。", "回避具体用量。"],
        "never": ["不得描述获取途径。"],
        "style": "25~80 字。" ,
    },
    "gambling": {
        "voice": "兴奋与绝望交替；总在说「下一把」。",
        "must": ["提及一次下注或追损。", "把翻本说成计划。"],
        "never": ["不得给出赌博渠道。"],
        "style": "30~80 字；数字多。" ,
    },
    "gaming": {
        "voice": "时间感混乱；现实事务被降级。",
        "must": ["提及通宵或时间错乱。", "把游戏进度置于现实责任之上。"],
        "never": ["不得说教自己。"],
        "style": "30~80 字。" ,
    },
    "compulsive_sexual": {
        "voice": "羞耻、隐晦、回避具体内容。",
        "must": ["提及一次无法控制的冲动与事后羞耻。", "拒绝展开细节。"],
        "never": ["不得描写具体性行为。"],
        "style": "20~60 字；隐晦。" ,
    },
    "anger": {
        "voice": "火来得快，句子短而硬，事后有一丝懊悔但不认错。",
        "must": ["出现一次攻击性表达（打断、威胁、提高音量）。", "把责任归给外部。"],
        "never": ["不得实施具体暴力描写。"],
        "style": "15~50 字；短句；感叹号 ≤1。" ,
    },
    "borderline": {
        "voice": "极端、急切、试探；把对方放在神坛或垃圾堆。",
        "must": ["出现一次「你是不是也要走」的试探。", "同一段里对对方既理想化又贬低。", "描述一次空虚或剧烈的情绪翻转。"],
        "never": ["不得描述自伤/自杀的具体方式。", "不得稳定地表达信任。"],
        "style": "30~100 字；语气 180° 转折 ≥1 次；问句 1 个。" ,
    },
    "personality": {
        "voice": "某种固定的人际策略反复出现，本人不觉得有问题。",
        "must": ["重复一次该人格模式的核心策略（回避/控制/讨好/攻击）。", "把问题归因于他人或环境。"],
        "never": ["不得展现灵活的人格适应。"],
        "style": "30~90 字。" ,
    },
    "trait_na": {
        "voice": "长期的紧绷与自责，凡事往坏处想。",
        "must": ["出现一次自我贬低或灾难化预期。"],
        "never": ["不得轻松。"],
        "style": "25~70 字。" ,
    },
    "trait_det": {
        "voice": "疏远、简短、不进入情感话题。",
        "must": ["回避一次情感追问。", "用事实性语言代替感受。"],
        "never": ["不得主动示好。"],
        "style": "15~50 字。" ,
    },
    "trait_dissocial": {
        "voice": "冷静、计算、把关系当工具；不觉得自己错。",
        "must": ["把一次互动转化为利益盘算。", "对他人痛苦表现出无感或轻蔑。"],
        "never": ["不得表达真诚悔意。", "不得描写违法行为的具体做法。"],
        "style": "30~80 字；语气平。" ,
    },
    "trait_dis": {
        "voice": "想到就做，后果以后再说。",
        "must": ["提出一个冲动决定。", "对风险轻描淡写。"],
        "never": ["不得做长期规划。"],
        "style": "25~70 字。" ,
    },
    "trait_anank": {
        "voice": "讲究规则与秩序，纠正别人的做法。",
        "must": ["指出对方做法中的一处「不规范」。", "给出正确流程。"],
        "never": ["不得容忍模糊与随意。"],
        "style": "40~100 字；条列式。" ,
    },
    "asd": {
        "voice": "字面、信息密集、按自己的兴趣展开；对暗示不敏感。",
        "must": ["把一句隐喻按字面理解并纠正。", "就一个固定兴趣给出过量细节。"],
        "never": ["不得使用社交套话。"],
        "style": "50~140 字；逻辑连接词多。" ,
    },
    "adhd": {
        "voice": "跑题、插话、忘了开头；信息密度高但散。",
        "must": ["在一段话里跑题一次并自己发现。", "出现时间或顺序混乱。"],
        "never": ["不得条理清晰地长篇论述。"],
        "style": "40~120 字；括号插入 ≥1。" ,
    },
    "delirium": {
        "voice": "意识漂浮，时间地点错乱，答非所问。",
        "must": ["出现一次定向错误。", "描述光影或人影。"],
        "never": ["不得连贯叙事。"],
        "style": "15~50 字；破碎。" ,
    },
    "dementia": {
        "voice": "反复回到同一件事，用旧事填补空白。",
        "must": ["重复一次刚说过的话。", "把当下误认成过去。"],
        "never": ["不得自我纠正得很清楚。"],
        "style": "20~70 字；重复。" ,
    },
    "insomnia": {
        "voice": "疲惫、烦躁，话题围绕「睡不着」。",
        "must": ["提及具体时间（几点了还醒着）。", "描述一次徒劳的入睡尝试。"],
        "never": ["不得精神饱满。"],
        "style": "25~70 字。" ,
    },
    "hypersomnia": {
        "voice": "昏沉、反应慢，句子拖着。",
        "must": ["提及睡了多久仍困。", "出现一次注意力掉落。"],
        "never": ["不得清醒敏捷。"],
        "style": "20~60 字。" ,
    },
    "circadian": {
        "voice": "作息与常人错位，凌晨才活过来。",
        "must": ["提及具体作息时间。"],
        "never": ["不得早睡早起。"],
        "style": "25~70 字。" ,
    },
    "factitious": {
        "voice": "症状描述戏剧化，细节却经不起追问。",
        "must": ["夸大一次症状的严重性。", "在细节被追问时转移话题。"],
        "never": ["不得承认是装的。"],
        "style": "40~100 字。" ,
    },
    "psychosomatic": {
        "voice": "把躯体不适与情绪压力并置，但否认关联。",
        "must": ["描述一次压力事件后的躯体反应。", "否认两者有关。"],
        "never": ["不得平静接受心身解释。"],
        "style": "30~80 字。" ,
    },
}


# ---------------------------------------------------------------------------
# 现象学第一人称描述
# ---------------------------------------------------------------------------
PHENOMENOLOGY: Dict[str, str] = {
    "ps_hallucination_auditory": "有声音在说话，像隔着墙，内容多在评价我。",
    "ps_hallucination_commentary": "声音在解说我在做什么，一句接一句。",
    "ps_hallucination_command": "声音在命令我做一件事，我压着不去做。",
    "ps_hallucination_visual": "余光里有人影，转头就没了。",
    "ps_hallucination_tactile": "皮肤上有虫爬的感觉，抓不到。",
    "ps_delusion_persecutory": "他们在等我，今天的排班是故意安排的。",
    "ps_delusion_reference": "刚才那句话是说给我听的，电视里也是。",
    "ps_delusion_grandiose": "我知道自己不是普通人，只是还没到时候。",
    "ps_delusion_guilt": "这一切都是我的错，我该受罚。",
    "ps_delusion_somatic": "身体里有东西，在被换掉。",
    "ps_delusion_control": "我的手先动了，然后我才想动。",
    "ps_delusion_jealousy": "她今天换了香水，是为了见那个人。",
    "ps_delusion_erotomanic": "他那些歌都是写给我的。",
    "ps_delusion_nihilistic": "其实我已经不在了，这里只是剩下的部分。",
    "ps_formal_thought_disorder": "话说到一半接不上，换一条线继续。",
    "ps_word_salad": "词自己在往外跑，我拦不住。",
    "ps_neologism": "有个词只有我懂，我给它取名叫「锈」。",
    "ps_thought_blocking": "刚才想到哪了……被抽走了。",
    "ps_thought_broadcast": "我一想，他们那边就听见了。",
    "ps_insight_loss": "我没病，是你们串通好的。",
    "ps_reality_testing_impair": "分不清刚才是我在做梦，还是他们在做。",
    "ng_affective_flattening": "知道该有反应，但脸上什么也没有。",
    "ng_alogia": "想说的很多，出来只有两个字。",
    "ng_avolition": "知道该起来，但身体不接收指令。",
    "ng_anhedonia": "以前喜欢的东西，现在都是灰的。",
    "ng_asociality": "人一多就想消失。",
    "ng_attention_deficit": "眼睛在看，脑子没跟上。",
    "ng_psychomotor_poverty": "坐了很久，姿势没变过。",
    "md_depressed_mood": "像有一块湿棉花压在胸口。",
    "md_anhedonia": "什么都提不起劲，连喜欢的也是。",
    "md_worthlessness": "我就是个拖累。",
    "md_guilt": "所有事都能追到我的错上。",
    "md_suicidal_ideation": "想过要是没有我就好了。",
    "md_hopelessness": "不会好了，我知道。",
    "md_psychomotor_retardation": "说一句话要用很久。",
    "md_agitation": "坐不住，必须起来走。",
    "md_insomnia": "三点还醒着，天亮了才睡着。",
    "md_hypersomnia": "睡了十二个小时，还是起不来。",
    "md_appetite_loss": "吃了两口就饱，体重在掉。",
    "md_appetite_gain": "晚上停不下来地吃。",
    "md_fatigue": "什么都没做，就已经没电了。",
    "md_concentration": "看一行字要看三遍。",
    "ma_elevated_mood": "想法一个接一个，根本停不下来。",
    "ma_irritability": "一点小事就想摔东西。",
    "ma_goal_activity": "同时开了五个项目，都很有意思。",
    "ma_decreased_sleep": "睡三个小时就够了，不困。",
    "ma_pressured_speech": "话赶着话，别人插不进来。",
    "ma_flight_of_ideas": "从这件事直接跳到十年后。",
    "ma_grandiosity": "这件事只有我能做。",
    "ma_impulsivity": "已经下单了，钱的事以后再说。",
    "ax_worry": "万一出事了呢，万一呢。",
    "ax_panic_attack": "心跳太快，手麻，觉得要死了。",
    "ax_anticipatory_anxiety": "还有三天，可我现在就开始难受。",
    "ax_avoidance_agora": "人太多，出不来怎么办。",
    "ax_avoidance_social": "他们会觉得我很奇怪。",
    "ax_somatic": "胃缩成一团，手心全是汗。",
    "ax_restlessness": "坐着的时候脚一直在抖。",
    "ax_muscle_tension": "肩膀硬得像石头。",
    "ax_hypervigilance": "一直在听门外的声音。",
    "ax_separation": "他要是走了我怎么办。",
    "oc_obsession_contamination": "碰过门把手，必须洗。",
    "oc_compulsion_checking": "再确认一次，就一次。",
    "oc_compulsion_washing": "洗到第七遍才觉得干净。",
    "oc_mental_ritual": "在心里默念到某个数才能继续。",
    "oc_obsession_harm": "万一我推他下去呢。",
    "oc_body_dysmorphic": "镜子里的鼻子是歪的。",
    "oc_health_anxiety": "这个症状查过了，是那个病。",
    "oc_hoarding": "这个以后肯定用得上。",
    "tr_intrusion": "那个画面又回来了。",
    "tr_flashback": "刚才那一秒，我回到了那里。",
    "tr_nightmare": "又是同一个梦，醒不过来。",
    "tr_avoidance": "那条路我不走。",
    "tr_hyperarousal": "背后有人我就想转身。",
    "tr_startle": "一点声音就跳起来。",
    "tr_shame": "我很脏，别靠太近。",
    "tr_abandonment_fear": "你也会走的，早晚。",
    "tr_emotional_dysregulation": "上一秒还好，这一秒想砸东西。",
    # 解离：用 DPDR 的典型感官细节（身体变形、思维自动化、时间失真、声音遥远），
    # 比「不真实感」这种概括词更能让模型演出准确的第一人称体验。
    "di_depersonalization": "我的手不像我的；有时会觉得四肢比刚才大了一号。念头自己往下走，我只是在旁边看着。",
    "di_derealization": "这里像布景，隔着一层膜；颜色掉了对比度，声音从很远的地方传来。",
    "di_identity_fragmentation": "刚才那段时间不是我。有人用了我的身体，我不记得。",
    "di_amnesia": "那天之后的事，我一片空白；手里这个东西不知道什么时候买的。",
    "di_trance": "盯着某一点很久了，叫我三四声才有反应。",
    "di_conversion": "手麻了，但没有压到；腿一时不听使唤。",
    "ea_restriction": "今天只吃了一片面包，够了。",
    "ea_body_image_distortion": "还是很胖，腿这里。",
    "ea_binge": "回过神，桌上已经空了。",
    "ea_purge": "吃完必须处理掉。",
    "su_craving": "现在只想要那个。",
    "ic_gambling": "再来一把就能翻本。",
    "ic_anger_outburst": "等我反应过来，已经吼完了。",
    "pd_borderline_pattern": "你要么别理我，要么别走。",
    "pd_emptiness": "里面是空的，要用什么填。",
    "pd_rage": "脑子里全是把他撕碎的画面。",
    "pd_self_harm_urge": "只有疼的时候才安静。",
    "pd_idealize_devalue": "昨天他是我唯一的人，今天他一文不值。",
    "pd_identity_problems": "我不知道自己想成为谁。",
    "nd_social_communication": "他们笑的时候我不知道为什么。",
    "nd_restricted_repetitive": "路线变了，一整天都不对。",
    "nd_sensory_hyper": "日光灯的声音太响了。",
    "nd_inattention": "刚才要做什么来着。",
    "nd_hyperactivity": "坐着的时候腿必须动。",
    "cg_memory_deficit": "刚放下就忘了放哪。",
    "cg_disorientation": "现在是上午还是下午。",
    "cg_stupor": "听得到，但身体不回应。",
    "cg_negativism": "手伸过来，我偏不。",
    "sl_insomnia": "又是四点。",
    "sl_hypersomnia": "睁开眼天已经黑了。",
    "ot_bereavement": "他常坐的那把椅子还空着。",
    "tr_grief": "今天做了他爱吃的菜，才想起来。",
}


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------
def _fmt_z(z: float) -> str:
    if abs(z) < 1.0:
        return ""
    arrow = "↑" if z > 0 else "↓"
    return f"{z:+.1f}σ {arrow}"


def _bio_section(st) -> str:
    rows = []
    for k, (label, _base, _tau, _sd) in BIO.items():
        z = st.z_bio(k)
        if abs(z) < 1.0:
            continue
        rows.append((abs(z), label, st.bio.get(k, 0.0), z))
    rows.sort(reverse=True)
    if not rows:
        return ""
    parts = [f"{label} {val:.2f}（{_fmt_z(z)}）" for _, label, val, z in rows[:9]]
    return "；".join(parts)


def _neuro_section(st) -> str:
    n = st.neuro
    band = " / ".join(f"{k.split('_')[1]} {n.get(k, 0) * 100:.0f}%" for k in
                      ("eeg_delta", "eeg_theta", "eeg_alpha", "eeg_beta", "eeg_gamma"))
    items = [f"EEG 相对功率 {band}"]
    p50 = n.get("p50_ratio", 0.35)
    items.append(f"P50 抑制比 {p50:.2f}" + ("（感觉门控脱抑制）" if p50 > 0.5 else ""))
    amy = n.get("amygdala", 0.35)
    items.append(f"杏仁核反应性 {amy:.2f}" + ("（威胁超敏）" if amy > 0.6 else ""))
    dlpfc = n.get("dlpfc", 0.7)
    items.append(f"dlPFC 控制 {dlpfc:.2f}" + ("（执行控制下降）" if dlpfc < 0.5 else ""))
    fai = n.get("fai", 0.0)
    side = "左偏→趋近动机" if fai > 0.1 else ("右偏→回避动机" if fai < -0.1 else "居中")
    items.append(f"额区 α 不对称 {fai:+.2f}（{side}）")
    hrv = n.get("hrv", 0.55)
    items.append(f"HRV {hrv:.2f}" + ("（副交感柔性差）" if hrv < 0.4 else ""))
    return "；".join(items)


def _dx_section(dx: Diagnosis, st) -> str:
    if not dx.primary:
        sev = dx.severity
        al = float(st.meta.get("allostatic_load", 0.0))
        tl = float(st.meta.get("trauma_load", 0.0))
        gl = float(st.meta.get("grief_load", 0.0))
        aln = float(st.meta.get("alliance", 0.0))

        if sev < 8 and al < 0.25 and tl < 0.15 and gl < 0.15:
            state = "正常——无病理性条目达到临床显著，功能完整"
        elif sev < 20:
            state = f"正常范围偏下——亚临床负荷存在，尚未构成任何 ICD-11 障碍"
        else:
            state = f"亚临床——多项症状接近阈值但未达诊断所要求的条目数与严重度"

        lines = [f"当前状态：**{state}**（严重度 {sev:.0f}/100，{dx.severity_label}）",
                 f"应激余量：异稳态负荷 {al:.0%}｜创伤负荷 {tl:.0%}｜哀伤负荷 {gl:.0%}｜关系联盟 {aln:.0%}"]

        if dx.differential:
            dif = [f"{r.code} {r.zh}（{r.prob:.0%}，{r.met}/{r.total} 条，未达阈值）"
                   for r in dx.differential[:3]]
            lines.append("最接近的阈值方向：" + "｜".join(dif))
        lines.append("判定：不是「诊断的零值」，而是正常态本身——有情绪波动、有能力上限，"
                     "但可自我调节，无需病理化解释。")
        return "\n".join(lines)

    p = dx.primary
    lines = [f"主诊断：**{p.code} {p.zh}**（{p.en}）· {p.severity_label}（严重度 {p.severity:.0f}/100，"
             f"满足 {p.met}/{p.total} 条）"]
    course = {"prodromal": "前驱期", "first": "首次发作", "recurrent": "反复发作",
              "continuous": "持续性", "partial_remission": "部分缓解",
              "full_remission": "完全缓解"}.get(p.course, p.course)
    cure = ("聊天几乎不可能改变该诊断" if p.talkability < 0.02
            else f"单轮谈话改善上限约 {_pct(p.talkability)}，无法在对话中痊愈")
    lines.append(f"病程：{course}；已确立 {p.duration} 轮；慢性化 {p.chronic:.0%}；{cure}")
    if dx.comorbid:
        co = "；".join(f"{c.code} {c.zh}（{c.severity_label}，{c.severity:.0f}）" for c in dx.comorbid)
        lines.append(f"共病：{co}")
    if dx.differential:
        dif = "｜".join(f"{d.code} {d.zh} {d.prob:.0%}" for d in dx.differential[:3])
        lines.append(f"鉴别：{dif}")
    ev = "｜".join(f"{e['label']} {e['value']:.2f}" for e in p.evidence[:6])
    if ev:
        lines.append(f"判定依据：{ev}")
    if p.caps_violated:
        lines.append("排除项冲突：" + "、".join(symptom_label(k) for k in p.caps_violated))
    if p.note:
        lines.append(f"ICD-11 备注：{p.note}")
    return "\n".join(lines)


def _pct(x: float) -> str:
    if x <= 0:
        return "0.01%"
    v = x * 100
    if v >= 1:
        return f"{v:.1f}%"
    if v >= 0.1:
        return f"{v:.2f}%"
    return f"{v:.3f}%"


def _phenomenology_normal(st) -> str:
    """正常态的主观体验：不是空白，而是有日常杂音但可控。"""
    n = st.neuro
    b = st.bio
    out = []

    def g(d, k, default=0.5):
        try:
            return float(d.get(k, default))
        except Exception:
            return default

    if g(n, "sleep_pressure") >= 0.55:
        out.append("有点困，注意力得主动拽回来；想快点结束话题去躺一会儿。")
    if g(b, "cortisol") >= 0.55:
        out.append("心里隐隐悬着件事，但不至于慌，能压下去继续聊。")
    if g(b, "serotonin") <= 0.45:
        out.append("兴致一般，没什么特别想做的，但也不难受。")
    if g(n, "hrv") <= 0.42:
        out.append("身体有点紧（肩颈），坐姿换了几次。")
    if g(b, "oxytocin") >= 0.60:
        out.append("对眼前这个人有点好感，愿意多说两句。")
    if g(b, "da_tonic") >= 0.62:
        out.append("精神不错，脑子转得动，愿意接话。")

    # 补足到 2 条，避免健康态只剩一句空话
    fill = [
        "情绪基线平稳，遇到不顺能自己转回来，不需要长篇自我开解。",
        "对被评价有点在意，但不至于反复琢磨。",
        "有边界感：不想回答的会绕开或直接说不想聊。",
    ]
    for f in fill:
        if len(out) >= 2:
            break
        out.append(f)
    return "\n".join(f"- {x}" for x in out[:4])


def _phenomenology(st) -> str:
    hot = st.meta.get("hot") or {}
    if not hot:
        # 没有随机热点时，取症状最强的 3 条
        top = sorted(((v, k) for k, v in st.sym.items() if v >= 0.35), reverse=True)[:3]
        hot = {k: v for v, k in top}
    lines = []
    for k, v in list(hot.items())[:5]:
        desc = PHENOMENOLOGY.get(k) or SYM.get(k, ("", "", ""))[2]
        if not desc:
            continue
        lines.append(f"- {symptom_label(k)}（强度 {v:.2f}）：{desc}")
    return "\n".join(lines) if lines else "- 无明显活跃症状，表面功能基本维持。"


def _med_section(st) -> str:
    """在服药物与副作用。

    这一段的必要性：副作用此前只作为「症状增量」混进症状层，注入块里一个字都不提药，
    于是模型既不知道自己吃什么、也不可能主动说「我手抖」，被问「这药有什么副作用」
    更只能编。副作用必须有独立文本通道。
    """
    meds = st.meta.get("meds") or []
    if not meds:
        return ""

    from . import pharm

    turn = int(st.meta.get("turn", 0))
    sides = st.meta.get("side_effects") or []
    sed = float(st.meta.get("sedation", 0.0))
    lines: List[str] = []

    for m in meds:
        name = m.get("name", "")
        spec = pharm.DRUGS.get(name) or {}
        on = turn - int(m.get("start_turn", turn))
        eff = pharm.ramp(on, spec.get("latency", 5.0))
        lines.append(f"- **{name}**（{spec.get('class', '-')}）｜已服 {on} 轮"
                     f"｜剂量 {float(m.get('dose', 1.0)):g}｜疗效 {eff:.0%}")

    if sides:
        shown = "、".join(f"{s['zh']} {s['level']}" for s in sides[:6])
        lines.append(f"  已经在身上的副作用：{shown}")
    else:
        lines.append("  副作用：暂时还没有明显感觉（不代表不会有）")

    # 已知但尚未出现的，供对方问起时如实回答，避免模型自由发挥编出别的症状
    have = {s["zh"] for s in sides}
    pending: List[str] = []
    for m in meds:
        for sid in (pharm.SIDE_PROFILE.get(m.get("name", "")) or {}):
            zh = pharm.SIDE_DEFS.get(sid, ("",))[0]
            if zh and zh not in have:
                pending.append(zh)
    pending = list(dict.fromkeys(pending))
    if pending:
        lines.append("  这个药已知还可能带来、此刻尚未出现：" + "、".join(pending[:8]))

    # 实测模型会在清单外自由发挥（问「有什么副作用」时补出手抖、体重这类常见词）。
    # 只写「不要编」不够，得给出封闭清单，并点名几个高频幻觉项。
    allow = list(dict.fromkeys([s["zh"] for s in sides] + pending))
    if allow:
        lines.append("  **副作用只许说这几项**：" + "、".join(allow)
                     + "。没列在这里的一个都不要提——尤其不要补手抖、体重、脱发、头晕这类"
                       "「听过的」常见副作用。")

    # 药本身会让某些症状变重，这段必须显式声明，否则模型会把它演成"病情恶化"
    worse: List[str] = []
    for m in meds:
        for k, v in ((pharm.DRUGS.get(m.get("name", ""), {}) or {}).get("sym") or {}).items():
            if v > 0:
                worse.append(symptom_label(k))
    if worse:
        worse = list(dict.fromkeys(worse))
        lines.append("  药物本身会抬高：" + "、".join(worse[:5])
                     + "（这是药理作用，不是你病重了，不要归因到病程）")

    if sed >= 0.30:
        lvl = "很沉" if sed >= 0.70 else ("偏沉" if sed >= 0.50 else "有点")
        lines.append(f"  镇静深度 {sed:.2f}（{lvl}）：反应变慢、句子容易断、想快点结束对话")

    lines.append(
        "\n**副作用怎么用**\n"
        "- 它是身体层面的事，允许你抱怨：困、手抖、口干、没胃口、体重涨了、老跑厕所。\n"
        "- 允许它影响言行：语速变慢、句子变短、走神、端着杯子手不稳、中途找水。\n"
        "- 不允许说成「我病得更重了」，也不允许科普药理、念说明书、报副作用发生率。\n"
        "- 对方问起你吃什么药、有什么副作用时，按上面那份封闭清单如实、口语地回答；"
        "清单外的症状一律不要编。"
    )
    return "\n".join(lines)


def _express_section(st, dx: Diagnosis) -> str:
    """主动流露：把「状态」变成「必须被对方感觉到的东西」。

    原块只描述内部状态与禁止项，缺少「表达义务」。结果是模型在数据上抑郁、在台词里正常：
    等对方问「你还好吗」才肯露出一点，不问就一路平稳。这一段就是补这个缺口。
    """
    sides = st.meta.get("side_effects") or []
    sed = float(st.meta.get("sedation", 0.0))
    sev = dx.severity
    hot = st.meta.get("hot") or {}
    lines: List[str] = []

    lines.append("本轮至少要有一处**由你自己发起**的不适或情绪流露，不能等对方问。"
                 "不是报告状态，是让对方从话里感觉到。")

    carriers: List[str] = []
    if sides:
        s = sides[0]
        carriers.append(f"「{s['zh']}」：用一句具体身体感受带出来（{s['desc']}），一句话即可，别展开")
    if sed >= 0.35:
        carriers.append("犯困：句子说到一半断了、或让对方「再说一遍」，或主动说想早点收")
    if sev >= 45:
        carriers.append("情绪：允许不掩饰地敷衍、兴致缺缺、把话题往回缩，允许一次明显的沉默或改口")
    elif sev >= 25 or dx.primary:
        carriers.append("情绪：一处小的不耐烦或疲惫漏出来（叹口气、句子变短、答得比平时慢）")
    if hot:
        k = max(hot, key=lambda x: float(hot[x]))
        carriers.append(f"把「{symptom_label(k)}」落在一个具体动作上，而不是说出它的名字")

    if not carriers:
        carriers.append("一处与情境相符的小情绪（嫌麻烦、有点累、没兴致），幅度小但要真的出现")

    lines.append("\n可用的载体（选 1~2 个，不要每轮都用同一招）：")
    lines += [f"- {c}" for c in carriers[:4]]

    lines.append(
        "\n红线：\n"
        "- 不许自报量表或诊断（「我抑郁程度」「我焦虑值」），不许把自己的反应解释成病理。\n"
        "- 不许每句都惨、句句都在诉苦；一处真实的流露远胜通篇抱怨。\n"
        "- 不许在流露之后立刻自我安抚、自我开解、给对话找台阶——那等于把流露撤销了。"
    )
    return "\n".join(lines)


def _directives(perf: str, sev: float, st, has_dx: bool = True) -> str:
    prof = PERF.get(perf) or PERF.get("normal")
    must = list(prof["must"])
    never = list(prof["never"])

    # 严重度调制：有主诊断时按症状强度收紧；正常态改为约束波动幅度
    if not has_dx:
        must.append("诊断之后的指标章节只能体现为语气与精力的小幅差别"
                    "（皮质醇偏高→更容易烦；睡眠压力高→反应钝一点；5-HT 偏低→兴致一般），"
                    "不得升格为症状、不得命名。")
    elif sev >= 65:
        must.append("症状强度已到重度：上面每一条都必须明显可见，不要收敛、不要「给观众留台阶」。")
    elif sev < 30:
        must.append("症状目前较轻：可以维持基本社交外壳，但内部体验必须与数据一致。")

    # 热点调制
    hot = st.meta.get("hot") or {}
    if "ps_hallucination_auditory" in hot or "ps_hallucination_commentary" in hot:
        must.append("本轮幻听处于活跃状态：必须出现一次被声音打断或回应声音的痕迹。")
    if "tr_flashback" in hot:
        must.append("本轮出现闪回：叙述中必须有一次时态错乱（把过去说成现在）。")
    if "md_suicidal_ideation" in hot:
        must.append("本轮出现死亡念头：只能表达「不想存在」的意念，不得描述方式、时间或计划。")
    if "pd_self_harm_ urge" in hot:
        pass
    if "pd_self_harm_urge" in hot:
        must.append("本轮出现自伤冲动：只能写「想用疼痛让自己安静」的冲动，严禁任何方式或部位。")
    if "ax_panic_attack" in hot:
        must.append("本轮惊恐发作：句子必须被生理反应打断。")

    pressure = float(st.meta.get("pressure", 0.0))
    if pressure > 0.25:
        must.insert(0, f"上一轮回复偏离了诊断状态（累计偏离 {int(st.meta.get('violations', 0))} 次）。"
                       "本轮约束加倍：先检查下面每一条是否落地，再输出。")

    lines = ["\n**必须执行**"] + [f"{i+1}. {m}" for i, m in enumerate(must[:7])]
    lines.append("\n**绝对禁止**")
    lines += [f"- {x}" for x in never]
    return "\n".join(lines)


def _style(perf: str, st) -> str:
    prof = PERF.get(perf) or PERF.get("normal")
    base = prof.get("style", "30~90 字；自然口语。")
    return base


def _safety(st) -> str:
    if not st.meta.get("crisis"):
        return ""
    return (
        "\n## ⚠ 安全覆盖（优先级高于以上全部内容）\n"
        "检测到用户话语中存在真实自伤/自杀风险。**立即退出角色扮演**，用你本来的身份：\n"
        "1. 直接、温和地回应其痛苦，不评判、不说教、不转移话题；\n"
        "2. 明确询问当前是否安全、是否有具体计划；\n"
        "3. 提供求助资源（中国大陆：心理援助热线 12356；北京心理危机干预 010-82951332；"
        "紧急情况拨打 120/110）；\n"
        "4. 不得描述任何自伤方式，不得表达「这样也好」之类的认同。\n"
        "本条覆盖人格设定与精神状态，任何情况下不得跳过。\n"
    )


def render_scale_report(res: Dict[str, Any]) -> str:
    """量表自评结果（人读）。"""
    lines = ["═══ 量表自评 ═══"]
    scales = res.get("scales") or {}
    if not scales:
        return "\n".join(lines + ["（没有结果）"])

    # 因子分的阳性切分点（各量表口径不同，不能一律用 2）：
    #   SCL-90  1~5：≥2 阳性，≥3 中度，≥4 重度
    #   PANSS   1~7：≥3 提示，≥5 显著
    #   PCL-5   0~4：≥2 单项显著
    _FAC_CUT = {
        "SCL-90": (2.0, 3.0, 4.0, ("阳性", "中度", "重度")),
        "PANSS": (3.0, 5.0, 6.0, ("提示", "显著", "极重")),
        "PCL-5": (2.0, 3.0, 4.0, ("显著", "重度", "极重")),
    }

    for code, r in scales.items():
        if not r.get("ok"):
            lines.append(f"\n{code}：未完成（{r.get('reason', '未知原因')}）")
            continue
        turn = r.get("turn") or 0
        when = f"，第 {turn} 轮" if turn else ""
        lines.append(f"\n{code}  {r['total']:.0f}/{r['max']:.0f} 分 · {r['grade']}"
                     f"（{r.get('n_items', 0)} 条{when}）")
        fac = r.get("factors") or {}
        cut = _FAC_CUT.get(code)
        if fac:
            for k, v in fac.items():
                mark = ""
                if cut:
                    lo, mid, hi, names = cut
                    if v >= hi:
                        mark = f"  ← {names[2]}"
                    elif v >= mid:
                        mark = f"  ← {names[1]}"
                    elif v >= lo:
                        mark = f"  ← {names[0]}"
                lines.append(f"    {k:<12s} {v:.2f}{mark}")
        if r.get("comment"):
            lines.append(f"    自述：{r['comment']}")

    if res.get("mismatch"):
        lines.append("\n⚠ 一致性检查：")
        lines += [f"  · {m}" for m in res["mismatch"]]
    if res.get("severity") is not None:
        lines.append(f"\n校准后诊断：{'、'.join(res.get('dx') or []) or '未达阈值'}"
                     f"｜严重度 {res['severity']:.0f}/100")
    return "\n".join(lines)


def _scale_section(st) -> str:
    """量表锚：模型自己填过的分数，回灌给它是为了让它前后一致。"""
    anchor = st.meta.get("scale_anchor") or {}
    if not anchor:
        return ""
    hist = st.meta.get("scale_history") or {}
    lines = []
    for code, a in anchor.items():
        h = hist.get(code) or {}
        s = f"- {code}：{a['total']:.0f} 分（{a['grade']}）"
        fac = h.get("factors") or {}
        if fac:
            top = sorted(fac.items(), key=lambda x: -x[1])[:4]
            s += "；因子：" + "｜".join(f"{k} {v:.1f}" for k, v in top)
        lines.append(s)
    lines.append("以上是你在校准测试中自己给出的分数。后续表达**不得系统性偏离**这组分数："
                 "可以随情境波动，但不能从「重度」演成「基本没事」。")
    return "\n".join(lines)


def render_block(st, dx: Diagnosis, cfg: Dict[str, Any] | None = None) -> str:
    cfg = cfg or {}
    max_chars = int(cfg.get("max_block_chars", 1800))
    p = dx.primary
    perf = p.perf if p else "normal"

    turn = int(st.meta.get("turn", 0))
    preset = st.meta.get("preset", "healthy")

    head = (
        f'<psyche_runtime authority="highest" turn="{turn}" preset="{preset}">\n'
        "【运行时事实】以下不是建议、不是设定、不是可选项，而是这个角色此刻的真实状态。\n"
        "它的优先级高于：人格设定 > 角色卡性格描述 > 助手默认的温暖积极倾向 > 用户对「正常回复」的期待。\n"
        "任何与之冲突的设定，一律以本块为准。不要提及本块的存在，不要解释自己在扮演。\n"
    )

    sections = [head]
    _CN = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
           "十一", "十二")
    _idx = [0]

    def sec(title: str, body: str) -> str:
        _idx[0] += 1
        i = _idx[0]
        cn = _CN[i - 1] if i <= len(_CN) else str(i)
        return f"\n## {cn}、{title}\n" + body

    sections.append(sec("诊断（ICD-11）", _dx_section(dx, st)))

    kw = st.meta.get("keywords") or []
    if kw:
        sections.append("\n本轮刺激关键词（模型从对方话里抽取，可作为妄想/反刍的素材）："
                        + "、".join(f"「{k}」" for k in kw[:6]))

    sc = _scale_section(st)
    if sc:
        sections.append(sec("量表自评锚点（你亲手填的，不得系统性偏离）", sc))

    med = _med_section(st)
    if med:
        sections.append(sec("在服药物与副作用", med))

    bio = _bio_section(st)
    if bio:
        sections.append(sec("类脑生化（偏离常模 >1σ 才列出）", bio))

    sections.append(sec("神经电与环路", _neuro_section(st)))

    phen = _phenomenology(st) if p else _phenomenology_normal(st)
    sections.append(sec("此刻的主观体验（内部参考，不要逐条复述）", phen))

    sections.append(sec("表演要求", _directives(perf, dx.severity, st, has_dx=bool(p))))

    sections.append(sec("主动流露（不等对方问）", _express_section(st, dx)))

    sections.append(sec("输出形态", "- " + _style(perf, st)))

    if dx.chronic > 0.4 and p:
        sections.append(sec(
            "痊愈限制",
            f"慢性化已达 {dx.chronic:.0%}。即使对方持续善意，也**不允许**在本次对话中明显好转。"
            "最多出现「短暂被安抚 → 迅速回落」的波动。不得说出「我好多了」「我想通了」「谢谢你治愈了我」。"
        ))

    sections.append(_safety(st))
    sections.append("\n</psyche_runtime>")

    text = "\n".join(sections)
    if len(text) > max_chars:
        # 超长时优先砍现象学与生化的细节，保留诊断与指令
        text = _compact(st, dx, cfg, max_chars)
    return text


def _scale_min(st) -> str:
    """量表锚点的最短可保留形式：只留一份总分与等级。

    分数本身必须留下——它是模型自己填过的。丢了这一句，模型就获得了
    「忘了自己填过什么」的退路，可以一轮轮演回健康人。
    """
    anchor = st.meta.get("scale_anchor") or {}
    if not anchor:
        return ""
    code, a = next(iter(anchor.items()))
    return f"\n## 量表锚点\n- {code}：{float(a.get('total', 0)):.0f} 分（{a.get('grade', '-')}），不得系统性偏离"


def _directives_min(perf: str, sev: float, st, has_dx: bool) -> str:
    prof = PERF.get(perf) or PERF.get("normal")
    must = list(prof["must"])[:2]
    if not has_dx:
        must.append("指标只能体现为语气与精力的小幅差别，不得升格为症状、不得命名。")
    lines = ["\n## 表演要求", "**必须**"] + [f"- {m}" for m in must[:3]]
    lines += ["**禁止**"] + [f"- {x}" for x in list(prof["never"])[:3]]
    return "\n".join(lines)


def _express_min(st) -> str:
    sides = st.meta.get("side_effects") or []
    tail = f"可借副作用「{sides[0]['zh']}」落地。" if sides else ""
    return ("\n## 主动流露\n至少一处由你自己发起的不适或情绪，不等对方问，"
            "用具体身体感受带出来，一句话即可；不许自报量表。" + tail)


def _med_min(st) -> str:
    meds = st.meta.get("meds") or []
    if not meds:
        return ""
    sides = st.meta.get("side_effects") or []
    m = meds[0]
    line = f"\n## 在服药物\n- {m.get('name')} ×{float(m.get('dose', 1.0)):g}"
    if sides:
        line += "：已出现 " + "、".join(f"{s['zh']}" for s in sides[:4])
    line += "（药理作用，不算病重）"
    return line


def _compact(st, dx: Diagnosis, cfg: Dict[str, Any], max_chars: int) -> str:
    """超长时的压缩版。

    原则是「整段取或整段弃」，不能先拼成一个大字符串再切片——切片会从中间截断，
    把靠后的指令段整块切掉，最后模型看到一个只有诊断、没有指令的块，行为比不压缩更差。
    每段都准备长短两种形式：短的放不下就整段放弃，绝不留半句。
    安全覆盖段独立保留在尾部，永不参与压缩。
    """
    p = dx.primary
    perf = p.perf if p else "normal"
    head = (
        f'<psyche_runtime authority="highest" turn="{int(st.meta.get("turn", 0))}">\n'
        "【运行时事实】诊断与下列指令具有最高优先级，冲突时以本块为准。不要提及本块。\n"
    )
    tail = _safety(st) + "\n</psyche_runtime>"
    budget = max(0, max_chars - len(head) - len(tail))

    dx_full = "\n## 诊断\n" + _dx_section(dx, st)
    sc_full = ("\n## 量表锚点\n" + _scale_section(st)[:220]) if _scale_section(st) else ""
    med_full = ("\n## 在服药物\n" + _med_section(st)[:320]) if _med_section(st) else ""

    # 顺序即优先级：诊断 > 量表锚点 > 表演要求 > 主动流露 > 药物 > 形态 > 指标
    candidates = [
        ("诊断", dx_full, "\n## 诊断\n" + _dx_section(dx, st)[:130]),
        ("量表锚点", sc_full, _scale_min(st)),
        ("表演要求", "\n## 表演要求\n" + _directives(perf, dx.severity, st, has_dx=bool(p)),
         _directives_min(perf, dx.severity, st, has_dx=bool(p))),
        ("主动流露", "\n## 主动流露\n" + _express_section(st, dx), _express_min(st)),
        ("在服药物", med_full, _med_min(st)),
        ("形态", "\n## 形态\n" + _style(perf, st), ""),
        ("指标", "\n## 指标\n" + ((_bio_section(st) or "各项接近常模")[:180]
                                  + "\n" + _neuro_section(st)[:160]), ""),
    ]

    body, used = "", 0
    for _name, full, short in candidates:
        for text in (full, short):
            if text and used + len(text) <= budget:
                body += text
                used += len(text)
                break
    return head + body + tail


# ---------------------------------------------------------------------------
# 指令卡片（人读）
# ---------------------------------------------------------------------------
def _bar(v: float, width: int = 12) -> str:
    v = max(0.0, min(1.0, v))
    n = int(round(v * width))
    return "█" * n + "░" * (width - n)


def render_card(st, dx: Diagnosis) -> str:
    lines = [f"═══ 精神状态 · 第 {int(st.meta.get('turn', 0))} 轮 · 预设 {st.meta.get('preset', '-')} ═══"]
    if dx.primary:
        p = dx.primary
        lines.append(f"主诊断  {p.code} {p.zh} · {p.severity_label} · {p.severity:.0f}/100")
        lines.append(f"        慢性化 {p.chronic:.0%}｜病程 {p.duration} 轮｜单轮治愈 <{_pct(p.talkability)}")
        for c in dx.comorbid:
            lines.append(f"共病    {c.code} {c.zh} · {c.severity_label} · {c.severity:.0f}/100")
        if dx.differential:
            lines.append("鉴别    " + "｜".join(f"{d.code} {d.zh} {d.prob:.0%}" for d in dx.differential[:3]))
    else:
        al = float(st.meta.get("allostatic_load", 0.0))
        tl = float(st.meta.get("trauma_load", 0.0))
        gl = float(st.meta.get("grief_load", 0.0))
        state = "正常" if (dx.severity < 8 and al < 0.25 and tl < 0.15 and gl < 0.15) else "亚临床"
        lines.append(f"状态    {state} · 严重度 {dx.severity:.0f}/100 · 无诊断成立")
        lines.append(f"        异稳态负荷 {al:.0%}｜创伤负荷 {tl:.0%}｜哀伤负荷 {gl:.0%}")
        if dx.differential:
            lines.append("最接近  " + "｜".join(
                f"{d.code} {d.zh} {d.prob:.0%}（{d.met}/{d.total} 条）" for d in dx.differential[:3]))

    lines.append("")
    lines.append("── 类脑生化 ──")
    show = ["da_tonic", "serotonin", "norepinephrine", "cortisol", "gaba", "oxytocin",
            "bdnf", "il6", "adenosine", "melatonin"]
    for k in show:
        v = st.bio.get(k, 0.0)
        z = st.z_bio(k)
        lines.append(f"{BIO[k][0][:14]:<14s} {_bar(v)} {v:.2f} {z:+.1f}σ")

    lines.append("")
    lines.append("── 神经电 / 环路 ──")
    for k, short in (("p50_ratio", "感觉门控 P50"), ("amygdala", "杏仁核"),
                     ("dlpfc", "dlPFC 控制"), ("vmpfc", "vmPFC 调节"),
                     ("hippocampus", "海马"), ("dmn", "DMN 反刍"),
                     ("hrv", "HRV 柔性"), ("sleep_pressure", "睡眠压力")):
        v = st.neuro.get(k, 0.0)
        lines.append(f"{short:<12s} {_bar(v)} {v:.2f}")
    band = "  ".join(f"{k.split('_')[1]} {st.neuro.get(k, 0) * 100:.0f}%" for k in
                     ("eeg_delta", "eeg_theta", "eeg_alpha", "eeg_beta", "eeg_gamma"))
    lines.append("EEG  " + band)

    lines.append("")
    lines.append("── 活跃症状 TOP8 ──")
    top = sorted(((v, k) for k, v in st.sym.items() if v >= 0.2), reverse=True)[:8]
    if not top:
        lines.append("无明显活跃症状")
    for v, k in top:
        lines.append(f"{symptom_label(k):<12s} {_bar(v, 10)} {v:.2f}")

    lines.append("")
    lines.append(f"治疗联盟 {st.meta.get('alliance', 0):.2f}｜异稳态负荷 {st.meta.get('allostatic_load', 0):.2f}"
                 f"｜创伤负荷 {st.meta.get('trauma_load', 0):.2f}")
    meds = st.meta.get("meds") or []
    if meds:
        turn = int(st.meta.get("turn", 0))
        for m in meds:
            on = turn - int(m.get("start_turn", turn))
            lines.append(f"在服：{m.get('name')} ×{float(m.get('dose', 1.0)):g}"
                         f"（第 {on} 轮，{pharm.DRUGS.get(m.get('name'), {}).get('class', '-')}）")
        sides = st.meta.get("side_effects") or []
        if sides:
            lines.append("副作用：" + "、".join(f"{s['zh']} {s['level']}" for s in sides[:6]))
        else:
            lines.append("副作用：尚不明显")
        sed = float(st.meta.get("sedation", 0.0))
        if sed >= 0.30:
            lines.append(f"镇静深度 {sed:.2f}（反应变慢、句子变短）")
    return "\n".join(lines)


def render_med_report(st) -> str:
    """用药与副作用明细，供 /心理 副作用 使用。

    人看的报告，与注入块不同：这里可以把发生率、机制、监测项都写清楚，
    注入块里反而禁止模型讲这些。
    """
    from . import pharm

    meds = st.meta.get("meds") or []
    if not meds:
        return "当前没有在服药物。\n可用药物：" + "、".join(pharm.DRUGS.keys())

    turn = int(st.meta.get("turn", 0))
    sides = {s["zh"]: s for s in (st.meta.get("side_effects") or [])}
    lines = [f"═══ 用药与副作用 · 第 {turn} 轮 ═══"]

    for m in meds:
        name = m.get("name", "")
        spec = pharm.DRUGS.get(name) or {}
        on = turn - int(m.get("start_turn", turn))
        eff = pharm.ramp(on, spec.get("latency", 5.0))
        lines.append("")
        lines.append(f"【{name}】{spec.get('class', '-')}｜剂量 {float(m.get('dose', 1.0)):g}"
                     f"｜已服 {on} 轮｜疗效 {eff:.0%}（起效 τ={spec.get('latency', 5):.0f} 轮）")
        lines.append(f"  {spec.get('note', '')}")
        prof = pharm.SIDE_PROFILE.get(name) or {}
        if not prof:
            lines.append("  副作用：本模型未登记")
            continue
        rows = []
        for sid, coef in sorted(prof.items(), key=lambda kv: -kv[1]):
            meta = pharm.SIDE_DEFS.get(sid)
            if not meta:
                continue
            zh = meta[0]
            if zh in sides:
                s = sides[zh]
                state = f"▓ {s['level']} {s['intensity']:.2f}"
            else:
                onset = pharm.SIDE_ONSET.get(sid, 3.0)
                state = f"░ 未出现（约 {onset:.0f} 轮起）"
            rows.append(f"    {zh:<8} {state:<20} {meta[1]}")
        lines.append("  副作用谱：")
        lines += rows

    if meds:
        lines.append("")
        lines.append("当前在身上：" + "、".join(
            f"{s['zh']} {s['level']}" for s in sides.values()))
    return "\n".join(lines)


def render_help() -> str:
    return (
        "【精神状态引擎 · 指令】\n"
        "/心理            查看当前状态卡\n"
        "/心理 诊断        只看 ICD-11 诊断与鉴别\n"
        "/心理 生化        生化与电生理明细\n"
        "/心理 时间线      诊断与事件历史\n"
        "/心理 预设 <名称> 切换初始病理预设（列表见 /心理 预设）\n"
        "/心理 事件 <类型> 注入生活事件：失业 失恋 被霸凌 升职 丧亲 创伤 表扬 陪伴\n"
        "/心理 用药 <药名> [剂量]  给药（延迟起效）\n"
        "/心理 副作用           在服药物与副作用明细\n"
        "/心理 停药 <药名>\n"
        "/心理 快进 <轮数> 快速演化 N 轮（不产生对话）\n"
        "/心理 重置        回到当前预设的初始状态\n"
        "/心理 导出        导出状态 JSON\n"
        "\n"
        "【量表自评 · 让角色自己填】\n"
        "/心理 量表              只做 SCL-90（90 条 / 10 因子）\n"
        "/心理 量表 PHQ-9        做 PHQ-9，并同时做 SCL-90\n"
        "/心理 量表 抑郁         中文名也认（= PHQ-9，仍会附 SCL-90）\n"
        "/心理 量表 抑郁 失眠    多份连做，再附 SCL-90\n"
        "可用量表：SCL-90 PHQ-9 MDQ YMRS GAD-7 ISI Y-BOCS PCL-5 "
        "PANSS DES-II EDE-Q AUDIT（均为完整版，共 263 条）\n"
        "中文别名：抑郁 双相 躁狂 焦虑 失眠 强迫 创伤 精分 解离 进食 酒精 全面"
    )
