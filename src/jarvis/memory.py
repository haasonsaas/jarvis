from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class MemoryEntry:
    id: int
    created_at: float
    kind: str
    text: str
    tags: list[str]
    importance: float
    source: str


@dataclass
class TaskStep:
    index: int
    text: str
    status: str


@dataclass
class TaskPlan:
    id: int
    created_at: float
    title: str
    status: str
    steps: list[TaskStep]


class MemoryStore:
    def __init__(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True) if path not in {":memory:", ""} else None
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._fts_enabled = False
        self._init_schema()

    def _init_schema(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                tags TEXT NOT NULL,
                importance REAL NOT NULL,
                source TEXT NOT NULL
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_created_at ON memory(created_at DESC);")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS task_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                title TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS task_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                idx INTEGER NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL,
                FOREIGN KEY(plan_id) REFERENCES task_plans(id)
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_task_steps_plan ON task_steps(plan_id, idx);")
        try:
            cur.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                    text,
                    content='memory',
                    content_rowid='id'
                );
                """
            )
            self._fts_enabled = True
        except sqlite3.OperationalError:
            self._fts_enabled = False
        self._conn.commit()

    def add_memory(
        self,
        text: str,
        *,
        kind: str = "note",
        tags: list[str] | None = None,
        importance: float = 0.5,
        source: str = "user",
    ) -> int:
        clean = text.strip()
        if not clean:
            raise ValueError("memory text required")
        payload = json.dumps(tags or [])
        created_at = time.time()
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO memory(created_at, kind, text, tags, importance, source) VALUES (?, ?, ?, ?, ?, ?)",
            (created_at, kind, clean, payload, float(importance), source),
        )
        memory_id = int(cur.lastrowid)
        if self._fts_enabled:
            cur.execute("INSERT INTO memory_fts(rowid, text) VALUES (?, ?)", (memory_id, clean))
        self._conn.commit()
        return memory_id

    def search(self, query: str, *, limit: int = 5) -> list[MemoryEntry]:
        cleaned = query.strip()
        if not cleaned:
            return []
        cur = self._conn.cursor()
        if self._fts_enabled:
            fts_query = self._build_fts_query(cleaned)
            if not fts_query:
                return []
            rows = cur.execute(
                """
                SELECT memory.* FROM memory_fts
                JOIN memory ON memory_fts.rowid = memory.id
                WHERE memory_fts MATCH ?
                ORDER BY bm25(memory_fts) ASC
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        else:
            like = f"%{cleaned}%"
            rows = cur.execute(
                "SELECT * FROM memory WHERE text LIKE ? ORDER BY created_at DESC LIMIT ?",
                (like, limit),
            ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def recent(self, *, limit: int = 5, kind: str | None = None) -> list[MemoryEntry]:
        cur = self._conn.cursor()
        if kind:
            rows = cur.execute(
                "SELECT * FROM memory WHERE kind = ? ORDER BY created_at DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        else:
            rows = cur.execute(
                "SELECT * FROM memory ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def add_task_plan(self, title: str, steps: list[str]) -> int:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("title required")
        if not steps:
            raise ValueError("steps required")
        created_at = time.time()
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO task_plans(created_at, title, status) VALUES (?, ?, ?)",
            (created_at, clean_title, "open"),
        )
        plan_id = int(cur.lastrowid)
        for idx, step in enumerate(steps):
            clean_step = step.strip()
            if not clean_step:
                continue
            cur.execute(
                "INSERT INTO task_steps(plan_id, idx, text, status) VALUES (?, ?, ?, ?)",
                (plan_id, idx, clean_step, "pending"),
            )
        self._conn.commit()
        return plan_id

    def list_task_plans(self, *, open_only: bool = True) -> list[TaskPlan]:
        cur = self._conn.cursor()
        if open_only:
            plans = cur.execute(
                "SELECT * FROM task_plans WHERE status != 'closed' ORDER BY created_at DESC",
            ).fetchall()
        else:
            plans = cur.execute(
                "SELECT * FROM task_plans ORDER BY created_at DESC",
            ).fetchall()
        results: list[TaskPlan] = []
        for plan in plans:
            steps = cur.execute(
                "SELECT idx, text, status FROM task_steps WHERE plan_id = ? ORDER BY idx",
                (plan["id"],),
            ).fetchall()
            results.append(
                TaskPlan(
                    id=int(plan["id"]),
                    created_at=float(plan["created_at"]),
                    title=str(plan["title"]),
                    status=str(plan["status"]),
                    steps=[TaskStep(index=int(s["idx"]), text=str(s["text"]), status=str(s["status"])) for s in steps],
                )
            )
        return results

    def update_task_step(self, plan_id: int, step_index: int, status: str) -> None:
        cur = self._conn.cursor()
        cur.execute(
            "UPDATE task_steps SET status = ? WHERE plan_id = ? AND idx = ?",
            (status, plan_id, step_index),
        )
        steps = cur.execute(
            "SELECT status FROM task_steps WHERE plan_id = ?",
            (plan_id,),
        ).fetchall()
        if steps and all(row["status"] == "done" for row in steps):
            cur.execute(
                "UPDATE task_plans SET status = 'closed' WHERE id = ?",
                (plan_id,),
            )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryEntry:
        tags = json.loads(row["tags"]) if row["tags"] else []
        return MemoryEntry(
            id=int(row["id"]),
            created_at=float(row["created_at"]),
            kind=str(row["kind"]),
            text=str(row["text"]),
            tags=tags,
            importance=float(row["importance"]),
            source=str(row["source"]),
        )

    def _build_fts_query(self, text: str) -> str:
        tokens = re.findall(r"\w+", text.lower())
        return " OR ".join(tokens[:12])
