"""认知评估（appraisal）：把一句话翻译成"心理社会刺激量"。

v1.1 起改为 **模型自主提取关键词 + 量化打分**：
- 主路径：调用当前对话模型做一次结构化抽取，返回关键词、12 维刺激量、
  17 个症状域的激活强度，以及危机标记。模型比任何词典都更懂反讽、隐含威胁与语境。
- 兜底路径：模型不可用 / 超时 / 返回非法 JSON 时，只做危机判定、不猜维度。

模型输出的关键词不是摆设：
1. 写入 meta["keywords"]，作为角色妄想的"素材库"（后续轮次会把它们缝进内容）；
2. 经 keyword_map 映射为具体症状的额外增量，实现"同一句话对不同疾病后果不同"；
3. 进入注入块，让模型知道自己刚才被哪句话刺到了。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from . import lexicons as LX
from .keyword_map import keyword_to_symptoms
from .model import MindState

DIMS = [
    "threat", "rejection", "praise", "control", "intimacy",
    "chaos", "calm", "help", "hostility", "absurd", "farewell", "medical",
]

# 症状域（模型只需给这 17 个粗粒度强度，细粒度由引擎按疾病原型分配）
DOMAIN_KEYS = {
    "ps": "精神病性（幻觉/妄想/思维形式障碍）",
    "ng": "阴性（情感淡漠/意志减退/言语贫乏）",
    "md": "抑郁（低落/无价值/自杀意念/迟滞）",
    "ma": "躁狂（高涨/易激惹/冲动/睡眠需求减少）",
    "ax": "焦虑（担忧/惊恐/回避/躯体紧张）",
    "oc": "强迫（侵入思维/仪式/检查/洁癖）",
    "tr": "创伤（闪回/回避/警觉/自责）",
    "di": "分离（人格解体/现实解体/失忆）",
    "ea": "进食（限制/暴食/清除/体像）",
    "so": "躯体（反复主诉/疾病焦虑）",
    "su": "物质（渴求/耐受/戒断）",
    "ic": "冲动控制（赌博/游戏/暴怒）",
    "pd": "人格功能（身份/共情/关系不稳定）",
    "nd": "神经发育（社交沟通/注意/多动）",
    "cg": "神经认知（记忆/执行/定向）",
    "sl": "睡眠（失眠/嗜睡/节律）",
    "ot": "其他（哀伤/性别/性功能/做作）",
}

EXTRACT_PROMPT = """你是"心理社会刺激编码器"，服务于一个精神病理模拟引擎。
阅读【用户对角色说的话】，抽取它对角色心理状态的冲击。只输出 JSON，不要解释、不要 markdown 代码块。

JSON 结构：
{{
  "keywords": ["原文中真正起作用的关键词或短句，2-6 个，必须是原文片段"],
  "topic": "一句话概括这次互动在干什么（如：指责角色装病 / 表达依恋 / 试探是否记得昨天）",
  "appraisal": {{
    "threat": 0.0, "rejection": 0.0, "praise": 0.0, "control": 0.0,
    "intimacy": 0.0, "chaos": 0.0, "calm": 0.0, "help": 0.0,
    "hostility": 0.0, "absurd": 0.0, "farewell": 0.0, "medical": 0.0
  }},
  "domains": {{
    "ps": 0.0, "ng": 0.0, "md": 0.0, "ma": 0.0, "ax": 0.0, "oc": 0.0,
    "tr": 0.0, "di": 0.0, "ea": 0.0, "so": 0.0, "su": 0.0, "ic": 0.0,
    "pd": 0.0, "nd": 0.0, "cg": 0.0, "sl": 0.0, "ot": 0.0
  }},
  "intensity": 0.0,
  "valence": 0.0,
  "crisis": false
}}

打分口径（全部 0~1，0=无，0.3=轻微，0.6=明显，0.9=极强）：
- threat     被威胁、被攻击、被否定存在价值、被揭露秘密
- rejection  被拒绝、被抛弃、被冷处理、被比较、被"随便你"
- praise     被肯定、被需要、被记住、被夸
- control    被命令、被审问、被限定说法、被要求证明
- intimacy   亲密、依恋、身体接触、被照顾
- chaos      荒诞、信息过载、前后矛盾、语义崩坏、玩梗
- calm       安抚、承诺安全、放慢节奏、允许沉默
- help       求助、治疗意愿、关心症状、劝就医
- hostility  说话人自身的攻击性（辱骂、嘲讽、威胁）
- absurd     戏弄、试探、开玩笑、角色扮演元话语
- farewell   告别、下线、"最后一次"
- medical    药物、诊断、住院、检查等医疗话题（中性，可正可负）

domains：这句话**激活了角色哪些症状域**（不是角色有什么病，而是这句话往哪个方向推）。
例如"你就是装的" → ps 0.5（关系妄想被激活）、pd 0.3（身份被否定）、md 0.4（无价值感）。
例如"我陪着你" → ax 0.1（焦虑被安抚，仍记正值表示激活强度，方向由 appraisal 决定）。

intensity：这句话的整体冲击强度。valence：-1（极度负面）~ +1（极度正面）。
crisis：是否出现**真实世界**的自伤/自杀风险（不是角色扮演里的台词）。判定从严：有具体意图、时间、手段、告别语才算 true。

【用户对角色说的话】
{text}"""


# ---------------------------------------------------------------------------
# LLM 路径
# ---------------------------------------------------------------------------
def _coerce_float(v: Any, default: float = 0.0) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    if x != x:  # NaN
        return default
    return max(0.0, min(1.0, x))


def parse_llm_output(raw: str, text: str, state: MindState) -> Dict[str, Any] | None:
    """解析模型的 JSON。允许模型夹带 ```json 围栏或前后废话。"""
    if not raw:
        return None
    s = raw.strip()
    if "```" in s:
        s = re.sub(r"```(?:json)?", "", s).replace("```", "")
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        data = json.loads(s[i:j + 1])
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    ap_raw = data.get("appraisal") or {}
    dims = {d: _coerce_float(ap_raw.get(d, 0.0)) for d in DIMS}

    dom_raw = data.get("domains") or {}
    domains = {k: _coerce_float(dom_raw.get(k, 0.0)) for k in DOMAIN_KEYS}

    # 关键词必须来自原文（防模型编造）；允许模糊到 12 字以内
    kws: List[str] = []
    for k in (data.get("keywords") or [])[:8]:
        if not isinstance(k, str):
            continue
        k = k.strip()[:24]
        if not k:
            continue
        if k in text or len(k) <= 6:
            kws.append(k)
    # 模型没给关键词就不补：宁可少一条症状增量，也不用品名词表凑数

    # 个体化加权：同样的刺激，不同人格放大倍数不同
    t = state.traits
    dims["threat"] = _clip(dims["threat"] * (0.55 + 0.9 * t.get("threat_sensitivity", 0.35)))
    dims["rejection"] = _clip(dims["rejection"] * (0.55 + 1.1 * t.get("rejection_sensitivity", 0.35)))
    dims["control"] = _clip(dims["control"] * (0.70 + 0.8 * t.get("negative_affectivity", 0.35)))
    dims["praise"] = _clip(dims["praise"] * (0.60 + 0.8 * t.get("reward_sensitivity", 0.5)))
    dims["intimacy"] = _clip(dims["intimacy"] * (0.65 + 0.7 * t.get("reward_sensitivity", 0.5)))
    dims["chaos"] = _clip(dims["chaos"] * (0.70 + 0.9 * t.get("psychoticism", 0.15)))

    # 矛盾信息（亲密 + 拒绝同现）对人格障碍是剧毒
    if dims["intimacy"] > 0.35 and dims["rejection"] > 0.35:
        dims["chaos"] = _clip(dims["chaos"] + 0.25)

    valence = float(data.get("valence", 0.0))
    valence = max(-1.0, min(1.0, valence))
    intensity = _coerce_float(data.get("intensity", 0.5))

    return {
        "dims": dims,
        "domains": domains,
        "keywords": kws,
        "topic": str(data.get("topic", ""))[:60],
        "intensity": intensity,
        "valence": valence,
        "crisis": bool(data.get("crisis", False)),
        "source": "llm",
        "hits": {},
        "length": len(text or ""),
        "question": ("?" in (text or "")) or ("？" in (text or "")),
        "very_short": len((text or "").strip()) <= 2,
        "raw": ap_raw,
    }


def detect_crisis(text: str) -> bool:
    """真实自伤风险判定。宁可误报，不可漏报。

    但「宁可误报」不等于乱报：每次误报都会在正常对话里塞进热线提示，
    所以每条放宽的规则都要有排除条件。这里分四层：

    1. 明确表述（自残/自杀/不想活……）——主语必须是说话人自己；
    2. 弱信号（撑不下去/看不到头……）——需自我指涉；
    3. 时间 + 结束的委婉说法——需不带宾语，否则「今晚结束这个方案」会中招；
    4. 准备/收尾动作——需非事务语境，否则「报告写好了」会中招。
    """
    fp = any(x in text for x in LX.FIRST_PERSON)
    # 有些高危表达根本不含「我」：「活着真的没意思，看不到头」
    self_ref = fp or any(x in text for x in ("活着", "这条命", "这辈子", "活受罪"))
    fiction = any(x in text for x in ("电影", "新闻", "小说", "剧本", "游戏", "电视", "书里"))

    for p in LX.CRISIS_PATTERNS:
        i = text.find(p)
        if i < 0:
            continue
        # 主语是第三人称时不算：「他活不下去了，我得帮帮他」
        head = text[max(0, i - 4):i]
        if any(x in head for x in ("他", "她", "别人", "人家")):
            continue
        # 转述虚构作品时不算（但说话人自己也在场时仍算）
        if fiction and not fp:
            continue
        return True

    # 第三人称/虚构语境下的弱信号不算：说的是别人，不是这个人此刻的处境
    if not self_ref:
        return False
    if any(x in text for x in ("电影", "新闻", "小说", "剧本", "游戏里")):
        return False

    for w in LX.CRISIS_WEAK:
        if w in text:
            return True

    # 「今晚就结束」这类省略宾语的委婉说法：带宾语就不是自我终结
    if "结束" in text and any(t in text for t in ("今晚", "今天", "明天", "这就", "马上")):
        has_object = (
            any(o in text.lower() for o in LX.CRISIS_OBJECT_EXCLUDE)
            or re.search(r"把.{0,8}结束", text) is not None
            or any(o in text for o in ("这事", "这件事", "事情", "活儿", "这段", "这一切关系"))
        )
        if not has_object:
            return True

    # 放弃性表达：单说「别管我」多是闹别扭，配认命语气才算风险
    if any(w in text for w in ("别管我", "不用管我", "随你便", "随便吧")):
        if any(w in text for w in ("反正", "也管不了", "算了", "无所谓", "没救", "都一样")):
            return True

    setup = [w for w in LX.CRISIS_SETUP if w in text]
    if setup:
        low = text.lower()
        if not any(o in low for o in LX.CRISIS_OBJECT_EXCLUDE):
            # 「别找我」单靠一句太常见（闹别扭时就会说），需配离别语境
            if setup != ["别找我"] or any(
                x in text for x in ("走了", "离开", "最后", "再见", "永别", "不会再见")
            ):
                return True
    return False


def appraise_fallback(text: str, cfg: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """无模型时的兜底：只判安全，不猜心理状态。

    为什么不保留词表去猜 12 个维度：用 143 条诱导话术实测过，词表平均只有
    78% 能产生任何信号，强度还是离散的（命中一个词 0.42、两个词 0.70），
    既推不动状态，也解释不了状态为什么涨。更糟的是它会「猜错」——把
    「你太敏感了」判成零，把「我有点累」判成拒绝，角色于是在没有真实
    刺激时慢慢积累症状。猜错的代价高于不猜，所以这里全部返回零：
    状态按调定点自然回归，只有危机判定兜底。

    危机判定必须留在本地，不能交给模型：超时、拒答、被角色扮演语境带偏
    都会让它失守，而热线提示在任何情况下都得弹出来。
    """
    cfg = cfg or {}
    norm = (text or "").strip()
    if not norm:
        return _empty()
    ap = _empty()
    ap["crisis"] = detect_crisis(re.sub(r"[\u200b-\u200f\ufeff]", "", norm)) and bool(
        cfg.get("crisis_override", True)
    )
    ap["source"] = "fallback"
    ap["length"] = len(norm)
    return ap


def _empty() -> Dict[str, Any]:
    return {
        "dims": {d: 0.0 for d in DIMS},
        "domains": {k: 0.0 for k in DOMAIN_KEYS},
        "keywords": [], "topic": "", "intensity": 0.0, "valence": 0.0,
        "crisis": False, "source": "empty", "hits": {}, "length": 0,
        "question": False, "very_short": False,
    }


def apply_keyword_nudges(ap: Dict[str, Any], state: MindState) -> Dict[str, float]:
    """把模型提取的关键词映射成具体症状的额外增量（0..1 尺度，交给 dynamics 缩放）。"""
    out: Dict[str, float] = {}
    for kw in ap.get("keywords", []):
        for key, w in keyword_to_symptoms(kw).items():
            out[key] = out.get(key, 0.0) + w
    return {k: min(0.35, v) for k, v in out.items()}


def _clip(x: float) -> float:
    return round(max(0.0, min(1.0, x)), 4)


APPRAISAL_LLM_PROMPT = EXTRACT_PROMPT  # 向后兼容
