"""类脑记忆：编码、分层、巩固、检索与遗忘（SQLite 版）。

为什么要有这一层
    注入块只描述「此刻」。没有记忆的角色，每轮都像刚认识对方：
    昨天说过的丧事、前天约好的事、上周吵过的架，一律不认。记忆层
    给的是连续性，不是知识库——它只回答一个问题：这句话勾起了哪几件
    事，那些事当时是什么滋味。

四层怎么分工
    瞬时   刚说过的话。容量 9，被挤出去时若够重就沉到短期，否则丢掉。
    短期   一天量级。半衰期 24 小时，命中两次或巩固到 0.45 升到较长期。
    较长期 几周量级。半衰期 14 天，被反复想起且跨度够长才升长期。
    长期   近永久。不再衰减，只在超过硬上限时按「被想起次数 × 强度」淘汰。

    分层的实质是晋升规则，不是四个抽屉。写进哪一层由「它被想起来的
    次数」和「它是不是人生节点」共同决定，不是由时间决定——三年前
    一句寒暄不该留在长期，昨天一场葬礼不该停在瞬时。

存储
    表与索引见 psyche/memdb.py。这里只负责把状态对象和库接起来、
    把检索结果渲染成给模型看的一段话。

两条约束
    1. 时间一律走虚拟时钟（vclock）。真实时钟模式下它就是真实经过的
       小时数，虚拟模式下是每轮累加的小时数——两种模式都能算年龄。
    2. 检索不做语义理解。中文 2-gram 加 FTS5 bm25，宁可少召回，也不
       凭关键词乱认亲。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import memdb as _mdb
from .appraisal import DOMAIN_KEYS

TEXT_MAX = 160
WORKING_CAP = 4

_TAG_ZH = {k: v.split("（")[0] for k, v in DOMAIN_KEYS.items()}
LAYER_ZH = _mdb.LAYER_ZH


# ----------------------------------------------------------------------
# 绑定
# ----------------------------------------------------------------------
def bind(st, path: str, umo: str, cfg: Optional[Dict[str, Any]] = None,
         db=None) -> None:
    """给状态挂上记忆库。由 Engine.load 调用，一个会话一个 umo。

    db 可以外部传入：引擎只持有一个连接，多个会话靠 umo 隔离，
    否则每开一个群就多一条 sqlite 连接。
    """
    st._memdb = db if db is not None else _mdb.MemDB(path, cfg or {})
    st._umo = umo


def detach(st) -> None:
    db = getattr(st, "_memdb", None)
    if db is not None:
        try:
            db.close()
        except Exception:
            pass
    st._memdb = None
    st._umo = ""


def _umo(st) -> str:
    u = getattr(st, "_umo", "") or ""
    if u:
        return u
    # 没有显式绑定时的退路：按创建时间与轮次凑一个稳定键，
    # 至少不会把两个会话的记忆混在一起。
    return f"anon:{id(st)}"


def _db(st):
    db = getattr(st, "_memdb", None)
    if db is None:
        return None
    umo = _umo(st)
    if not db.migrated(umo):
        legacy = getattr(st, "mem", None) or []
        if legacy:
            db.migrate(umo, legacy)      # 旧 JSON 存档一次性搬进表
        else:
            db.mark_migrated(umo)
        try:
            st.mem = []                  # 主存已经不在 JSON 里了
        except Exception:
            pass
    return db


# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------
def _clip(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _now_clock(st, hours: float = 0.0) -> float:
    """虚拟时钟（小时）。身体模块在跑时以它为准，否则按轮次折算。"""
    body = getattr(st, "body", None) or {}
    clock = body.get("clock")
    if isinstance(clock, (int, float)) and clock >= 0:
        return float(clock)
    return float(st.meta.get("turn", 0)) * max(1.0, hours)


def _tags(st, ap: Dict[str, Any] | None,
          emo_state: Dict[str, float] | None) -> List[str]:
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


def _dims(emo_state: Optional[Dict[str, float]]) -> Tuple[float, float, str]:
    if not emo_state:
        return 0.0, 0.5, ""
    from .emotion import dimensions

    d = dimensions(emo_state)
    return float(d["valence"]), float(d["arousal"]), str(d.get("dominant", ""))


# ----------------------------------------------------------------------
# 演化
# ----------------------------------------------------------------------
# 纯寒暄。它们连「短期」都不该占位：问一句「在吗」不值得成为回忆。
_TRIVIAL = frozenset({
    "在吗", "在么", "在不在", "嗯", "嗯嗯", "哦", "噢", "好", "好的", "行",
    "哈哈", "哈哈哈", "呵呵", "嘿嘿", "你好", "您好", "早", "早安", "晚安",
    "没事", "没什么", "不知道", "随便聊聊", "聊聊", "聊聊天", "没事干",
    "对", "是的", "收到", "ok", "OK",
})


def _worth(text: str, va: float, tags: List[str]) -> bool:
    """这句话值不值得记。

    寒暄不进记忆——不是嫌它短，是它没有任何可召回的内容，而容量 9 的
    瞬时层六句寒暄就能把「我爸住院了」顶出去。事实陈述则一律放行：
    「我住在成都」没有情绪、没有标签，但它正是最该被记住的那类东西。
    """
    t = (text or "").strip(" 。！？…~,.!?、")
    if not t or t in _TRIVIAL:
        return False
    if tags or abs(va) >= 0.20:
        return True
    return len(t) >= 5


def _significance(va: float, ar: float, tags: List[str], text: str) -> float:
    """显著度 0.25~2.0。基线 0.30：中性短句过不了晋升门槛，会被丢掉。"""
    s = 0.30 + abs(va) * ar * 1.4 + 0.08 * min(3, len(tags))
    if _mdb.is_milestone(text):
        s += 0.25
    return min(2.0, s)


def step(st, text: str, ap: Dict[str, Any] | None, hours: float,
         emo_state: Dict[str, float] | None = None,
         cfg: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """推进一轮记忆：衰减 → 编码 → 晋升 → 淘汰。"""
    db = _db(st)
    if db is None:
        return {"encoded": False, "forgotten": 0, "total": 0}
    umo = _umo(st)
    hours = max(0.02, min(72.0, float(hours or 1.0)))
    va, ar, dom = _dims(emo_state)
    clock = _now_clock(st, hours)
    turn = int(st.meta.get("turn", 0))

    gone = db.decay(umo, hours, cur_va=va)

    made = None
    body = (text or "").strip()
    tags = _tags(st, ap, emo_state)
    if len(body) >= 3 and _worth(body, va, tags):
        made = db.encode(
            umo, body, turn=turn, vclock=clock, s=_significance(va, ar, tags, body),
            va=va, ar=ar, tags=tags, emo=dom, layer="instant",
        )
        # 危机与不可逆的人生节点不该在工作记忆里等下一轮：直接压到
        # 该去的那一层，否则下一句闲聊就能把它们挤出容量 9。
        # 这里绕过晋升链是有意的——「确诊」「葬礼」不需要被想起来五次
        # 才算长期记忆。
        if made and not made.get("reinforced"):
            if (ap or {}).get("crisis") or _mdb.is_milestone_core(body):
                db._set_layer(int(made["id"]), "long", pinned=True)
            elif _mdb.is_milestone(body):
                db._set_layer(int(made["id"]), "short")
                db.touch(int(made["id"]), hit=False, con_gain=0.25)

    moved = db.promote(umo, now_vclock=clock)
    db.trim_all(umo)
    return {
        "encoded": made is not None,
        "reinforced": bool(made and made.get("reinforced")),
        "forgotten": gone,
        "promoted": moved,
        "total": db.total(umo),
    }


# ----------------------------------------------------------------------
# 检索
# ----------------------------------------------------------------------
def search(st, query: str, limit: int = 5,
           emo_state: Dict[str, float] | None = None,
           before_turn: Optional[int] = None,
           layers: Tuple[str, ...] = _mdb.LAYERS,
           ) -> List[Tuple[Dict[str, Any], float]]:
    db = _db(st)
    if db is None:
        return []
    va, _, _ = _dims(emo_state)
    rows = db.search(_umo(st), query, limit=limit, cur_va=va,
                     before_turn=before_turn, layers=layers)
    # 被想起来一次，就更容易再被想起来：这部分是「检索即复习」
    for it, _score in rows[:3]:
        db.touch(int(it["id"]), hit=True, s_gain=0.05, con_gain=0.03)
    return rows


def working_set(st, hours: float = 6.0) -> List[Dict[str, Any]]:
    """工作记忆：最近的一批，容量受生化影响。"""
    db = _db(st)
    if db is None:
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
    cap = max(2, min(9, cap))
    return db.recent(_umo(st), limit=cap, layer="instant")


def latest(st, before_turn: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """最近一条记忆。压缩块用它，避免整份渲染被截断。"""
    db = _db(st)
    if db is None:
        return None
    rows = db.recent(_umo(st), limit=1, before_turn=before_turn)
    return rows[0] if rows else None


def stats(st) -> Dict[str, Any]:
    db = _db(st)
    if db is None:
        return {"total": 0, "layers": {k: 0 for k in _mdb.LAYERS},
                "consolidated": 0, "avg_strength": 0.0,
                "working": 0, "oldest_turn": None, "newest_turn": None}
    umo = _umo(st)
    layers = db.counts(umo)
    lo, hi = db.turn_span(umo)
    total = sum(layers.values())
    return {
        "total": total,
        "layers": layers,
        "consolidated": db.consolidated(umo),
        "avg_strength": db.avg_strength(umo),
        "working": len(working_set(st)),
        "oldest_turn": lo,
        "newest_turn": hi,
        "fts": db.fts,
    }


def clear(st, layer: Optional[str] = None) -> int:
    db = _db(st)
    if db is None:
        return 0
    return db.clear(_umo(st), layer)


# ----------------------------------------------------------------------
# 渲染
# ----------------------------------------------------------------------
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


def _when(st, it: Dict[str, Any]) -> str:
    """相对时间。按虚拟时钟差算，两种时钟模式都成立。"""
    now = _now_clock(st)
    age = max(0.0, now - float(it.get("vclock", now)))
    if age < 1.0:
        return "刚刚"
    if age < 12.0:
        return f"{int(age)} 小时内"
    if age < 36.0:
        return "昨天前后"
    if age < 24.0 * 7:
        return f"{int(age / 24)} 天前"
    if age < 24.0 * 30:
        return f"{int(age / 24 / 7)} 周前"
    if age < 24.0 * 365:
        return f"{int(age / 24 / 30)} 个月前"
    return f"{int(age / 24 / 365)} 年前"


def _layer_word(it: Dict[str, Any]) -> str:
    return LAYER_ZH.get(str(it.get("layer", "short")), "短期")


def render_block(st, query: str = "", limit: int = 4,
                 emo_state: Dict[str, float] | None = None) -> str:
    """注入段：这一句勾起了哪几件事。"""
    db = _db(st)
    if db is None:
        return ""
    umo = _umo(st)
    cur_turn = int(st.meta.get("turn", 0))

    picked: List[Tuple[Dict[str, Any], float]] = []
    seen: set = set()
    seen_text: set = set()

    def take(it: Dict[str, Any], sc: float) -> bool:
        key = str(it.get("text", ""))[:40]
        if int(it.get("id", 0)) in seen or key in seen_text:
            return False
        picked.append((it, sc))
        seen.add(int(it.get("id", 0)))
        seen_text.add(key)
        return True

    if query:
        for it, sc in search(st, query, limit=limit, emo_state=emo_state,
                             before_turn=cur_turn):
            take(it, sc)

    # 补最近一条：检索为 0 时，人记住的通常就是「刚说过的」。
    for it in db.recent(umo, limit=1, before_turn=cur_turn):
        if len(picked) >= limit:
            break
        take(it, 0.0)

    # 还不够就按强度补：一场对话里最重的那句不该被后几句废话挤掉
    if len(picked) < limit:
        for it in db.strongest(umo, limit=limit + 4, before_turn=cur_turn):
            if len(picked) >= limit:
                break
            take(it, 0.0)

    if not picked:
        return ""

    lines: List[str] = []
    lines.append("- 你还记得这些（不必主动复述，除非对方问起或它影响了你的反应）：")
    for it, score in picked[:limit]:
        txt = str(it.get("text", ""))[:70]
        tag = str(it.get("tags", ""))[:24]
        mark = "（这一句直接勾起）" if score >= 0.25 else ""
        lines.append(
            f"  · {_layer_word(it)}｜{_when(st, it)}｜{txt}"
            + (f"［{tag}］" if tag else "")
            + f"｜{_valence_word(float(it.get('va', 0.0)))}{mark}"
        )
    lines.append(
        "- 记忆是有偏的：长期的事稳固但细节会磨平，近期的事清楚但可能记混；"
        "情绪强烈的事记得清，平淡的事会记错，也可能把两件事并成一件。"
        "不要声称自己记得比这更细。"
    )
    return "\n".join(lines)


def render_report(st, query: str = "", limit: int = 15,
                  emo_state: Dict[str, float] | None = None) -> str:
    """用户可见：/心理 记忆 [关键词]"""
    db = _db(st)
    if db is None:
        return "记忆库未启用（memory_enabled=false）。"
    umo = _umo(st)
    s = stats(st)
    if s["total"] == 0:
        return "暂无记忆（还没开始对话，或已清空）。"

    if query:
        rows = search(st, query, limit=limit, emo_state=emo_state)
        if not rows:
            return f"没有和「{query}」相关的记忆。"
        out = [f"── 记忆检索「{query}」· 命中 {len(rows)} 条 ──"]
        for it, score in rows:
            out.append(
                f"{_layer_word(it)} · 第 {int(it.get('turn', 0)):>3d} 轮 · "
                f"{_when(st, it)} · 相关 {score:.2f} · "
                f"{_valence_word(float(it.get('va', 0.0)))}"
                + (f"［{it.get('tags')}］" if it.get("tags") else "")
            )
            out.append(f"        {str(it.get('text', ''))[:100]}")
        return "\n".join(out)

    ly = s["layers"]
    out = [
        f"── 记忆 · 共 {s['total']} 条（平均强度 {s['avg_strength']:.2f}）──",
        "｜".join(f"{LAYER_ZH[k]} {ly.get(k, 0)}" for k in _mdb.LAYERS)
        + f"｜工作记忆 {s['working']} 条",
        f"跨度 第 {s['oldest_turn']} 轮 → 第 {s['newest_turn']} 轮"
        + ("｜FTS5 索引在线" if s.get("fts") else "｜FTS5 不可用，走倒排表"),
        "",
    ]
    for layer in ("long", "medium", "short", "instant"):
        rows = db.by_layer(umo, layer, limit=max(4, limit // 3))
        if not rows:
            continue
        out.append(f"【{LAYER_ZH[layer]}】{ly.get(layer, 0)} 条")
        for it in rows:
            out.append(
                f"  第 {int(it.get('turn', 0)):>3d} 轮 · 强度 {float(it.get('s', 1)):.2f}"
                f" · 巩固 {float(it.get('con', 0)):.2f} · 命中 {int(it.get('hits', 0))}"
                f" · {_when(st, it)}"
            )
            out.append(f"        {str(it.get('text', ''))[:100]}")
        out.append("")
    out.append("（用「/心理 记忆 关键词」检索，或「/心理 记忆 层 长期」只看某一层）")
    return "\n".join(out)


def dump(st, limit_per_layer: int = 500) -> List[Dict[str, Any]]:
    """所有层的条目，平铺。测试与调试用。"""
    db = _db(st)
    if db is None:
        return []
    out: List[Dict[str, Any]] = []
    for layer in _mdb.LAYERS:
        out.extend(db.by_layer(_umo(st), layer, limit=limit_per_layer))
    return out


def render_layer(st, layer: str, limit: int = 20) -> str:
    """用户可见：某一层的前若干条。"""
    db = _db(st)
    if db is None:
        return "记忆库未启用。"
    if layer not in _mdb.LAYERS:
        return f"未知层级「{layer}」。可选：瞬时 / 短期 / 较长期 / 长期。"
    rows = db.by_layer(_umo(st), layer, limit=limit)
    if not rows:
        return f"【{LAYER_ZH[layer]}】还是空的。"
    out = [f"── {LAYER_ZH[layer]} · {len(rows)} 条 ──"]
    for it in rows:
        out.append(
            f"第 {int(it.get('turn', 0)):>3d} 轮 · 强度 {float(it.get('s', 1)):.2f}"
            f" · 命中 {int(it.get('hits', 0))} · {_when(st, it)}"
        )
        out.append(f"     {str(it.get('text', ''))[:110]}")
    return "\n".join(out)
