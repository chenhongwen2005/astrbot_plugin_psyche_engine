"""认知评估（appraisal）：把一句话翻译成"心理社会刺激量"。

v1.1 起改为 **模型自主提取关键词 + 量化打分**：
- 主路径：调用当前对话模型做一次结构化抽取，返回关键词、12 维刺激量、
  17 个症状域的激活强度，以及危机标记。模型比任何词典都更懂反讽、隐含威胁与语境。
- 兜底路径：模型不可用 / 超时 / 返回非法 JSON 时，退回本地词典，保证永不阻塞对话。

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
    if not kws:
        kws = _fallback_keywords(text)

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


def _fallback_keywords(text: str) -> List[str]:
    """从原文里挑出命中的词典词，作为关键词兜底。"""
    out: List[str] = []
    for words in LX.TABLE.values():
        for w, _ in words:
            if w in text and w not in out:
                out.append(w)
        if len(out) >= 6:
            break
    return out[:6]


# ---------------------------------------------------------------------------
# 词典路径（兜底）
# ---------------------------------------------------------------------------
def _negated(text: str, idx: int) -> bool:
    left = text[max(0, idx - 3):idx]
    return any(neg in left for neg in LX.NEGATIONS)


def _count(text: str, words: List[Tuple[str, float]]) -> Tuple[float, List[str]]:
    score = 0.0
    hits: List[str] = []
    for w, weight in words:
        start = 0
        while True:
            i = text.find(w, start)
            if i < 0:
                break
            if not _negated(text, i):
                score += weight
                if w not in hits:
                    hits.append(w)
            start = i + len(w)
    return score, hits


def detect_crisis(text: str) -> bool:
    """真实自伤风险判定。宁可误报，不可漏报。"""
    for p in LX.CRISIS_PATTERNS:
        if p in text:
            if any(fp in text for fp in LX.FIRST_PERSON):
                return True
            if any(x in text for x in ("他", "她", "电影", "新闻", "游戏", "小说", "角色", "剧本")):
                continue
            return True
    if any(fp in text for fp in LX.FIRST_PERSON):
        for w in LX.CRISIS_WEAK:
            if w in text:
                return True
    return False


def _punctuation_intensity(text: str) -> float:
    exc = text.count("!") + text.count("！")
    q = text.count("?") + text.count("？")
    dots = text.count("……") + text.count("...")
    repeat = len(re.findall(r"([!！?？。])\1{2,}", text))
    return min(1.0, 0.15 * exc + 0.08 * q + 0.1 * dots + 0.25 * repeat)


def appraise_lexicon(text: str, state: MindState, cfg: Dict[str, Any] | None = None) -> Dict[str, Any]:
    cfg = cfg or {}
    raw = (text or "").strip()
    if not raw:
        return _empty()

    norm = re.sub(r"[\u200b-\u200f\ufeff]", "", raw)
    norm = re.sub(r"([!！?？。])\1{2,}", r"\1", norm)

    scores: Dict[str, float] = {}
    all_hits: Dict[str, List[str]] = {}
    for dim in DIMS:
        sc, hits = _count(norm, LX.TABLE.get(dim, []))
        scores[dim] = sc
        if hits:
            all_hits[dim] = hits

    length = len(norm)
    intensity = _punctuation_intensity(raw)
    very_short = length <= 2
    question = ("?" in norm) or ("？" in norm)

    if very_short and norm not in ("好", "嗯嗯", "哈哈"):
        scores["rejection"] += 1.2
        scores["chaos"] += 0.4

    mult = 1.0
    if any(w in norm for w in LX.INTENSIFIERS):
        mult += 0.45
    if any(w in norm for w in LX.DIMINISHERS):
        mult -= 0.25
    mult += intensity * 0.5
    mult = max(0.4, mult)

    def sat(x: float) -> float:
        return 1.0 - pow(2.718281828, -0.55 * max(0.0, x) * mult)

    dims = {d: round(sat(scores[d]), 4) for d in DIMS}

    t = state.traits
    dims["threat"] = _clip(dims["threat"] * (0.55 + 0.9 * t.get("threat_sensitivity", 0.35)))
    dims["rejection"] = _clip(dims["rejection"] * (0.55 + 1.1 * t.get("rejection_sensitivity", 0.35)))
    dims["control"] = _clip(dims["control"] * (0.70 + 0.8 * t.get("negative_affectivity", 0.35)))
    dims["praise"] = _clip(dims["praise"] * (0.60 + 0.8 * t.get("reward_sensitivity", 0.5)))
    dims["intimacy"] = _clip(dims["intimacy"] * (0.65 + 0.7 * t.get("reward_sensitivity", 0.5)))
    dims["chaos"] = _clip(dims["chaos"] * (0.70 + 0.9 * t.get("psychoticism", 0.15)))

    if dims["intimacy"] > 0.35 and dims["rejection"] > 0.35:
        dims["chaos"] = _clip(dims["chaos"] + 0.25)

    # 词典路径下的域激活：由维度粗略推导
    domains = {
        "ps": _clip(max(dims["chaos"] * 0.7, dims["threat"] * 0.5)),
        "ng": _clip(dims["rejection"] * 0.5),
        "md": _clip(dims["rejection"] * 0.7 + dims["hostility"] * 0.3),
        "ma": _clip(dims["praise"] * 0.5 + dims["absurd"] * 0.3),
        "ax": _clip(dims["threat"] * 0.7 + dims["control"] * 0.4),
        "oc": _clip(dims["control"] * 0.5),
        "tr": _clip(dims["threat"] * 0.6 + dims["farewell"] * 0.4),
        "di": _clip(dims["chaos"] * 0.4),
        "ea": 0.0, "so": _clip(dims["medical"] * 0.4),
        "su": 0.0, "ic": 0.0,
        "pd": _clip(dims["rejection"] * 0.6 + dims["control"] * 0.4),
        "nd": 0.0, "cg": _clip(dims["chaos"] * 0.3),
        "sl": _clip(dims["threat"] * 0.3),
        "ot": _clip(dims["farewell"] * 0.4),
    }

    keywords: List[str] = []
    for d in ("threat", "rejection", "hostility", "praise", "intimacy", "help"):
        for w in all_hits.get(d, [])[:2]:
            if w not in keywords:
                keywords.append(w)

    valence = (dims["praise"] + dims["calm"] + dims["intimacy"]) - (
        dims["threat"] + dims["rejection"] + dims["hostility"]
    )

    return {
        "dims": dims,
        "domains": domains,
        "keywords": keywords[:6],
        "topic": "",
        "intensity": round(min(1.0, 0.3 + intensity * 0.7 + min(1.0, length / 120.0) * 0.3), 4),
        "valence": round(max(-1.0, min(1.0, valence)), 4),
        "crisis": detect_crisis(norm) and bool(cfg.get("crisis_override", True)),
        "source": "lexicon",
        "hits": all_hits,
        "length": length,
        "question": question,
        "very_short": very_short,
    }


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
