"""持久化：SQLite。每个会话/用户一份状态，另有事件流水。

注意：数据必须放在 AstrBot 的 data 目录下（由 main.py 传入），
不能放在插件目录里，否则更新插件会被覆盖。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional


class Store:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init()

    def _init(self) -> None:
        with self._lock:
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS mind (
                    umo TEXT PRIMARY KEY,
                    preset TEXT,
                    data TEXT NOT NULL,
                    updated REAL NOT NULL
                )"""
            )
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS event (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    umo TEXT NOT NULL,
                    turn INTEGER,
                    kind TEXT,
                    payload TEXT,
                    ts REAL
                )"""
            )
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_event_umo ON event(umo, id)")
            self._conn.commit()

    # ------------------------------------------------------------------
    def load(self, umo: str) -> Optional[str]:
        with self._lock:
            cur = self._conn.execute("SELECT data FROM mind WHERE umo=?", (umo,))
            row = cur.fetchone()
            return row[0] if row else None

    def save(self, umo: str, data: str, preset: str = "") -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO mind(umo, preset, data, updated) VALUES(?,?,?,?) "
                "ON CONFLICT(umo) DO UPDATE SET data=excluded.data, preset=excluded.preset, updated=excluded.updated",
                (umo, preset, data, time.time()),
            )
            self._conn.commit()

    def log(self, umo: str, turn: int, kind: str, payload: Any) -> None:
        try:
            body = json.dumps(payload, ensure_ascii=False)[:4000]
        except Exception:
            body = str(payload)[:4000]
        with self._lock:
            self._conn.execute(
                "INSERT INTO event(umo, turn, kind, payload, ts) VALUES(?,?,?,?,?)",
                (umo, turn, kind, body, time.time()),
            )
            self._conn.commit()

    def events(self, umo: str, limit: int = 30) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT turn, kind, payload, ts FROM event WHERE umo=? ORDER BY id DESC LIMIT ?",
                (umo, limit),
            )
            rows = cur.fetchall()
        out = []
        for turn, kind, payload, ts in reversed(rows):
            try:
                body = json.loads(payload)
            except Exception:
                body = payload
            out.append({"turn": turn, "kind": kind, "payload": body, "ts": ts})
        return out

    def delete(self, umo: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM mind WHERE umo=?", (umo,))
            self._conn.execute("DELETE FROM event WHERE umo=?", (umo,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
