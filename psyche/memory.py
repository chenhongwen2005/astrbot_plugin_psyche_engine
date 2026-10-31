"""类脑记忆：情景记忆的编码、巩固、检索与遗忘。

为什么要有这一层
    注入块只描述「此刻」。没有记忆的角色，每轮都像刚认识对方：
    昨天说过的丧事、前天约好的事、上周吵过的架，一律不认。记忆层
    给的是连续性，不是知识库——它只回答一个问题：这句话勾起了哪几件
    事，那些事当时是什么滋味。

四条约束
    1. 只走虚拟时钟。新鲜度、衰减、遗忘都按轮次推进的小时数算。
       按墙钟算的话，一场紧凑的对话里所有记忆都「刚刚发生」。
    2. 存原文，但截断。每条 160 字上限，条数上限默认 240；超限淘汰
       强度最低、最旧的，不静默丢最新的。
    3. 检索要能中中文。没有分词器，用 2-gram 重叠加标签匹配，
       不做语义理解——宁可召回少一点，也不要凭关键词乱认亲。
    4. 遗忘是功能不是缺陷。强度掉到阈值以下就删，巩固过的活得久。
"""

from __future__ import annotations

import math
import re
import zlib
from typing import Any, Dict, List, Optional, Tuple

from .appraisal import DOMAIN_KEYS

TEXT_MAX = 160          # 单条记忆保留的字数
DEFAULT_CAP = 240       # 单会话条数上限
HALF_LIFE_H = 720.0     # 未巩固记忆的半衰期（30 天）
FORGET_AT = 0.06        # 强度低于此值即遗忘
WORKING_CAP = 4         # 工作记忆基础容量（项）

_TAG_ZH = {k: v.split("（")[0] for k, v in DOMAIN_KEYS.items()}


def _clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _now_clock(st, hours: float = 0.0) -> float:
    """虚拟时钟（小时）。身体模块在跑时以它为准，否则按轮次折算。"""
    body = getattr(st, "body", None) or {}
    clock = body.get("clock")
    if isinstance(clock, (int, float)) and clock >= 0:
        return float(clock)
    return float(st.meta.get("turn", 0)) * max(1.0, hours)


# ---------------------------------------------------------------------------
# 分词：中文 2-gram + 拉丁词
# ---------------------------------------------------------------------------
_ASCII = re.compile(r"[a-z0-9]+")
_CJK = re.compile(r"[\u4e00-\u9fff]+")


def _tokens(text: str) -> set:
    s = (text or "").lower()
    out = set(_ASCII.findall(s))
    for run in _CJK.findall(s):
        if len(run) == 1:
            out.add(run)
        for i in range(len(run) - 1):
            out.add(run[i:i + 2])
    return out


def _overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / math.sqrt(len(a) * len(b))


# ---------------------------------------------------------------------------
# 存取
# ---------------------------------------------------------------------------
def ensure(st) -> List[Dict[str, Any]]:
    mem = getattr(st, "mem", None)
    if not isinstance(mem, list):
        mem = []
        st.mem = mem
    return mem


def _tags(st, ap: Dict[str, Any] | None, emo_state: Dict[str, float] | None) -> List[str]:
    tags: List[str] = []
    ap = ap or {}
    for k, v in (ap.get("domains") or {}).items():
        if float(v or 0.0) >= 0.25 and k in _TAG_ZH:
            tags.append(_TAG_ZH[k])
    if ap.get("crisis"):
        tags.append("危机")
    for kw in (ap.get("keywords") or [])[:3]:
        if kw:
            tags.append(str(kw)[:12])
    return tags[:6]


def _encode(st, text: str, ap: Dict[str, Any] | None,
            emo_state: Dict[str, float] | None, hours: float) -> Optional[Dict[str, Any]]:
    text = (text or "").strip()
    if len(text) < 3:
        return None
    mem = ensure(st)
    key = text[:TEXT_MAX]

    # 短时间内重复同一句话不重复记（刷屏保护）；但重复发生说明它重要，
    # 强度加一点。
    for item in mem[-4:]:
        if item.get("text") == key:
            item["s"] = min(2.0, float(item.get("s", 1.0)) + 0.25)
            item["clock"] = _now_clock(st, hours)
            return item

    e = emo_state or {}
    va = 0.0
    ar = 0.5
    if e:
        from .emotion import dimensions   # 延迟导入，避免与 emotion 互相依赖

        d = dimensions(e)
        va, ar = d["valence"], d["arousal"]

    turn = int(st.meta.get("turn", 0))
    item = {
        # crc32 而不是内置 hash：后者带进程级随机盐，重启一次 id 全变
        "id": f"m{turn}_{zlib.crc32(key.encode('utf-8')) % 100000}",
        "text": key,
        "turn": turn,
        "clock": round(_now_clock(st, hours), 2),
        "va": round(va, 3),
        "ar": round(ar, 3),
        "tags": _tags(st, ap, emo_state),
        "s": round(min(2.0, 1.0 + abs(va) * ar * 1.6), 2),
        "hits": 0,
        "con": 0.0,
    }
    mem.append(item)
    _trim(st, mem)
    return item


def _trim(st, mem: List[Dict[str, Any]]) -> None:
    cap = int(st.meta.get("memory_cap") or DEFAULT_CAP)
    if len(mem) <= cap:
        return
    # 淘汰分：巩固程度低、强度低、越旧的越先走。
    # 但最近的几条要保护起来——巩固是累积的，旧条目天然分高，
    # 只按分淘汰会把刚发生的事删掉，留下半年前一句无关紧要的话。
    def score(it: Dict[str, Any]) -> float:
        return float(it.get("s", 1.0)) * (1.0 + float(it.get("con", 0.0)) * 2.0) \
            + float(it.get("hits", 0)) * 0.15

    protect = {id(it) for it in mem[-8:]}
    need = len(mem) - cap
    cand = sorted([it for it in mem if id(it) not in protect], key=score)
    drop = {id(it) for it in cand[:need]}
    mem[:] = [it for it in mem if id(it) not in drop]
    if len(mem) > cap:
        # 受保护的本身就超过上限（上限调到极小），退化为按分淘汰
        cand = sorted(mem, key=score)
        drop = {id(it) for it in cand[:len(mem) - cap]}
        mem[:] = [it for it in mem if id(it) not in drop]


# ---------------------------------------------------------------------------
# 演化
# ---------------------------------------------------------------------------
def step(st, text: str, ap: Dict[str, Any] | None, hours: float,
         emo_state: Dict[str, float] | None = None,
         cfg: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """推进一轮记忆：衰减 → 巩固 → 编码 → 遗忘。"""
    mem = ensure(st)
    hours = max(0.02, min(72.0, float(hours or 1.0)))

    # 1. 强度衰减。巩固程度越高衰减越慢（皮层表征比海马痕迹稳）。
    for it in mem:
        con = float(it.get("con", 0.0))
        half = HALF_LIFE_H * (1.0 + 1.5 * con)
        it["s"] = float(it.get("s", 1.0)) * (0.5 ** (hours / half))

    # 2. 巩固：睡眠时段更快，被检索过的也更快
    sleep_h = float(((getattr(st, "body", None) or {}).get("life") or {}).get("sleep_h", 7.0) or 7.0)
    sleep_w = 1.0 + min(1.0, max(0.0, sleep_h) / 8.0)
    for it in mem:
        gain = 0.004 * (hours / 6.0) * sleep_w * (1.0 + 0.2 * float(it.get("hits", 0)))
        it["con"] = _clip(float(it.get("con", 0.0)) + gain)

    # 3. 编码
    made = _encode(st, text, ap, emo_state, hours)

    # 4. 遗忘
    before = len(mem)
    mem[:] = [it for it in mem if float(it.get("s", 1.0)) >= FORGET_AT]
    return {"encoded": made is not None, "forgotten": max(0, before - len(mem)),
            "total": len(mem)}


# ---------------------------------------------------------------------------
# 检索
# ---------------------------------------------------------------------------
def search(st, query: str, limit: int = 5,
           emo_state: Dict[str, float] | None = None,
           before_turn: Optional[int] = None) -> List[Tuple[Dict[str, Any], float]]:
    mem = ensure(st)
    if not mem:
        return []
    if before_turn is not None:
        # 只检索本轮之前的事：本轮刚说的话不算「记得」
        mem = [it for it in mem if int(it.get("turn", -1)) < int(before_turn)]
        if not mem:
            return []
    q = _tokens(query)
    cur_va = 0.0
    if emo_state:
        from .emotion import dimensions

        cur_va = dimensions(emo_state)["valence"]

    now = _now_clock(st)
    scored: List[Tuple[Dict[str, Any], float]] = []
    for it in mem:
        body_score = _overlap(q, _tokens(it.get("text", "")))
        tag_hit = len(set(it.get("tags") or []) & q)
        score = body_score + 0.12 * tag_hit
        if score <= 0:
            continue
        # 情绪一致性：同效价的记忆更容易被想起
        score *= 1.0 + 0.15 * (1.0 - abs(float(it.get("va", 0.0)) - cur_va) / 2.0)
        # 时间与强度
        age_h = max(0.0, now - float(it.get("clock", now)))
        score *= math.exp(-age_h / 900.0) * min(1.6, float(it.get("s", 1.0)))
        if score >= 0.06:
            scored.append((it, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    for it, _ in scored[:3]:
        it["hits"] = int(it.get("hits", 0)) + 1
        it["s"] = min(2.0, float(it.get("s", 1.0)) * 1.05)
        it["con"] = _clip(float(it.get("con", 0.0)) + 0.03)
    return scored[:limit]


def working_set(st, hours: float = 6.0) -> List[Dict[str, Any]]:
    """工作记忆：最近且强度足够高的几条。容量受生化影响。

    容量不单独存一份列表——存了就要同步维护，容易和主表对不上。
    直接按「最近」取，容量由 NE / ACh / 皮质醇 / 海马功能决定。
    """
    mem = ensure(st)
    if not mem:
        return []
    cap = WORKING_CAP
    for bio, w in (("norepinephrine", 1.0), ("acetylcholine", 0.8),
                   ("dopamine_tonic", 0.6)):
        try:
            z = st.z_bio(bio)
        except KeyError:
            continue
        cap += int(round(w * max(-1.0, min(1.0, z))))
    for bio, w in (("cortisol", 1.2),):
        try:
            z = st.z_bio(bio)
        except KeyError:
            continue
        cap -= int(round(w * max(0.0, min(1.5, z))))
    cap = max(2, min(7, cap))
    return sorted(mem, key=lambda it: float(it.get("clock", 0.0)),
                  reverse=True)[:cap]


def stats(st) -> Dict[str, Any]:
    mem = ensure(st)
    if not mem:
        return {"total": 0, "consolidated": 0, "avg_strength": 0.0,
                "working": 0, "oldest_turn": None, "newest_turn": None}
    strong = sum(1 for it in mem if float(it.get("con", 0.0)) >= 0.5)
    return {
        "total": len(mem),
        "consolidated": strong,
        "avg_strength": sum(float(it.get("s", 1.0)) for it in mem) / len(mem),
        "working": len(working_set(st)),
        "oldest_turn": min(int(it.get("turn", 0)) for it in mem),
        "newest_turn": max(int(it.get("turn", 0)) for it in mem),
    }


def clear(st) -> int:
    mem = ensure(st)
    n = len(mem)
    mem.clear()
    return n


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------
def _valence_word(va: float) -> str:
    if va <= -0.45:
        return "当时很难受"
    if va <= -0.15:
        return "当时不太舒服"
    if va >= 0.45:
        return "当时是高兴的"
    if va >= 0.15:
        return "当时还算轻松"
    return "当时没什么起伏"


def _age_word(st, it: Dict[str, Any]) -> str:
    turn = int(st.meta.get("turn", 0))
    gap = max(0, turn - int(it.get("turn", turn)))
    if gap == 0:
        return "刚刚"
    if gap == 1:
        return "上一轮"
    if gap <= 3:
        return f"前 {gap} 轮"
    if gap <= 10:
        return "几轮前"
    if gap <= 40:
        return "早些时候"
    return "很久以前"


def render_block(st, query: str = "", limit: int = 4,
                 emo_state: Dict[str, float] | None = None) -> str:
    """注入段：这一句勾起了哪几件事。"""
    mem = ensure(st)
    if not mem:
        return ""

    # 本轮刚说的话不算「记得」——那是刚刚听到的
    cur_turn = int(st.meta.get("turn", 0))
    hist = [it for it in mem if int(it.get("turn", -1)) < cur_turn]
    if not hist:
        return ""

    lines: List[str] = []
    picked: List[Tuple[Dict[str, Any], float]] = []
    seen: set = set()
    seen_text: set = set()

    def take(it: Dict[str, Any], sc: float) -> bool:
        # 同一句话隔几轮又说一遍会重新编码成新条目，但注入段列两条一样的
        # 只会白占篇幅，所以按文本再去一次重
        key = str(it.get("text", ""))[:40]
        if id(it) in seen or key in seen_text:
            return False
        picked.append((it, sc))
        seen.add(id(it))
        seen_text.add(key)
        return True

    if query:
        for it, sc in search(st, query, limit=limit, emo_state=emo_state,
                             before_turn=cur_turn):
            take(it, sc)

    # 再补最近发生的一条：检索为 0 时，人记住的通常就是「刚说过的」。
    # 只补一条——补多了会把「印象最深」的位置占满，一场争吵里最重的那句
    # 就永远排不上。
    recent = sorted(hist, key=lambda it: float(it.get("clock", 0.0)), reverse=True)
    for it in recent[:1]:
        if len(picked) >= limit:
            break
        take(it, 0.0)

    # 还不足就按「强度 × 情绪强度」补，把印象最深的事带上来——
    # 只按时间取的话，一场对话里最重的那句会被后几句废话挤掉。
    if len(picked) < limit:
        rest = [it for it in hist if id(it) not in seen]
        rest.sort(key=lambda it: float(it.get("s", 1.0))
                  * (1.0 + abs(float(it.get("va", 0.0)))), reverse=True)
        for it in rest:
            if len(picked) >= limit:
                break
            take(it, 0.0)

    if not picked:
        return ""

    lines.append("- 你还记得这些（不必主动复述，除非对方问起或它影响了你的反应）：")
    for it, score in picked[:limit]:
        txt = str(it.get("text", ""))[:70]
        tag = "｜".join(it.get("tags") or [])[:24]
        mark = "（这一句直接勾起）" if score >= 0.25 else ""
        lines.append(f"  · {_age_word(st, it)}｜{txt}"
                     + (f"［{tag}］" if tag else "") + f"｜{_valence_word(float(it.get('va', 0.0)))}{mark}")
    lines.append("- 记忆是有偏的：情绪强烈的事记得清，平淡的事会记错、记混，"
                 "也可能把两件事并成一件。不要声称自己记得比这更细。")
    return "\n".join(lines)


def render_report(st, query: str = "", limit: int = 15,
                  emo_state: Dict[str, float] | None = None) -> str:
    """用户可见：/心理 记忆 [关键词]"""
    mem = ensure(st)
    if not mem:
        return "暂无记忆（记忆模块关闭，或还没开始对话）。"

    if query:
        rows = search(st, query, limit=limit, emo_state=emo_state)
        if not rows:
            return f"没有和「{query}」相关的记忆。"
        out = [f"── 记忆检索「{query}」· 命中 {len(rows)} 条 ──"]
        for it, score in rows:
            out.append(f"第 {int(it.get('turn', 0)):>3d} 轮 · {score:.2f} · "
                       f"{_valence_word(float(it.get('va', 0.0)))}"
                       + (f"［{'｜'.join(it.get('tags') or [])}］" if it.get("tags") else ""))
            out.append(f"        {str(it.get('text', ''))[:100]}")
        return "\n".join(out)

    s = stats(st)
    out = [f"── 记忆 · 共 {s['total']} 条（巩固 {s['consolidated']} 条，"
           f"平均强度 {s['avg_strength']:.2f}）──",
           f"跨度 第 {s['oldest_turn']} 轮 → 第 {s['newest_turn']} 轮｜工作记忆 {s['working']} 条",
           ""]
    recent = sorted(mem, key=lambda it: float(it.get("clock", 0.0)), reverse=True)
    for it in recent[:limit]:
        out.append(f"第 {int(it.get('turn', 0)):>3d} 轮 · 强度 {float(it.get('s', 1.0)):.2f} · "
                   f"巩固 {float(it.get('con', 0.0)):.2f} · {_valence_word(float(it.get('va', 0.0)))}")
        out.append(f"        {str(it.get('text', ''))[:100]}")
    if s["total"] > limit:
        out.append(f"\n（仅显示最近 {limit} 条，用「/心理 记忆 关键词」检索）")
    return "\n".join(out)
