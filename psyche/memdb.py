"""四层记忆库：SQLite 建表、建索引、存原文、跑检索。

为什么不放在 JSON 里
    状态 JSON 每次落盘要把整份 mem 列表序列化一遍。240 条时是几十 KB，
    无所谓；分层之后是几千条，每轮都写一遍就变成明显的 CPU 与 IO 开销，
    而且「按关键词找一条」只能全表扫。记忆天然是表，不是字段。

四层不是四个数组
    人的记忆不是按时间切段的抽屉，而是一套按「还重不重要」流动的层级：
    刚说过的话先进工作记忆（瞬时），值得留的沉到短期，反复被想起来的
    沉到较长期，跨越很久还被想起来、或本身就是人生节点的才进长期。
    所以分层的实质是**晋升规则**，不是四个独立容器。

    | 层 | 容量 | 半衰期 | 晋升到下一层 |
    |---|---|---|---|
    | instant 瞬时 | 9 | 不衰减，挤出即走 | 强度 ≥0.30 或 |效价| ≥0.45 |
    | short 短期 | 240 | 24 小时 | 命中 ≥2 次或巩固 ≥0.45 |
    | medium 较长期 | 480 | 14 天 | 命中 ≥5 次且跨度 ≥30 天，或里程碑 |
    | long 长期 | 2000 | 不衰减 | —（接近永久，硬上限保护） |

两套索引
    FTS5 建在「2-gram 空格串」上：中文没有分词器，把正文切成 2-gram
    存进去，unicode61 按空格切词，等于自己做了分词。bm25 排序直接可用。
    另建一张 mem_term 倒排表作兜底——不是所有 sqlite 编译都带 FTS5
    （某些精简发行版、部分 Android 内置版本），缺了不能让检索整体失灵。

一个必须说清的取舍
    检索不做语义理解。「被辞退了」勾不出「被裁员」，因为 2-gram 不重叠。
    这不是没做完，是刻意的：凭关键词乱认亲比少召回更伤角色可信度。
"""

from __future__ import annotations

import math
import os
import re
import sqlite3
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ----------------------------------------------------------------------
# 分层常量
# ----------------------------------------------------------------------
LAYERS = ("instant", "short", "medium", "long")
LAYER_ZH = {"instant": "瞬时", "short": "短期", "medium": "较长期", "long": "长期"}

CAP = {"instant": 9, "short": 240, "medium": 480, "long": 2000}
# 半衰期（小时）。long 用 None 表示不衰减。
HALF_LIFE = {"instant": None, "short": 24.0, "medium": 336.0, "long": None}
FORGET_AT = 0.06

# 晋升阈值。
# 强度不再是「1.0 起」：1.0 的基线会让每一句闲聊都越过门槛，
# 工作记忆永远清不空，短期层被「随便聊聊」灌满。现在由调用方按
# 显著性给分（基线 0.30），门槛才真正起到筛选作用。
P_INSTANT = 0.34          # 强度
P_INSTANT_VA = 0.35       # 或 |效价|
P_SHORT_HITS = 2
P_SHORT_CON = 0.45
P_MEDIUM_HITS = 5
P_MEDIUM_SPAN_H = 30 * 24.0
P_MEDIUM_S = 0.55         # 里程碑 + 强度

TEXT_MAX = 160
SIG_MAX = 60

# 人生节点词。命中且强度够，直接从当前层提到 long——这类事不需要
# 反复想起来才算长期记忆，一次就够。
MILESTONE = (
    "去世", "死了", "走了", "葬礼", "追悼", "临终", "病危",
    "结婚", "婚礼", "离婚", "分手", "表白", "在一起",
    "怀孕", "流产", "生了", "孩子", "宝宝", "产检",
    "手术", "住院", "确诊", "癌症", "化疗", "透析", "抢救",
    "失业", "辞职", "被裁", "入职", "升职", "毕业", "考上", "落榜",
    "搬家", "移民", "出国", "欠债", "破产", "坐牢",
    "自杀", "自伤", "崩溃", "报警",
)

# 其中最不可逆的那一批：说出来一次就该进长期，不靠反复提起。
# 其余节点（入职、搬家、毕业）先进短期——它们重要，但人生里出现得
# 比丧亲频繁得多，一次性全部塞进永久层会让长期层迅速失去区分度。
MILESTONE_CORE = (
    "去世", "死了", "葬礼", "追悼", "临终", "病危", "流产",
    "手术", "住院", "确诊", "癌症", "化疗", "透析", "抢救",
    "破产", "坐牢", "自杀", "自伤", "报警", "离婚",
)

# ----------------------------------------------------------------------
# 分词
# ----------------------------------------------------------------------
_ASCII = re.compile(r"[a-z0-9]+")
_CJK = re.compile(r"[\u4e00-\u9fff]+")


def terms(text: str, with_tf: bool = False):
    """中文 2-gram + 拉丁词。with_tf=True 时返回 {term: 次数}。"""
    s = (text or "").lower()
    counts: Dict[str, int] = {}

    def add(t: str) -> None:
        counts[t] = counts.get(t, 0) + 1

    for w in _ASCII.findall(s):
        add(w)
    for run in _CJK.findall(s):
        if len(run) == 1:
            add(run)
        for i in range(len(run) - 1):
            add(run[i:i + 2])
    return counts if with_tf else set(counts)


# 同义组：检索是 2-gram 字面匹配，「被辞退」与「被裁员」没有一个字重叠，
# 于是勾不出来。这里只放高频、且字面确实不通的几组——不做语义模型，
# 做的是「同一件事的几种叫法」。扩展词的权重打六折，字面命中永远优先。
_SYNONYMS: Tuple[Tuple[str, ...], ...] = (
    ("辞退", "裁员", "开除", "解雇", "优化", "下岗", "失业", "离职"),
    ("难过", "伤心", "低落", "失落", "想哭", "沮丧", "难受"),
    ("失眠", "睡不着", "熬夜", "通宵", "早醒"),
    ("分手", "离婚", "散伙", "分开"),
    ("工资", "薪水", "收入", "报酬", "发薪"),
    ("住院", "手术", "开刀", "病房", "出院"),
    ("生病", "病了", "不舒服", "发烧", "感冒"),
    ("父亲", "爸", "老爸", "爹"),
    ("母亲", "妈", "老妈", "娘"),
    ("考试", "期末", "答辩", "面试", "笔试"),
    ("孩子", "儿子", "女儿", "小孩"),
    ("猫", "猫猫", "猫咪"),
)


def _syn_terms(query: str) -> List[str]:
    """把查询里出现的词换成同组的其他说法，返回扩展后的 2-gram。"""
    q = (query or "").strip()
    if not q:
        return []
    extra: List[str] = []
    for group in _SYNONYMS:
        if not any(w in q for w in group):
            continue
        for w in group:
            if w not in q:
                extra.append(w)
    if not extra:
        return []
    return sorted(terms(" ".join(extra[:24])))


def _sig(text: str) -> str:
    return re.sub(r"\s+", "", (text or ""))[:SIG_MAX]


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def is_milestone(text: str) -> bool:
    t = text or ""
    return any(w in t for w in MILESTONE)


def is_milestone_core(text: str) -> bool:
    """不可逆的节点：一次就进长期。"""
    t = text or ""
    return any(w in t for w in MILESTONE_CORE)


# ----------------------------------------------------------------------
# 库
# ----------------------------------------------------------------------
class MemDB:
    """一个文件、多会话共用；用 umo 列隔离。"""

    _fts_ok: Optional[bool] = None     # 类级缓存：同一个进程只需要探一次

    def __init__(self, path: str, cfg: Optional[Dict[str, Any]] = None):
        self.path = path
        self.cfg = cfg or {}
        d = os.path.dirname(os.path.abspath(path))
        if d:
            os.makedirs(d, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, timeout=5.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=3000")
        # 容量可按会话配置覆盖：memory_max 控制「短期」这一档，
        # 其余按比例走，避免把 240 直接当总量导致分层退化成一层。
        self.cap = dict(CAP)
        try:
            short_cap = int(self.cfg.get("memory_max", CAP["short"]))
        except (TypeError, ValueError):
            short_cap = CAP["short"]
        self.cap["short"] = max(20, short_cap)
        self.cap["medium"] = max(40, short_cap * 2)
        self._init()

    # ------------------------------------------------------------------
    # 建表建索引
    # ------------------------------------------------------------------
    def _init(self) -> None:
        with self._lock:
            c = self._conn
            c.execute(
                """CREATE TABLE IF NOT EXISTS memory (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    umo      TEXT NOT NULL,
                    layer    TEXT NOT NULL,
                    turn     INTEGER NOT NULL DEFAULT 0,
                    ts       REAL NOT NULL,
                    vclock   REAL NOT NULL DEFAULT 0,
                    text     TEXT NOT NULL,
                    sig      TEXT NOT NULL,
                    s        REAL NOT NULL DEFAULT 1.0,
                    con      REAL NOT NULL DEFAULT 0.0,
                    va       REAL NOT NULL DEFAULT 0.0,
                    ar       REAL NOT NULL DEFAULT 0.5,
                    emo      TEXT NOT NULL DEFAULT '',
                    tags     TEXT NOT NULL DEFAULT '',
                    hits     INTEGER NOT NULL DEFAULT 0,
                    last_hit REAL NOT NULL DEFAULT 0,
                    pinned   INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(umo, sig)
                )"""
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_m_umo_layer ON memory(umo, layer, s DESC)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_m_umo_ts ON memory(umo, ts DESC)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_m_umo_vclock ON memory(umo, vclock)")

            # 倒排表：FTS5 不可用时的兜底，也用于「按词精确命中数」加权
            c.execute(
                """CREATE TABLE IF NOT EXISTS mem_term (
                    umo    TEXT NOT NULL,
                    term   TEXT NOT NULL,
                    mem_id INTEGER NOT NULL,
                    tf     INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (umo, term, mem_id)
                ) WITHOUT ROWID"""
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_t_term ON mem_term(umo, term)")

            c.execute(
                """CREATE TABLE IF NOT EXISTS mem_meta (
                    umo TEXT PRIMARY KEY,
                    migrated INTEGER NOT NULL DEFAULT 0,
                    updated REAL NOT NULL DEFAULT 0
                )"""
            )

            if MemDB._fts_ok is None:
                try:
                    c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
                    c.execute("DROP TABLE IF EXISTS _fts_probe")
                    MemDB._fts_ok = True
                except Exception:
                    MemDB._fts_ok = False

            if MemDB._fts_ok:
                try:
                    c.execute(
                        """CREATE VIRTUAL TABLE IF NOT EXISTS mem_fts USING fts5(
                            tokens, umo UNINDEXED, mem_id UNINDEXED,
                            tokenize='unicode61')"""
                    )
                except Exception:
                    MemDB._fts_ok = False
            c.commit()

    @property
    def fts(self) -> bool:
        return bool(MemDB._fts_ok)

    # ------------------------------------------------------------------
    # 写
    # ------------------------------------------------------------------
    def encode(self, umo: str, text: str, *, turn: int = 0, vclock: float = 0.0,
               s: float = 1.0, va: float = 0.0, ar: float = 0.5,
               tags: Optional[Iterable[str]] = None, emo: str = "",
               layer: str = "instant") -> Optional[Dict[str, Any]]:
        """写一条。同一句话（前 60 字相同）不重复存，只加固。"""
        text = (text or "").strip()
        if len(text) < 3:
            return None
        text = text[:TEXT_MAX]
        sig = _sig(text)
        if not sig:
            return None
        tag_s = "｜".join(list(tags or [])[:6])
        now = time.time()

        with self._lock:
            row = self._conn.execute(
                "SELECT id, layer, s, hits FROM memory WHERE umo=? AND sig=?",
                (umo, sig),
            ).fetchone()
            if row:
                # 复述同一件事：强度加固，命中数 +1，但层级只升不降
                self._conn.execute(
                    "UPDATE memory SET s=MIN(2.0, s+0.15), hits=hits+1, "
                    "last_hit=?, turn=?, vclock=?, ts=? WHERE id=?",
                    (now, turn, vclock, now, row["id"]),
                )
                self._conn.commit()
                return {"id": row["id"], "reinforced": True, "layer": row["layer"]}

            cur = self._conn.execute(
                "INSERT INTO memory(umo, layer, turn, ts, vclock, text, sig, s, con,"
                " va, ar, emo, tags, hits, last_hit, pinned)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,0)",
                (umo, layer, int(turn), now, float(vclock), text, sig,
                 float(s), 0.0, float(va), float(ar), str(emo)[:12], tag_s),
            )
            mem_id = int(cur.lastrowid)

            tf = terms(text, with_tf=True)
            self._conn.executemany(
                "INSERT OR REPLACE INTO mem_term(umo, term, mem_id, tf) VALUES(?,?,?,?)",
                [(umo, t, mem_id, n) for t, n in tf.items()],
            )
            if self.fts:
                self._conn.execute(
                    "INSERT INTO mem_fts(tokens, umo, mem_id) VALUES(?,?,?)",
                    (" ".join(sorted(tf.keys())), umo, mem_id),
                )
            self._conn.commit()
            return {"id": mem_id, "reinforced": False, "layer": layer}

    def touch(self, mem_id: int, *, hit: bool = True, s_gain: float = 0.0,
              con_gain: float = 0.0) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE memory SET hits=hits+?, s=MIN(2.0, s+?), con=MIN(1.0, con+?),"
                " last_hit=? WHERE id=?",
                (1 if hit else 0, float(s_gain), float(con_gain), time.time(), mem_id),
            )
            self._conn.commit()

    # ------------------------------------------------------------------
    # 读
    # ------------------------------------------------------------------
    def _rows(self, sql: str, args: Tuple = ()) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, args).fetchall()]

    def recent(self, umo: str, limit: int = 8, layer: Optional[str] = None,
               before_turn: Optional[int] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM memory WHERE umo=?"
        args: List[Any] = [umo]
        if layer:
            sql += " AND layer=?"
            args.append(layer)
        if before_turn is not None:
            sql += " AND turn<?"
            args.append(int(before_turn))
        sql += " ORDER BY vclock DESC, id DESC LIMIT ?"
        args.append(int(limit))
        return self._rows(sql, tuple(args))

    def by_layer(self, umo: str, layer: str, limit: int = 20) -> List[Dict[str, Any]]:
        return self._rows(
            "SELECT * FROM memory WHERE umo=? AND layer=? ORDER BY s DESC, vclock DESC LIMIT ?",
            (umo, layer, int(limit)),
        )

    def strongest(self, umo: str, limit: int = 6,
                  before_turn: Optional[int] = None,
                  layers: Tuple[str, ...] = ("short", "medium", "long"),
                  ) -> List[Dict[str, Any]]:
        ph = ",".join("?" for _ in layers)
        sql = f"SELECT * FROM memory WHERE umo=? AND layer IN ({ph})"
        args: List[Any] = [umo, *layers]
        if before_turn is not None:
            sql += " AND turn<?"
            args.append(int(before_turn))
        sql += " ORDER BY s DESC, vclock DESC LIMIT ?"
        args.append(int(limit))
        return self._rows(sql, tuple(args))

    def consolidated(self, umo: str) -> int:
        r = self._rows(
            "SELECT COUNT(*) AS n FROM memory WHERE umo=? AND "
            "(layer='long' OR (layer='medium' AND con>=0.5))", (umo,)
        )
        return int(r[0]["n"]) if r else 0

    def avg_strength(self, umo: str) -> float:
        r = self._rows("SELECT AVG(s) AS a FROM memory WHERE umo=?", (umo,))
        return float(r[0]["a"] or 0.0) if r else 0.0

    def turn_span(self, umo: str) -> Tuple[Optional[int], Optional[int]]:
        r = self._rows(
            "SELECT MIN(turn) AS lo, MAX(turn) AS hi FROM memory WHERE umo=?", (umo,)
        )
        if not r or r[0]["lo"] is None:
            return None, None
        return int(r[0]["lo"]), int(r[0]["hi"])

    def counts(self, umo: str) -> Dict[str, int]:
        out = {k: 0 for k in LAYERS}
        for r in self._rows(
            "SELECT layer, COUNT(*) AS n FROM memory WHERE umo=? GROUP BY layer", (umo,)
        ):
            if r["layer"] in out:
                out[r["layer"]] = int(r["n"])
        return out

    def total(self, umo: str) -> int:
        r = self._rows("SELECT COUNT(*) AS n FROM memory WHERE umo=?", (umo,))
        return int(r[0]["n"]) if r else 0

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------
    def _term_ids(self, umo: str, q: Any) -> Dict[int, float]:
        """按词取候选 id 与粗排分。FTS5 优先，不可用时退倒排表。"""
        ids: Dict[int, float] = {}
        terms_list = list(q or [])
        if not terms_list:
            return ids
        if self.fts:
            expr = " OR ".join(f'"{t}"' for t in sorted(terms_list)[:40])
            try:
                with self._lock:
                    rows = self._conn.execute(
                        "SELECT mem_id, bm25(mem_fts) AS r FROM mem_fts "
                        "WHERE mem_fts MATCH ? AND umo=? ORDER BY r LIMIT 400",
                        (expr, umo),
                    ).fetchall()
                for r in rows:
                    # bm25 越小越相关，取负号变成「越大越好」
                    ids[int(r["mem_id"])] = -float(r["r"])
            except Exception:
                ids = {}

        if not ids:
            # 兜底：倒排表。取命中词数 × tf 平方根
            marks = ",".join("?" for _ in terms_list)
            with self._lock:
                rows = self._conn.execute(
                    f"SELECT mem_id, COUNT(*) AS n, SUM(tf) AS tf FROM mem_term "
                    f"WHERE umo=? AND term IN ({marks}) GROUP BY mem_id "
                    f"ORDER BY n DESC, tf DESC LIMIT 400",
                    (umo, *sorted(terms_list)),
                ).fetchall()
            for r in rows:
                ids[int(r["mem_id"])] = float(r["n"]) + 0.3 * math.log1p(float(r["tf"]))
        return ids

    def search(self, umo: str, query: str, limit: int = 6, *,
               cur_va: float = 0.0, before_turn: Optional[int] = None,
               layers: Tuple[str, ...] = LAYERS,
               ) -> List[Tuple[Dict[str, Any], float]]:
        # 工作记忆也参与检索：上一轮说的话当然能被这句话勾起来。
        # 「本轮刚说的不算记得」由调用方用 before_turn 排除，不靠层级。
        q = terms(query)
        if not q and not query.strip():
            return []
        ids = self._term_ids(umo, q)

        # 字面召回不足时才用同义扩展，且分数打折：扩展是「可能相关」，
        # 不能顶掉「确实说过这个词」。
        if len(ids) < max(3, limit) :
            q2 = _syn_terms(query)
            if q2:
                for mid, sc in self._term_ids(umo, q2).items():
                    if mid not in ids:
                        ids[mid] = sc * 0.60

        if not ids:
            return []

        ph = ",".join("?" for _ in ids)
        sql = f"SELECT * FROM memory WHERE id IN ({ph}) AND umo=?"
        args: List[Any] = [*ids.keys(), umo]
        if before_turn is not None:
            sql += " AND turn<?"
            args.append(int(before_turn))
        placeholders = ",".join("?" for _ in layers)
        sql += f" AND layer IN ({placeholders})"
        args.extend(layers)

        rows = self._rows(sql, tuple(args))
        scored: List[Tuple[Dict[str, Any], float]] = []
        for r in rows:
            base = float(ids.get(int(r["id"]), 0.0))
            # 情绪一致性：同效价的记忆更容易被想起
            base *= 1.0 + 0.15 * (1.0 - abs(float(r["va"]) - cur_va) / 2.0)
            base *= 1.0 + 0.10 * LAYERS.index(r["layer"]) if r["layer"] in LAYERS else 1.0
            base *= min(1.6, max(0.2, float(r["s"])))
            if base > 0:
                scored.append((r, base))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    # ------------------------------------------------------------------
    # 时间演化：衰减 → 晋升 → 淘汰
    # ------------------------------------------------------------------
    def decay(self, umo: str, hours: float, *, cur_va: float = 0.0) -> int:
        """按经过小时衰减短期与较长期，返回被遗忘的条数。"""
        hours = max(0.0, float(hours))
        if hours <= 0:
            return 0
        gone = 0
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, layer, s, con, hits, va, vclock, ts FROM memory "
                "WHERE umo=? AND layer IN ('short','medium')", (umo,),
            ).fetchall()
            for r in rows:
                half = HALF_LIFE.get(r["layer"]) or 24.0
                # 巩固与命中都会拖慢衰减：反复想起的事不该和一次性的事一起淡掉
                half *= 1.0 + 1.5 * float(r["con"]) + 0.25 * float(r["hits"])
                s = float(r["s"]) * (0.5 ** (hours / half))
                if s < FORGET_AT:
                    self._forget(int(r["id"]))
                    gone += 1
                else:
                    self._conn.execute("UPDATE memory SET s=? WHERE id=?", (s, r["id"]))
            self._conn.commit()
        return gone

    def _forget(self, mem_id: int) -> None:
        self._conn.execute("DELETE FROM mem_term WHERE mem_id=?", (mem_id,))
        if self.fts:
            self._conn.execute("DELETE FROM mem_fts WHERE mem_id=?", (mem_id,))
        self._conn.execute("DELETE FROM memory WHERE id=?", (mem_id,))

    def promote(self, umo: str, *, now_vclock: float = 0.0) -> Dict[str, int]:
        """跑一遍晋升。返回每层升上去多少条。"""
        moved = {"instant": 0, "short": 0, "medium": 0}
        with self._lock:
            # 1) instant → short（被挤出工作记忆的那批）
            #
            # 不在这里删。工作记忆的含义是「此刻还在脑子里」，被挤出去的
            # 只是不在前台了，不等于忘掉——「我住在成都」这种话没有情绪，
            # 强度永远过不了门槛，按门槛删就等于永远记不住任何事实。
            # 所以一律下沉到短期，够不够格留到明天由 24 小时半衰期决定。
            # 太弱的给一次额外折扣，让它淡得更快。
            # 先取「挤出窗口」的那批下沉，**不能先 trim**：trim 会把它们
            # 直接删掉，短期层永远是空的，记忆一条都活不过瞬息。
            rows = self._conn.execute(
                "SELECT id, s, va FROM memory WHERE umo=? AND layer='instant' "
                "ORDER BY vclock DESC LIMIT -1 OFFSET ?", (umo, self.cap["instant"]),
            ).fetchall()
            for r in rows:
                weak = not (float(r["s"]) >= P_INSTANT
                            or abs(float(r["va"])) >= P_INSTANT_VA)
                self._set_layer(int(r["id"]), "short")
                if weak:
                    self._conn.execute(
                        "UPDATE memory SET s=s*0.7 WHERE id=?", (int(r["id"]),)
                    )
                moved["instant"] += 1
            self._trim(umo, "instant")

            # 2) short → medium
            rows = self._conn.execute(
                "SELECT id, hits, con, s, text FROM memory WHERE umo=? AND layer='short'",
                (umo,),
            ).fetchall()
            for r in rows:
                if int(r["hits"]) >= P_SHORT_HITS or float(r["con"]) >= P_SHORT_CON:
                    self._set_layer(int(r["id"]), "medium")
                    moved["short"] += 1
                elif is_milestone(r["text"]) and float(r["s"]) >= P_MEDIUM_S:
                    self._set_layer(int(r["id"]), "long", pinned=True)
                    moved["short"] += 1

            # 3) medium → long
            rows = self._conn.execute(
                "SELECT id, hits, s, text, vclock FROM memory WHERE umo=? AND layer='medium'",
                (umo,),
            ).fetchall()
            for r in rows:
                span = abs(now_vclock - float(r["vclock"])) if now_vclock else 0.0
                if is_milestone(r["text"]) and float(r["s"]) >= P_MEDIUM_S:
                    self._set_layer(int(r["id"]), "long", pinned=True)
                elif int(r["hits"]) >= P_MEDIUM_HITS and span >= P_MEDIUM_SPAN_H:
                    self._set_layer(int(r["id"]), "long", pinned=True)
                else:
                    continue
                moved["medium"] += 1

            self._conn.commit()
        return moved

    def _set_layer(self, mem_id: int, layer: str, pinned: bool = False) -> None:
        self._conn.execute(
            "UPDATE memory SET layer=?, pinned=? WHERE id=?",
            (layer, 1 if pinned else 0, mem_id),
        )

    def _trim(self, umo: str, layer: str) -> int:
        cap = int(self.cap.get(layer, 240))
        n = int(self._conn.execute(
            "SELECT COUNT(*) AS n FROM memory WHERE umo=? AND layer=?", (umo, layer)
        ).fetchone()["n"])
        if n <= cap:
            return 0

        if layer == "instant":
            # 工作记忆按时间淘汰，不看分数：刚说的话不需要「重要」才留下
            rows = self._conn.execute(
                "SELECT id FROM memory WHERE umo=? AND layer='instant' "
                "ORDER BY vclock DESC, id DESC LIMIT -1 OFFSET ?", (umo, cap),
            ).fetchall()
        else:
            # 长期层永不衰减，只按「被想起来过几次 + 强度」淘汰最弱的；
            # 短期/较长期同理，但会把最近的 8 条保护起来。
            keep = 8 if layer != "long" else 0
            rows = self._conn.execute(
                "SELECT id FROM memory WHERE umo=? AND layer=? "
                "ORDER BY (s * (1 + 2*con) + 0.15*hits) ASC LIMIT ?",
                (umo, layer, n - cap + keep),
            ).fetchall()
            if keep:
                rows = rows[: max(0, n - cap)]
        for r in rows:
            self._forget(int(r["id"]))
        return len(rows)

    def trim_all(self, umo: str) -> Dict[str, int]:
        with self._lock:
            out = {k: self._trim(umo, k) for k in LAYERS}
            self._conn.commit()
        return out

    # ------------------------------------------------------------------
    # 迁移与清理
    # ------------------------------------------------------------------
    def migrated(self, umo: str) -> bool:
        r = self._conn.execute(
            "SELECT migrated FROM mem_meta WHERE umo=?", (umo,)
        ).fetchone()
        return bool(r and int(r["migrated"]))

    def mark_migrated(self, umo: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO mem_meta(umo, migrated, updated) VALUES(?,1,?) "
                "ON CONFLICT(umo) DO UPDATE SET migrated=1, updated=excluded.updated",
                (umo, time.time()),
            )
            self._conn.commit()

    def migrate(self, umo: str, items: List[Dict[str, Any]]) -> int:
        """旧存档的 JSON 列表 → 表。按原强度与巩固度直接定层。"""
        n = 0
        for it in items or []:
            text = str(it.get("text") or "")[:TEXT_MAX]
            if len(text) < 3:
                continue
            s = float(it.get("s", 1.0))
            con = float(it.get("con", 0.0))
            if con >= 0.75 or (is_milestone(text) and s >= P_MEDIUM_S):
                layer = "long"
            elif con >= 0.3 or s >= P_INSTANT:
                layer = "medium"
            else:
                layer = "short"
            r = self.encode(
                umo, text, turn=int(it.get("turn", 0)),
                vclock=float(it.get("clock", 0.0)), s=s,
                va=float(it.get("va", 0.0)), ar=float(it.get("ar", 0.5)),
                tags=it.get("tags") or [], layer=layer,
            )
            if r and not r.get("reinforced"):
                if int(it.get("hits", 0)):
                    self._conn.execute(
                        "UPDATE memory SET hits=?, con=? WHERE id=?",
                        (int(it.get("hits", 0)), con, r["id"]),
                    )
                n += 1
        with self._lock:
            self._conn.commit()
        self.mark_migrated(umo)
        return n

    def clear(self, umo: str, layer: Optional[str] = None) -> int:
        with self._lock:
            if layer:
                ids = [int(r["id"]) for r in self._conn.execute(
                    "SELECT id FROM memory WHERE umo=? AND layer=?", (umo, layer)
                ).fetchall()]
            else:
                ids = [int(r["id"]) for r in self._conn.execute(
                    "SELECT id FROM memory WHERE umo=?", (umo,)
                ).fetchall()]
            for i in ids:
                self._forget(i)
            self._conn.commit()
        return len(ids)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
