"""四层记忆库的自测：建表、索引、晋升、淘汰、迁移。

跑法：
    python tests/test_memdb.py

测的是「机制对不对」，不是「参数好不好」：表与索引建了没有、同一句话
会不会被存两遍、检索能不能中中文、瞬时会不会真的沉到短期、里程碑会不会
直达长期、超限时删的是不是最弱的、旧 JSON 能不能搬进来。
具体容量与半衰期都会调，所以这里只在跨过阈值时断言趋势。
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from psyche import memdb as M  # noqa: E402

PASS = 0


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"[ok] {msg}")


def fail(msg: str) -> None:
    raise AssertionError(msg)


def new_db(**cfg):
    path = os.path.join(tempfile.mkdtemp(), "mem.db")
    return M.MemDB(path, cfg), path


# ----------------------------------------------------------------------
def test_schema() -> None:
    db, path = new_db()
    con = sqlite3.connect(path)
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    idx = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index'")}
    for need in ("memory", "mem_term", "mem_meta"):
        if need not in tables:
            fail(f"缺表 {need}")
    for need in ("idx_m_umo_layer", "idx_m_umo_ts", "idx_t_term"):
        if need not in idx:
            fail(f"缺索引 {need}")
    if not db.fts:
        fail("FTS5 不可用（这台机器该有，没有的话检索会退化到倒排表）")
    if "mem_fts" not in tables:
        fail("FTS5 表没建")
    con.close()
    ok(f"建表建索引齐备（memory / mem_term / mem_meta / mem_fts，"
       f"{len(idx)} 个索引，FTS5 {db.fts}）")


def test_encode_and_dedup() -> None:
    db, _ = new_db()
    a = db.encode("u", "我妈妈上周查出来肺上有阴影", turn=1, vclock=1.0, s=0.8)
    b = db.encode("u", "我妈妈上周查出来肺上有阴影", turn=2, vclock=2.0, s=0.8)
    c = db.encode("u", "我", turn=2, vclock=2.0)
    if not a or a.get("reinforced"):
        fail("第一次编码没写进去")
    if not b or not b.get("reinforced"):
        fail("同一句话没有被识别为复述")
    if c:
        fail("太短的片段不该编码")
    n = db.total("u")
    if n != 1:
        fail(f"复述被存成了 {n} 条")
    row = db.recent("u", 1)[0]
    if int(row["hits"]) != 1:
        fail("复述没有累加命中数")
    ok("编码与去重：同一句话只存一条，命中最强加固，碎句不记")


def test_search_cjk() -> None:
    db, _ = new_db()
    db.encode("u", "主管今天当众骂我，说我不配做这份工作", turn=1, vclock=1.0, s=0.9)
    db.encode("u", "晚上回去煮了碗面，加了两个蛋", turn=2, vclock=2.0, s=0.4)
    db.encode("u", "周末想去爬山但天气预报说有雨", turn=3, vclock=3.0, s=0.4)

    hits = db.search("u", "主管", limit=5)
    if not hits:
        fail("中文检索没命中「主管」")
    if "主管" not in str(hits[0][0]["text"]):
        fail(f"命中了错的那条：{hits[0][0]['text'][:30]}")

    none = db.search("u", "核聚变", limit=5)
    if none:
        fail("无关词居然命中了")
    ok(f"中文 2-gram 检索命中（「主管」→ {len(hits)} 条），无关词不误召")


def test_layer_promotion() -> None:
    """瞬时 → 短期 → 较长期 → 长期，每层都要真的能流过去。"""
    db, _ = new_db()
    db.cap["instant"] = 2
    for i in range(6):
        db.encode("u", f"第{i}句话说的是不同的事情", turn=i, vclock=float(i), s=0.6)
    moved = db.promote("u", now_vclock=10.0)
    if db.counts("u")["short"] < 3:
        fail(f"瞬时没有下沉：{db.counts('u')}")
    if moved["instant"] < 3:
        fail(f"晋升计数不对：{moved}")

    # 短期 → 较长期：命中两次或巩固到 0.45
    for row in db.by_layer("u", "short", 10):
        db.touch(int(row["id"]), hit=True, con_gain=0.5)
    db.promote("u", now_vclock=20.0)
    if db.counts("u")["medium"] < 3:
        fail(f"短期没有升到较长期：{db.counts('u')}")

    # 较长期 → 长期：命中 5 次且跨度 30 天。
    # 前面 promote 前的固结算第 1 次命中，这里再补 4 次。
    for row in db.by_layer("u", "medium", 10):
        for _ in range(4):
            db.touch(int(row["id"]), hit=True, con_gain=0.02)
    db.promote("u", now_vclock=24.0 * 40)
    if db.counts("u")["long"] < 1:
        fail(f"较长期没有升到长期：{db.counts('u')}")
    ok(f"四层晋升链打通：{db.counts('u')}")


def test_milestone_shortcut() -> None:
    """不可逆的节点一次就进长期；普通节点进短期。"""
    db, _ = new_db()
    core = db.encode("u", "我爸爸上个月去世了", turn=1, vclock=1.0, s=0.9, layer="long")
    soft = db.encode("u", "我下个月要搬家", turn=2, vclock=2.0, s=0.6, layer="short")
    if not core or not soft:
        fail("里程碑没写进去")
    if not M.is_milestone_core("我爸爸上个月去世了"):
        fail("核心节点词表没认出来")
    if M.is_milestone_core("我下个月要搬家"):
        fail("搬家不该算不可逆节点")
    if M.is_milestone("我下个月要搬家") is False:
        fail("搬家应该算普通人生节点")
    ok("里程碑分级：丧亲/手术直达长期，搬家/入职只进短期")


def test_long_cap_eviction() -> None:
    """长期层超限时淘汰最弱的那批，不是最新的。"""
    db, _ = new_db()
    db.cap["long"] = 5
    for i in range(9):
        r = db.encode("u", f"第{i}件很久以前的事，依然记得", turn=i,
                      vclock=float(i), s=0.4 + 0.1 * i, layer="long")
        if r:
            db.touch(int(r["id"]), hit=False, s_gain=0.0)
            db._conn.execute("UPDATE memory SET hits=? WHERE id=?",
                             (i, int(r["id"])))
    db.trim_all("u")
    rows = db.by_layer("u", "long", 50)
    if len(rows) > 5:
        fail(f"长期层没截到上限：{len(rows)}")
    texts = [r["text"] for r in rows]
    if any("第0件" in t for t in texts):
        fail("最弱最旧的那条没被淘汰")
    if not any("第8件" in t for t in texts):
        fail("最强的那条被误删")
    ok(f"长期层硬上限生效（5 条），淘汰最弱、保住最强")


def test_forget_and_long_immunity() -> None:
    db, _ = new_db()
    weak = db.encode("u", "几乎没留下印象的一句", turn=1, vclock=0.0, s=0.07, layer="short")
    deep = db.encode("u", "这辈子都忘不掉的", turn=1, vclock=0.0, s=0.5, layer="long")
    db.decay("u", 48.0)
    ids = {int(r["id"]) for r in db._rows("SELECT id FROM memory WHERE umo='u'")}
    if int(weak["id"]) in ids:
        fail("弱记忆没被忘掉")
    for _ in range(30):
        db.decay("u", 240.0)
    ids = {int(r["id"]) for r in db._rows("SELECT id FROM memory WHERE umo='u'")}
    if int(deep["id"]) not in ids:
        fail("长期层被衰减掉了")
    ok("遗忘按强度生效，长期层不参与衰减（两年后仍在）")


def test_umo_isolation() -> None:
    db, _ = new_db()
    db.encode("a", "A 的秘密是喜欢下雨天", turn=1, vclock=1.0, s=0.8)
    db.encode("b", "B 的秘密是怕黑", turn=1, vclock=1.0, s=0.8)
    a = db.search("a", "秘密", limit=5)
    b = db.search("b", "秘密", limit=5)
    if len(a) != 1 or len(b) != 1:
        fail(f"会话隔离失败：{len(a)} / {len(b)}")
    if "A" not in a[0][0]["text"] or "B" not in b[0][0]["text"]:
        fail("检索串到别的会话去了")
    ok("多会话按 umo 隔离（同一张表，互不串味）")


def test_migrate_legacy() -> None:
    """旧存档的 JSON 列表要能整批搬进表，并按巩固度定层。"""
    db, _ = new_db()
    legacy = [
        {"text": "爸爸住院那次我在走廊坐了一夜", "turn": 3, "clock": 18.0,
         "va": -0.7, "ar": 0.8, "tags": ["丧失"], "s": 1.5, "hits": 2, "con": 0.9},
        {"text": "那天中午吃了碗面", "turn": 4, "clock": 24.0,
         "va": 0.1, "ar": 0.4, "tags": [], "s": 1.0, "hits": 0, "con": 0.05},
        {"text": "养了只猫叫豆豆", "turn": 5, "clock": 30.0,
         "va": 0.4, "ar": 0.5, "tags": [], "s": 1.2, "hits": 0, "con": 0.35},
    ]
    n = db.migrate("u", legacy)
    if n != 3:
        fail(f"迁移条数不对：{n}")
    counts = db.counts("u")
    if counts["long"] < 1:
        fail(f"巩固 0.9 的旧记忆没有进长期：{counts}")
    if not db.migrated("u"):
        fail("迁移标记没写")
    hits = db.search("u", "走廊", limit=3)
    if not hits:
        fail("迁移进来的内容检索不到")
    ok(f"旧 JSON 迁移：{n} 条按巩固度定层 {counts}，且可检索")


def test_clear_by_layer() -> None:
    db, _ = new_db()
    db.encode("u", "长期的一条", turn=1, vclock=1.0, s=0.8, layer="long")
    db.encode("u", "短期的一条", turn=2, vclock=2.0, s=0.5, layer="short")
    n = db.clear("u", "short")
    if n != 1:
        fail(f"按层清理条数不对：{n}")
    if db.counts("u")["long"] != 1:
        fail("清短期把长期也清了")
    if db.total("u") != 1:
        fail("清完之后还有残留")
    ok("按层清理只动指定层")


def main() -> int:
    print("── 四层记忆库自测 ──")
    test_schema()
    test_encode_and_dedup()
    test_search_cjk()
    test_layer_promotion()
    test_milestone_shortcut()
    test_long_cap_eviction()
    test_forget_and_long_immunity()
    test_umo_isolation()
    test_migrate_legacy()
    test_clear_by_layer()
    print(f"\n全部通过（{PASS} 项）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
