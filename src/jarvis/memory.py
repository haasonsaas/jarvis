from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

MAX_QUERY_LIMIT = 200
MAX_SEARCH_FANOUT = 800


@dataclass
class MemoryEntry:
    id: int
    created_at: float
    kind: str
    text: str
    tags: list[str]
    importance: float
    sensitivity: float
    source: str
    score: float = 0.0


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


@dataclass
class MemorySummary:
    topic: str
    summary: str
    updated_at: float


class MemoryStore:
    def __init__(self, path: str) -> None:
        if path not in {":memory:", ""}:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._closed = False
        self._configure_connection()
        self._fts_enabled = False
        self._memory_enabled = False
        self._last_warm = None
        self._last_sync = None
        self._last_optimize = None
        self._last_vacuum = None
        self._init_schema()

    def _configure_connection(self) -> None:
        cur = self._conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.execute("PRAGMA busy_timeout=5000;")
        self._conn.commit()

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
                sensitivity REAL NOT NULL DEFAULT 0.0,
                source TEXT NOT NULL
            );
            """
        )
        self._ensure_column(cur, "memory", "sensitivity", "REAL NOT NULL DEFAULT 0.0")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_created_at ON memory(created_at DESC);")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
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
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_summaries (
                topic TEXT PRIMARY KEY,
                summary TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_summaries_updated ON memory_summaries(updated_at DESC);")
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
        try:
            cur.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING fts5(
                    text,
                    content='memory',
                    content_rowid='id'
                );
                """
            )
            self._memory_enabled = True
        except sqlite3.OperationalError:
            self._memory_enabled = False
        self._conn.commit()

    def add_memory(
        self,
        text: str,
        *,
        kind: str = "note",
        tags: list[str] | None = None,
        importance: float = 0.5,
        sensitivity: float = 0.0,
        source: str = "user",
    ) -> int:
        clean = text.strip()
        if not clean:
            raise ValueError("memory text required")
        payload = json.dumps(tags or [])
        created_at = time.time()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO memory(created_at, kind, text, tags, importance, sensitivity, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (created_at, kind, clean, payload, float(importance), float(sensitivity), source),
        )
        memory_id = int(cur.lastrowid)
        if self._fts_enabled:
            cur.execute("INSERT INTO memory_fts(rowid, text) VALUES (?, ?)", (memory_id, clean))
        if self._memory_enabled:
            cur.execute("INSERT INTO memory_vec(rowid, text) VALUES (?, ?)", (memory_id, clean))
        self._conn.commit()
        return memory_id

    def warm(self) -> None:
        self._last_warm = time.time()

    def sync(self) -> None:
        self._last_sync = time.time()

    def search_v2(
        self,
        query: str,
        *,
        limit: int = 5,
        max_sensitivity: float | None = None,
        hybrid_weight: float = 0.7,
        decay_enabled: bool = False,
        decay_half_life_days: float = 30.0,
        mmr_enabled: bool = False,
        mmr_lambda: float = 0.7,
        sources: list[str] | None = None,
    ) -> list[MemoryEntry]:
        cleaned = query.strip()
        if not cleaned:
            return []
        limit = max(1, min(MAX_QUERY_LIMIT, int(limit)))
        sensitivity_clause, sensitivity_params = self._sensitivity_filter(max_sensitivity)
        keyword_rows = self._search_keyword(
            cleaned,
            min(MAX_SEARCH_FANOUT, limit * 4),
            sensitivity_clause,
            sensitivity_params,
            sources,
        )
        if not keyword_rows:
            return []
        entries = [self._row_to_memory(row) for row in keyword_rows]
        entries = self._apply_hybrid_scoring(entries, cleaned, hybrid_weight)
        if decay_enabled:
            entries = self._apply_temporal_decay(entries, decay_half_life_days)
        if mmr_enabled:
            entries = self._apply_mmr(entries, mmr_lambda)
        return sorted(entries, key=lambda e: e.score, reverse=True)[:limit]

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        max_sensitivity: float | None = None,
    ) -> list[MemoryEntry]:
        cleaned = query.strip()
        if not cleaned:
            return []
        limit = max(1, min(MAX_QUERY_LIMIT, int(limit)))
        cur = self._conn.cursor()
        sensitivity_clause, sensitivity_params = self._sensitivity_filter(max_sensitivity)
        if self._fts_enabled:
            fts_query = self._build_fts_query(cleaned)
            if not fts_query:
                return []
            sql = (
                "SELECT memory.* FROM memory_fts "
                "JOIN memory ON memory_fts.rowid = memory.id "
                "WHERE memory_fts MATCH ? "
                f"{sensitivity_clause} "
                "ORDER BY bm25(memory_fts) ASC "
                "LIMIT ?"
            )
            rows = cur.execute(sql, (fts_query, *sensitivity_params, limit)).fetchall()
        else:
            like = f"%{cleaned}%"
            sql = (
                "SELECT * FROM memory WHERE text LIKE ? "
                f"{sensitivity_clause} "
                "ORDER BY created_at DESC LIMIT ?"
            )
            rows = cur.execute(sql, (like, *sensitivity_params, limit)).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def recent(self, *, limit: int = 5, kind: str | None = None, sources: list[str] | None = None) -> list[MemoryEntry]:
        limit = max(1, min(MAX_QUERY_LIMIT, int(limit)))
        cur = self._conn.cursor()
        source_clause, source_params = self._source_filter(sources)
        if kind:
            sql = (
                "SELECT * FROM memory WHERE kind = ? "
                f"{source_clause} "
                "ORDER BY created_at DESC LIMIT ?"
            )
            rows = cur.execute(sql, (kind, *source_params, limit)).fetchall()
        else:
            sql = f"SELECT * FROM memory WHERE 1=1 {source_clause} ORDER BY created_at DESC LIMIT ?"
            rows = cur.execute(sql, (*source_params, limit)).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def add_task_plan(self, title: str, steps: list[str]) -> int:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("title required")
        clean_steps = [step.strip() for step in steps if step.strip()]
        if not clean_steps:
            raise ValueError("steps required")
        created_at = time.time()
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO task_plans(created_at, title, status) VALUES (?, ?, ?)",
            (created_at, clean_title, "open"),
        )
        plan_id = int(cur.lastrowid)
        for idx, clean_step in enumerate(clean_steps):
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

    def task_plan_progress(self, plan_id: int) -> tuple[int, int] | None:
        cur = self._conn.cursor()
        total = cur.execute(
            "SELECT COUNT(*) AS total FROM task_steps WHERE plan_id = ?",
            (plan_id,),
        ).fetchone()
        if not total or total["total"] == 0:
            return None
        done = cur.execute(
            "SELECT COUNT(*) AS done FROM task_steps WHERE plan_id = ? AND status = 'done'",
            (plan_id,),
        ).fetchone()
        return int(done["done"]), int(total["total"])

    def update_task_step(self, plan_id: int, step_index: int, status: str) -> bool:
        allowed_statuses = {"pending", "in_progress", "blocked", "done"}
        if status not in allowed_statuses:
            raise ValueError(f"invalid step status: {status}")
        cur = self._conn.cursor()
        cur.execute(
            "UPDATE task_steps SET status = ? WHERE plan_id = ? AND idx = ?",
            (status, plan_id, step_index),
        )
        updated = cur.rowcount > 0
        steps = cur.execute(
            "SELECT status FROM task_steps WHERE plan_id = ?",
            (plan_id,),
        ).fetchall()
        if steps and all(row["status"] == "done" for row in steps):
            cur.execute(
                "UPDATE task_plans SET status = 'closed' WHERE id = ?",
                (plan_id,),
            )
        elif steps and any(row["status"] != "done" for row in steps):
            cur.execute(
                "UPDATE task_plans SET status = 'open' WHERE id = ?",
                (plan_id,),
            )
        self._conn.commit()
        return updated

    def next_task_step(self, plan_id: int | None = None) -> tuple[TaskPlan, TaskStep] | None:
        cur = self._conn.cursor()
        if plan_id is None:
            plan_row = cur.execute(
                "SELECT * FROM task_plans WHERE status != 'closed' ORDER BY created_at DESC LIMIT 1",
            ).fetchone()
        else:
            plan_row = cur.execute(
                "SELECT * FROM task_plans WHERE id = ?",
                (plan_id,),
            ).fetchone()
        if not plan_row:
            return None
        step_row = cur.execute(
            """
            SELECT idx, text, status FROM task_steps
            WHERE plan_id = ? AND status != 'done'
            ORDER BY idx LIMIT 1
            """,
            (plan_row["id"],),
        ).fetchone()
        if not step_row:
            return None
        plan = TaskPlan(
            id=int(plan_row["id"]),
            created_at=float(plan_row["created_at"]),
            title=str(plan_row["title"]),
            status=str(plan_row["status"]),
            steps=[],
        )
        step = TaskStep(index=int(step_row["idx"]), text=str(step_row["text"]), status=str(step_row["status"]))
        return plan, step

    def upsert_summary(self, topic: str, summary: str) -> None:
        clean_topic = topic.strip().lower()
        clean_summary = summary.strip()
        if not clean_topic or not clean_summary:
            raise ValueError("topic and summary required")
        updated_at = time.time()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO memory_summaries(topic, summary, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(topic) DO UPDATE SET summary = excluded.summary, updated_at = excluded.updated_at
            """,
            (clean_topic, clean_summary, updated_at),
        )
        self._conn.commit()

    def list_summaries(self, *, limit: int = 5) -> list[MemorySummary]:
        limit = max(1, min(MAX_QUERY_LIMIT, int(limit)))
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT * FROM memory_summaries ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            MemorySummary(topic=str(row["topic"]), summary=str(row["summary"]), updated_at=float(row["updated_at"]))
            for row in rows
        ]

    def get_summary(self, topic: str) -> MemorySummary | None:
        clean_topic = topic.strip().lower()
        if not clean_topic:
            return None
        row = self._conn.cursor().execute(
            "SELECT * FROM memory_summaries WHERE topic = ? LIMIT 1",
            (clean_topic,),
        ).fetchone()
        if not row:
            return None
        return MemorySummary(
            topic=str(row["topic"]),
            summary=str(row["summary"]),
            updated_at=float(row["updated_at"]),
        )

    def close(self) -> None:
        if self._closed:
            return
        self._conn.close()
        self._closed = True

    def memory_status(self) -> dict[str, Any]:
        cur = self._conn.cursor()
        count = cur.execute("SELECT COUNT(*) as c FROM memory").fetchone()["c"]
        sources = cur.execute("SELECT source, COUNT(*) as c FROM memory GROUP BY source").fetchall()
        source_counts = {str(row["source"]): int(row["c"]) for row in sources}
        return {
            "entries": int(count),
            "fts": self._fts_enabled,
            "vector": self._memory_enabled,
            "sources": source_counts,
            "last_warm": self._last_warm,
            "last_sync": self._last_sync,
            "last_optimize": self._last_optimize,
            "last_vacuum": self._last_vacuum,
        }

    def optimize(self) -> None:
        self._conn.execute("ANALYZE;")
        self._conn.execute("PRAGMA optimize;")
        self._conn.commit()
        self._last_optimize = time.time()

    def vacuum(self) -> None:
        self._conn.execute("VACUUM;")
        self._conn.commit()
        self._last_vacuum = time.time()

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryEntry:
        tags: list[str]
        if not row["tags"]:
            tags = []
        else:
            try:
                parsed = json.loads(row["tags"])
            except (TypeError, ValueError):
                parsed = []
            if isinstance(parsed, list):
                tags = [str(tag) for tag in parsed if str(tag).strip()]
            else:
                tags = []
        return MemoryEntry(
            id=int(row["id"]),
            created_at=float(row["created_at"]),
            kind=str(row["kind"]),
            text=str(row["text"]),
            tags=tags,
            importance=float(row["importance"]),
            sensitivity=float(row["sensitivity"]),
            source=str(row["source"]),
        )

    def _build_fts_query(self, text: str) -> str:
        tokens = re.findall(r"\w+", text.lower())
        return " OR ".join(tokens[:12])

    def _extract_keywords(self, text: str) -> list[str]:
        tokens = re.findall(r"\w+", text.lower())
        stop = {
            "a",
            "an",
            "the",
            "this",
            "that",
            "these",
            "those",
            "i",
            "me",
            "my",
            "we",
            "our",
            "you",
            "your",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "can",
            "may",
            "might",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "about",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "over",
            "and",
            "or",
            "but",
            "if",
            "then",
            "because",
            "as",
            "while",
            "when",
            "where",
            "what",
            "which",
            "who",
            "how",
            "why",
            "please",
            "help",
            "find",
            "show",
            "get",
            "tell",
            "give",
        }
        keywords: list[str] = []
        seen = set()
        for token in tokens:
            if token in stop or len(token) < 3:
                continue
            if token not in seen:
                seen.add(token)
                keywords.append(token)
        return keywords

    def _search_keyword(
        self,
        query: str,
        limit: int,
        sensitivity_clause: str,
        sensitivity_params: list[float],
        sources: list[str] | None,
    ) -> list[sqlite3.Row]:
        source_clause, source_params = self._source_filter(sources)
        if self._fts_enabled:
            keywords = self._extract_keywords(query)
            fts_query = self._build_fts_query(query)
            expanded = " OR ".join([fts_query, *keywords]) if keywords else fts_query
            if not expanded:
                return []
            sql = (
                "SELECT memory.* FROM memory_fts "
                "JOIN memory ON memory_fts.rowid = memory.id "
                "WHERE memory_fts MATCH ? "
                f"{sensitivity_clause} {source_clause} "
                "ORDER BY bm25(memory_fts) ASC "
                "LIMIT ?"
            )
            return self._conn.cursor().execute(
                sql,
                (expanded, *sensitivity_params, *source_params, limit),
            ).fetchall()
        like = f"%{query}%"
        sql = (
            "SELECT * FROM memory WHERE text LIKE ? "
            f"{sensitivity_clause} {source_clause} "
            "ORDER BY created_at DESC LIMIT ?"
        )
        return self._conn.cursor().execute(sql, (like, *sensitivity_params, *source_params, limit)).fetchall()

    def _apply_hybrid_scoring(self, entries: list[MemoryEntry], query: str, weight: float) -> list[MemoryEntry]:
        tokens = set(re.findall(r"\w+", query.lower()))
        for entry in entries:
            entry_tokens = set(re.findall(r"\w+", entry.text.lower()))
            overlap = len(tokens & entry_tokens)
            text_score = overlap / max(1, len(tokens))
            entry.score = (weight * entry.importance) + ((1 - weight) * text_score)
        return entries

    def _apply_temporal_decay(self, entries: list[MemoryEntry], half_life_days: float) -> list[MemoryEntry]:
        if half_life_days <= 0:
            return entries
        decay_lambda = 0.69314718056 / half_life_days
        now = time.time()
        for entry in entries:
            age_days = max(0.0, (now - entry.created_at) / 86400.0)
            multiplier = pow(2.0, -(age_days / half_life_days)) if decay_lambda > 0 else 1.0
            entry.score *= multiplier
        return entries

    def _apply_mmr(self, entries: list[MemoryEntry], lambda_weight: float) -> list[MemoryEntry]:
        if not entries:
            return entries
        lambda_weight = max(0.0, min(1.0, lambda_weight))
        selected: list[MemoryEntry] = []
        remaining = entries[:]
        max_score = max(e.score for e in remaining) or 1.0
        min_score = min(e.score for e in remaining)
        range_score = max_score - min_score

        def normalize(score: float) -> float:
            if range_score == 0:
                return 1.0
            return (score - min_score) / range_score

        while remaining:
            best = None
            best_score = -1e9
            for entry in remaining:
                relevance = normalize(entry.score)
                max_sim = 0.0
                entry_tokens = set(re.findall(r"\w+", entry.text.lower()))
                for chosen in selected:
                    chosen_tokens = set(re.findall(r"\w+", chosen.text.lower()))
                    intersection = len(entry_tokens & chosen_tokens)
                    union = len(entry_tokens | chosen_tokens)
                    sim = intersection / union if union else 0.0
                    if sim > max_sim:
                        max_sim = sim
                mmr_score = (lambda_weight * relevance) - ((1 - lambda_weight) * max_sim)
                if mmr_score > best_score:
                    best_score = mmr_score
                    best = entry
            if best is None:
                break
            selected.append(best)
            remaining.remove(best)
        return selected

    def _source_filter(self, sources: list[str] | None) -> tuple[str, list[str]]:
        if not sources:
            return "", []
        cleaned = [source.strip() for source in sources if source and source.strip()]
        if not cleaned:
            return "", []
        placeholders = ",".join(["?"] * len(cleaned))
        return f"AND source IN ({placeholders})", cleaned

    def _sensitivity_filter(self, max_sensitivity: float | None) -> tuple[str, list[float]]:
        if max_sensitivity is None:
            return "", []
        return "AND sensitivity <= ?", [float(max_sensitivity)]

    def _ensure_column(self, cur: sqlite3.Cursor, table: str, column: str, ddl: str) -> None:
        info = cur.execute(f"PRAGMA table_info({table})").fetchall()
        columns = {row["name"] for row in info}
        if column not in columns:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
