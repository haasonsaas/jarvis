from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import time
import base64
import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # pragma: no cover - runtime fallback
    Fernet = None  # type: ignore[assignment]
    InvalidToken = Exception  # type: ignore[assignment]

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - optional dependency
    OpenAI = None  # type: ignore[assignment]

MAX_QUERY_LIMIT = 200
MAX_SEARCH_FANOUT = 800
MAX_CANDIDATE_ANALYSIS_FANOUT = 400
DEFAULT_SEARCH_CANDIDATE_MULTIPLIER = 4
DEFAULT_RECENCY_PRIOR_HALF_LIFE_DAYS = 45.0

_STOP_WORDS = {
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
    "yesterday",
    "today",
    "tomorrow",
    "earlier",
    "later",
    "recently",
    "now",
    "thing",
    "things",
    "stuff",
}

_TOKEN_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "prefs": ("preference", "preferences"),
    "pref": ("preference",),
    "todo": ("task", "tasks"),
    "todos": ("task", "tasks"),
    "appt": ("appointment", "calendar"),
    "tv": ("television",),
    "msg": ("message", "messages"),
    "addr": ("address",),
}


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


@dataclass
class TimerEntry:
    id: int
    created_at: float
    due_at: float
    duration_sec: float
    label: str
    status: str
    cancelled_at: float | None


@dataclass
class ReminderEntry:
    id: int
    created_at: float
    due_at: float
    text: str
    status: str
    completed_at: float | None
    notified_at: float | None


class MemoryStore:
    def __init__(
        self,
        path: str,
        *,
        encryption_key: str = "",
        embedding_enabled: bool = False,
        embedding_model: str = "text-embedding-3-small",
        embedding_api_key: str = "",
        embedding_base_url: str = "",
        embedding_vector_weight: float = 0.65,
        embedding_min_similarity: float = 0.2,
        embedding_timeout_sec: float = 6.0,
    ) -> None:
        if path not in {":memory:", ""}:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._closed = False
        self._encrypted = False
        self._crypto_available = Fernet is not None
        self._fernet: Fernet | None = None
        self._configure_encryption(encryption_key)
        self._configure_connection()
        self._fts_enabled = False
        self._memory_enabled = False
        self._embedding_enabled = False
        self._embedding_model = ""
        self._embedding_api_key = ""
        self._embedding_base_url = ""
        self._embedding_vector_weight = 0.65
        self._embedding_min_similarity = 0.2
        self._embedding_timeout_sec = 6.0
        self._embedding_last_error = ""
        self._embedding_client: Any | None = None
        self._configure_embeddings(
            embedding_enabled=embedding_enabled,
            embedding_model=embedding_model,
            embedding_api_key=embedding_api_key,
            embedding_base_url=embedding_base_url,
            embedding_vector_weight=embedding_vector_weight,
            embedding_min_similarity=embedding_min_similarity,
            embedding_timeout_sec=embedding_timeout_sec,
        )
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

    def _configure_encryption(self, encryption_key: str) -> None:
        key = str(encryption_key or "").strip()
        if not key:
            self._encrypted = False
            self._fernet = None
            return
        if Fernet is None:
            self._encrypted = False
            self._fernet = None
            return
        candidate = key.encode("utf-8")
        try:
            # Accept a full Fernet key directly.
            Fernet(candidate)
            fernet_key = candidate
        except Exception:
            # Derive a stable Fernet key from passphrase input.
            digest = hashlib.sha256(candidate).digest()
            fernet_key = base64.urlsafe_b64encode(digest)
        self._fernet = Fernet(fernet_key)
        self._encrypted = True

    def _configure_embeddings(
        self,
        *,
        embedding_enabled: bool,
        embedding_model: str,
        embedding_api_key: str,
        embedding_base_url: str,
        embedding_vector_weight: float,
        embedding_min_similarity: float,
        embedding_timeout_sec: float,
    ) -> None:
        self._embedding_model = str(embedding_model or "text-embedding-3-small").strip() or "text-embedding-3-small"
        self._embedding_api_key = str(embedding_api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
        self._embedding_base_url = str(embedding_base_url or "").strip()
        vector_weight = 0.65
        try:
            parsed_vector_weight = float(embedding_vector_weight)
            if math.isfinite(parsed_vector_weight):
                vector_weight = parsed_vector_weight
        except (TypeError, ValueError):
            pass
        min_similarity = 0.2
        try:
            parsed_min_similarity = float(embedding_min_similarity)
            if math.isfinite(parsed_min_similarity):
                min_similarity = parsed_min_similarity
        except (TypeError, ValueError):
            pass
        timeout = 6.0
        try:
            parsed_timeout = float(embedding_timeout_sec)
            if math.isfinite(parsed_timeout):
                timeout = parsed_timeout
        except (TypeError, ValueError):
            pass
        self._embedding_vector_weight = self._clamp01(vector_weight)
        self._embedding_min_similarity = self._clamp01(min_similarity)
        self._embedding_timeout_sec = max(0.5, timeout)
        self._embedding_last_error = ""
        self._embedding_enabled = bool(embedding_enabled)
        if not self._embedding_enabled:
            return
        if self._encrypted:
            self._embedding_enabled = False
            self._embedding_last_error = "disabled_by_encryption"
            return
        if OpenAI is None:
            self._embedding_enabled = False
            self._embedding_last_error = "openai_sdk_missing"
            return
        if not self._embedding_api_key:
            self._embedding_enabled = False
            self._embedding_last_error = "missing_api_key"
            return

    def _encrypt_text(self, text: str) -> str:
        value = str(text)
        if not self._encrypted or self._fernet is None:
            return value
        token = self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        return f"enc:v1:{token}"

    def _decrypt_text(self, value: Any) -> str:
        text = str(value or "")
        if not self._encrypted or self._fernet is None:
            return text
        if not text.startswith("enc:v1:"):
            # Backward-compatible plaintext rows.
            return text
        token = text[len("enc:v1:") :]
        try:
            raw = self._fernet.decrypt(token.encode("utf-8"))
        except InvalidToken:
            return ""
        return raw.decode("utf-8")

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
            CREATE TABLE IF NOT EXISTS memory_embeddings (
                memory_id INTEGER PRIMARY KEY,
                model TEXT NOT NULL,
                vector TEXT NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(memory_id) REFERENCES memory(id) ON DELETE CASCADE
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_memory_embeddings_model ON memory_embeddings(model);")
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
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS timers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                due_at REAL NOT NULL,
                duration_sec REAL NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                cancelled_at REAL
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_timers_status_due ON timers(status, due_at ASC);")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL,
                due_at REAL NOT NULL,
                text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                completed_at REAL,
                notified_at REAL
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_reminders_status_due ON reminders(status, due_at ASC);")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_reminders_notify_due ON reminders(status, notified_at, due_at ASC);"
        )
        if not self._encrypted:
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
        else:
            self._fts_enabled = False
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
        stored_text = self._encrypt_text(clean)
        payload = json.dumps(tags or [])
        created_at = time.time()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO memory(created_at, kind, text, tags, importance, sensitivity, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (created_at, kind, stored_text, payload, float(importance), float(sensitivity), source),
        )
        memory_id = int(cur.lastrowid)
        if self._fts_enabled and not self._encrypted:
            cur.execute("INSERT INTO memory_fts(rowid, text) VALUES (?, ?)", (memory_id, clean))
        if self._memory_enabled and not self._encrypted:
            cur.execute("INSERT INTO memory_vec(rowid, text) VALUES (?, ?)", (memory_id, clean))
        self._conn.commit()
        if self._embedding_enabled:
            self._refresh_embedding_for_memory(memory_id, clean)
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
        candidate_multiplier: int = DEFAULT_SEARCH_CANDIDATE_MULTIPLIER,
    ) -> list[MemoryEntry]:
        cleaned = query.strip()
        if not cleaned:
            return []
        limit = self._normalize_limit(limit, default=5)
        candidate_limit = self._candidate_limit(limit=limit, multiplier=candidate_multiplier)
        if self._encrypted:
            entries = self._search_encrypted(
                cleaned,
                limit=candidate_limit,
                max_sensitivity=max_sensitivity,
                sources=sources,
            )
            entries = self._apply_hybrid_scoring(entries, cleaned, hybrid_weight)
            if decay_enabled:
                entries = self._apply_temporal_decay(entries, decay_half_life_days)
            if mmr_enabled:
                entries = self._apply_mmr(entries, mmr_lambda)
            return sorted(entries, key=lambda e: e.score, reverse=True)[:limit]
        vector_rows = self._search_vector(
            cleaned,
            limit=candidate_limit,
            max_sensitivity=max_sensitivity,
            sources=sources,
        )
        sensitivity_clause, sensitivity_params = self._sensitivity_filter(max_sensitivity)
        keyword_rows = self._search_keyword(
            cleaned,
            candidate_limit,
            sensitivity_clause,
            sensitivity_params,
            sources,
        )
        if not keyword_rows and not vector_rows:
            return []
        entries_by_id: dict[int, MemoryEntry] = {}
        vector_scores: dict[int, float] = {}
        for row in keyword_rows:
            entry = self._row_to_memory(row)
            entries_by_id[entry.id] = entry
        for entry, score in vector_rows:
            vector_scores[entry.id] = float(score)
            if entry.id not in entries_by_id:
                entries_by_id[entry.id] = entry
        entries = list(entries_by_id.values())
        entries = self._apply_hybrid_scoring(
            entries,
            cleaned,
            hybrid_weight,
            vector_scores=vector_scores,
            vector_weight=self._embedding_vector_weight,
        )
        if decay_enabled:
            entries = self._apply_temporal_decay(entries, decay_half_life_days)
        if mmr_enabled:
            entries = self._apply_mmr(entries, mmr_lambda)
        return sorted(entries, key=lambda e: e.score, reverse=True)[:limit]

    def inspect_memory_candidate(
        self,
        text: str,
        *,
        limit: int = 3,
        fanout: int = 40,
        max_sensitivity: float | None = None,
        sources: list[str] | None = None,
        duplicate_threshold: float = 0.88,
    ) -> dict[str, Any]:
        clean = str(text or "").strip()
        if not clean:
            return {
                "candidate_count": 0,
                "top_matches": [],
                "near_duplicates": [],
                "contradictions": [],
            }
        limit = self._normalize_limit(limit, default=3)
        fanout = self._normalize_limit(fanout, default=40)
        fanout = max(limit, min(MAX_CANDIDATE_ANALYSIS_FANOUT, fanout))
        incoming_tokens = set(self._tokenize_words(clean))
        incoming_assertion = self._extract_assertion(clean)
        candidates = self.search_v2(
            clean,
            limit=fanout,
            max_sensitivity=max_sensitivity,
            hybrid_weight=0.5,
            decay_enabled=False,
            mmr_enabled=False,
            sources=sources,
            candidate_multiplier=1,
        )
        top_matches: list[dict[str, Any]] = []
        duplicates: list[dict[str, Any]] = []
        contradictions: list[dict[str, Any]] = []
        for entry in candidates:
            entry_tokens = set(self._tokenize_words(entry.text))
            similarity = self._token_similarity(incoming_tokens, entry_tokens)
            if self._normalize_text(entry.text) == self._normalize_text(clean):
                similarity = 1.0
            candidate = {
                "memory_id": int(entry.id),
                "similarity": round(similarity, 4),
                "score": round(float(entry.score), 4),
                "kind": str(entry.kind),
                "source": str(entry.source),
                "text": str(entry.text),
            }
            top_matches.append(candidate)
            if similarity >= max(0.0, min(1.0, float(duplicate_threshold))):
                duplicates.append(candidate)
            existing_assertion = self._extract_assertion(entry.text)
            if incoming_assertion and existing_assertion and self._assertions_conflict(incoming_assertion, existing_assertion):
                contradictions.append(
                    {
                        **candidate,
                        "subject": incoming_assertion["subject"],
                        "predicate": incoming_assertion["predicate"],
                        "incoming": f"{incoming_assertion['polarity']}:{incoming_assertion['value']}",
                        "existing": f"{existing_assertion['polarity']}:{existing_assertion['value']}",
                    }
                )
        top_matches.sort(key=lambda item: float(item["similarity"]), reverse=True)
        duplicates.sort(key=lambda item: float(item["similarity"]), reverse=True)
        contradictions.sort(key=lambda item: float(item["similarity"]), reverse=True)
        return {
            "candidate_count": len(top_matches),
            "top_matches": top_matches[:limit],
            "near_duplicates": duplicates[:limit],
            "contradictions": contradictions[:limit],
        }

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
        limit = self._normalize_limit(limit, default=5)
        if self._encrypted:
            return self._search_encrypted(cleaned, limit=limit, max_sensitivity=max_sensitivity, sources=None)
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
        limit = self._normalize_limit(limit, default=5)
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

    def update_memory_text(self, memory_id: int, text: str) -> bool:
        clean = text.strip()
        if not clean:
            raise ValueError("memory text required")
        memory_key = int(memory_id)
        stored_text = self._encrypt_text(clean)
        with self._conn:
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE memory SET text = ? WHERE id = ?",
                (stored_text, memory_key),
            )
            updated = cur.rowcount > 0
            if not updated:
                return False
            if self._fts_enabled and not self._encrypted:
                cur.execute("DELETE FROM memory_fts WHERE rowid = ?", (memory_key,))
                cur.execute("INSERT INTO memory_fts(rowid, text) VALUES (?, ?)", (memory_key, clean))
            if self._memory_enabled and not self._encrypted:
                cur.execute("DELETE FROM memory_vec WHERE rowid = ?", (memory_key,))
                cur.execute("INSERT INTO memory_vec(rowid, text) VALUES (?, ?)", (memory_key, clean))
        if self._embedding_enabled:
            self._refresh_embedding_for_memory(memory_key, clean)
        return True

    def delete_memory(self, memory_id: int) -> bool:
        memory_key = int(memory_id)
        with self._conn:
            cur = self._conn.cursor()
            if self._fts_enabled and not self._encrypted:
                cur.execute("DELETE FROM memory_fts WHERE rowid = ?", (memory_key,))
            if self._memory_enabled and not self._encrypted:
                cur.execute("DELETE FROM memory_vec WHERE rowid = ?", (memory_key,))
            if self._embedding_enabled:
                cur.execute("DELETE FROM memory_embeddings WHERE memory_id = ?", (memory_key,))
            cur.execute("DELETE FROM memory WHERE id = ?", (memory_key,))
            return cur.rowcount > 0

    def add_task_plan(self, title: str, steps: list[str]) -> int:
        clean_title = title.strip()
        if not clean_title:
            raise ValueError("title required")
        clean_steps = [step.strip() for step in steps if step.strip()]
        if not clean_steps:
            raise ValueError("steps required")
        created_at = time.time()
        with self._conn:
            cur = self._conn.cursor()
            cur.execute(
                "INSERT INTO task_plans(created_at, title, status) VALUES (?, ?, ?)",
                (created_at, self._encrypt_text(clean_title), "open"),
            )
            plan_id = int(cur.lastrowid)
            for idx, clean_step in enumerate(clean_steps):
                cur.execute(
                    "INSERT INTO task_steps(plan_id, idx, text, status) VALUES (?, ?, ?, ?)",
                    (plan_id, idx, self._encrypt_text(clean_step), "pending"),
                )
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
                    title=self._decrypt_text(plan["title"]),
                    status=str(plan["status"]),
                    steps=[
                        TaskStep(
                            index=int(s["idx"]),
                            text=self._decrypt_text(s["text"]),
                            status=str(s["status"]),
                        )
                        for s in steps
                    ],
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
        with self._conn:
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
            title=self._decrypt_text(plan_row["title"]),
            status=str(plan_row["status"]),
            steps=[],
        )
        step = TaskStep(
            index=int(step_row["idx"]),
            text=self._decrypt_text(step_row["text"]),
            status=str(step_row["status"]),
        )
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
            (clean_topic, self._encrypt_text(clean_summary), updated_at),
        )
        self._conn.commit()

    def list_summaries(self, *, limit: int = 5) -> list[MemorySummary]:
        limit = self._normalize_limit(limit, default=5)
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT * FROM memory_summaries ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            MemorySummary(
                topic=str(row["topic"]),
                summary=self._decrypt_text(row["summary"]),
                updated_at=float(row["updated_at"]),
            )
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
            summary=self._decrypt_text(row["summary"]),
            updated_at=float(row["updated_at"]),
        )

    def add_timer(
        self,
        *,
        due_at: float,
        duration_sec: float,
        label: str = "",
        created_at: float | None = None,
    ) -> int:
        if not math.isfinite(due_at):
            raise ValueError("due_at must be finite")
        if not math.isfinite(duration_sec) or duration_sec <= 0.0:
            raise ValueError("duration_sec must be > 0")
        created = time.time() if created_at is None else float(created_at)
        clean_label = label.strip()
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO timers(created_at, due_at, duration_sec, label, status, cancelled_at)
            VALUES (?, ?, ?, ?, 'active', NULL)
            """,
            (created, float(due_at), float(duration_sec), clean_label),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_timers(
        self,
        *,
        status: str = "active",
        include_expired: bool = False,
        now: float | None = None,
        limit: int = 200,
    ) -> list[TimerEntry]:
        clean_status = status.strip().lower()
        if clean_status not in {"active", "expired", "cancelled"}:
            raise ValueError("status must be active, expired, or cancelled")
        limit = self._normalize_limit(limit, default=200)
        cur = self._conn.cursor()
        params: list[Any] = [clean_status]
        where = "status = ?"
        if clean_status == "active" and not include_expired:
            now_ts = time.time() if now is None else float(now)
            where += " AND due_at > ?"
            params.append(now_ts)
        rows = cur.execute(
            f"SELECT * FROM timers WHERE {where} ORDER BY due_at ASC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [self._row_to_timer(row) for row in rows]

    def expire_timers(self, *, now: float | None = None) -> int:
        now_ts = time.time() if now is None else float(now)
        with self._conn:
            cur = self._conn.cursor()
            cur.execute(
                """
                UPDATE timers
                SET status = 'expired'
                WHERE status = 'active' AND due_at <= ?
                """,
                (now_ts,),
            )
            return int(cur.rowcount)

    def cancel_timer(self, timer_id: int, *, cancelled_at: float | None = None) -> bool:
        cancelled = time.time() if cancelled_at is None else float(cancelled_at)
        with self._conn:
            cur = self._conn.cursor()
            cur.execute(
                """
                UPDATE timers
                SET status = 'cancelled', cancelled_at = ?
                WHERE id = ? AND status = 'active'
                """,
                (cancelled, int(timer_id)),
            )
            return cur.rowcount > 0

    def timer_counts(self) -> dict[str, int]:
        rows = self._conn.cursor().execute(
            "SELECT status, COUNT(*) AS c FROM timers GROUP BY status",
        ).fetchall()
        counts = {"active": 0, "expired": 0, "cancelled": 0}
        for row in rows:
            key = str(row["status"])
            if key in counts:
                counts[key] = int(row["c"])
        return counts

    def add_reminder(
        self,
        *,
        text: str,
        due_at: float,
        created_at: float | None = None,
    ) -> int:
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("reminder text required")
        if not math.isfinite(due_at):
            raise ValueError("due_at must be finite")
        created = time.time() if created_at is None else float(created_at)
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO reminders(created_at, due_at, text, status, completed_at, notified_at)
            VALUES (?, ?, ?, 'pending', NULL, NULL)
            """,
            (created, float(due_at), self._encrypt_text(clean_text)),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_reminders(
        self,
        *,
        status: str = "pending",
        due_only: bool = False,
        include_notified: bool = True,
        now: float | None = None,
        limit: int = 200,
    ) -> list[ReminderEntry]:
        clean_status = status.strip().lower()
        if clean_status not in {"pending", "completed"}:
            raise ValueError("status must be pending or completed")
        limit = self._normalize_limit(limit, default=200)
        where = "status = ?"
        params: list[Any] = [clean_status]
        if due_only:
            now_ts = time.time() if now is None else float(now)
            where += " AND due_at <= ?"
            params.append(now_ts)
        if clean_status == "pending" and not include_notified:
            where += " AND notified_at IS NULL"
        rows = self._conn.cursor().execute(
            f"SELECT * FROM reminders WHERE {where} ORDER BY due_at ASC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [self._row_to_reminder(row) for row in rows]

    def complete_reminder(self, reminder_id: int, *, completed_at: float | None = None) -> bool:
        completed = time.time() if completed_at is None else float(completed_at)
        with self._conn:
            cur = self._conn.cursor()
            cur.execute(
                """
                UPDATE reminders
                SET status = 'completed', completed_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (completed, int(reminder_id)),
            )
            return cur.rowcount > 0

    def mark_reminder_notified(self, reminder_id: int, *, notified_at: float | None = None) -> bool:
        notified = time.time() if notified_at is None else float(notified_at)
        with self._conn:
            cur = self._conn.cursor()
            cur.execute(
                """
                UPDATE reminders
                SET notified_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (notified, int(reminder_id)),
            )
            return cur.rowcount > 0

    def reminder_counts(self) -> dict[str, int]:
        rows = self._conn.cursor().execute(
            "SELECT status, COUNT(*) AS c FROM reminders GROUP BY status",
        ).fetchall()
        counts = {"pending": 0, "completed": 0}
        for row in rows:
            key = str(row["status"])
            if key in counts:
                counts[key] = int(row["c"])
        return counts

    def prune_retention(self, *, cutoff_ts: float) -> dict[str, int]:
        cutoff = float(cutoff_ts)
        deleted = {
            "memory": 0,
            "task_plans": 0,
            "task_steps": 0,
            "memory_summaries": 0,
            "timers": 0,
            "reminders": 0,
        }
        with self._conn:
            cur = self._conn.cursor()
            if self._fts_enabled:
                cur.execute("DELETE FROM memory_fts WHERE rowid IN (SELECT id FROM memory WHERE created_at < ?)", (cutoff,))
            if self._memory_enabled:
                cur.execute("DELETE FROM memory_vec WHERE rowid IN (SELECT id FROM memory WHERE created_at < ?)", (cutoff,))
            if self._embedding_enabled:
                cur.execute(
                    "DELETE FROM memory_embeddings WHERE memory_id IN (SELECT id FROM memory WHERE created_at < ?)",
                    (cutoff,),
                )
            cur.execute("DELETE FROM memory WHERE created_at < ?", (cutoff,))
            deleted["memory"] = int(cur.rowcount)

            cur.execute("DELETE FROM task_steps WHERE plan_id IN (SELECT id FROM task_plans WHERE created_at < ?)", (cutoff,))
            deleted["task_steps"] = int(cur.rowcount)
            cur.execute("DELETE FROM task_plans WHERE created_at < ?", (cutoff,))
            deleted["task_plans"] = int(cur.rowcount)

            cur.execute("DELETE FROM memory_summaries WHERE updated_at < ?", (cutoff,))
            deleted["memory_summaries"] = int(cur.rowcount)

            cur.execute("DELETE FROM timers WHERE created_at < ? AND status != 'active'", (cutoff,))
            deleted["timers"] = int(cur.rowcount)

            cur.execute("DELETE FROM reminders WHERE created_at < ? AND status = 'completed'", (cutoff,))
            deleted["reminders"] = int(cur.rowcount)
        return deleted

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
        embedding_count_row = cur.execute("SELECT COUNT(*) AS c FROM memory_embeddings").fetchone()
        embedding_count = int(embedding_count_row["c"]) if embedding_count_row is not None else 0
        return {
            "entries": int(count),
            "fts": self._fts_enabled,
            "vector": self._memory_enabled,
            "encrypted": self._encrypted,
            "crypto_available": self._crypto_available,
            "semantic_vector": {
                "enabled": self._embedding_enabled,
                "model": self._embedding_model,
                "entries": embedding_count,
                "vector_weight": self._embedding_vector_weight,
                "min_similarity": self._embedding_min_similarity,
                "last_error": self._embedding_last_error,
            },
            "sources": source_counts,
            "timers": self.timer_counts(),
            "reminders": self.reminder_counts(),
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
            text=self._decrypt_text(row["text"]),
            tags=tags,
            importance=float(row["importance"]),
            sensitivity=float(row["sensitivity"]),
            source=str(row["source"]),
        )

    def _row_to_timer(self, row: sqlite3.Row) -> TimerEntry:
        cancelled_at = row["cancelled_at"]
        return TimerEntry(
            id=int(row["id"]),
            created_at=float(row["created_at"]),
            due_at=float(row["due_at"]),
            duration_sec=float(row["duration_sec"]),
            label=str(row["label"] or ""),
            status=str(row["status"]),
            cancelled_at=float(cancelled_at) if cancelled_at is not None else None,
        )

    def _row_to_reminder(self, row: sqlite3.Row) -> ReminderEntry:
        completed_at = row["completed_at"]
        notified_at = row["notified_at"]
        return ReminderEntry(
            id=int(row["id"]),
            created_at=float(row["created_at"]),
            due_at=float(row["due_at"]),
            text=self._decrypt_text(row["text"]),
            status=str(row["status"]),
            completed_at=float(completed_at) if completed_at is not None else None,
            notified_at=float(notified_at) if notified_at is not None else None,
        )

    @staticmethod
    def _normalize_limit(value: Any, *, default: int = 5) -> int:
        parsed = default
        if isinstance(value, bool):
            parsed = default
        elif isinstance(value, int):
            parsed = value
        elif isinstance(value, float):
            if math.isfinite(value) and value.is_integer():
                parsed = int(value)
        elif isinstance(value, str):
            text = value.strip()
            if text and (text.isdigit() or (text.startswith(("+", "-")) and text[1:].isdigit())):
                try:
                    parsed = int(text)
                except ValueError:
                    parsed = default
        else:
            try:
                parsed = int(value)
            except (TypeError, ValueError, OverflowError):
                parsed = default
        return max(1, min(MAX_QUERY_LIMIT, parsed))

    def _build_fts_query(self, text: str) -> str:
        tokens = self._extract_keywords(text)
        if not tokens:
            tokens = self._tokenize_words(text)
        return " OR ".join(tokens[:16])

    def _extract_keywords(self, text: str) -> list[str]:
        tokens = self._tokenize_words(text)
        keywords: list[str] = []
        seen = set()
        for token in tokens:
            if token in _STOP_WORDS or len(token) < 3:
                continue
            if token not in seen:
                seen.add(token)
                keywords.append(token)
        return keywords

    def _tokenize_words(self, text: str) -> list[str]:
        return re.findall(r"[a-z0-9_']+", str(text or "").lower())

    def _expand_query_tokens(self, tokens: list[str]) -> list[str]:
        expanded: list[str] = []
        seen = set(tokens)
        for token in tokens:
            stems: list[str] = []
            if token.endswith("ies") and len(token) > 4:
                stems.append(token[:-3] + "y")
            if token.endswith("ing") and len(token) > 5:
                stems.append(token[:-3])
            if token.endswith("ed") and len(token) > 4:
                stems.append(token[:-2])
            if token.endswith("es") and len(token) > 4:
                stems.append(token[:-2])
            if token.endswith("s") and len(token) > 3:
                stems.append(token[:-1])
            stems.extend(_TOKEN_EXPANSIONS.get(token, ()))
            for stem in stems:
                normalized = stem.strip().lower()
                if not normalized or normalized in _STOP_WORDS or normalized in seen:
                    continue
                seen.add(normalized)
                expanded.append(normalized)
        return expanded

    def _normalize_text(self, text: str) -> str:
        return " ".join(str(text or "").strip().lower().split())

    def _token_similarity(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        intersection = len(left & right)
        union = len(left | right)
        if union <= 0:
            return 0.0
        return intersection / union

    def _temporal_prior(self, created_at: float, *, half_life_days: float) -> float:
        if half_life_days <= 0.0:
            return 1.0
        age_days = max(0.0, (time.time() - float(created_at)) / 86400.0)
        multiplier = math.exp(-math.log(2.0) * (age_days / half_life_days))
        return self._clamp01(multiplier)

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    def _candidate_limit(self, *, limit: int, multiplier: Any) -> int:
        parsed = DEFAULT_SEARCH_CANDIDATE_MULTIPLIER
        if isinstance(multiplier, bool):
            parsed = DEFAULT_SEARCH_CANDIDATE_MULTIPLIER
        elif isinstance(multiplier, int):
            parsed = multiplier
        elif isinstance(multiplier, float):
            if math.isfinite(multiplier):
                parsed = int(multiplier)
        elif isinstance(multiplier, str):
            text = multiplier.strip()
            if text and (text.isdigit() or (text.startswith(("+", "-")) and text[1:].isdigit())):
                with_value_error = DEFAULT_SEARCH_CANDIDATE_MULTIPLIER
                try:
                    with_value_error = int(text)
                except ValueError:
                    with_value_error = DEFAULT_SEARCH_CANDIDATE_MULTIPLIER
                parsed = with_value_error
        parsed = max(1, min(20, parsed))
        return min(MAX_SEARCH_FANOUT, max(limit, limit * parsed))

    def _extract_assertion(self, text: str) -> dict[str, str] | None:
        parsed_text = self._normalize_text(text)
        if not parsed_text:
            return None
        match = re.match(
            (
                r"^(?P<subject>[a-z0-9][a-z0-9 _'-]{1,80}?)\s+"
                r"(?P<predicate>is|are|likes|like|prefers|prefer)\s+"
                r"(?P<negation>not\s+)?"
                r"(?P<value>[a-z0-9][a-z0-9 _'/-]{0,80})$"
            ),
            parsed_text,
            re.IGNORECASE,
        )
        if not match:
            return None
        predicate_raw = match.group("predicate").strip().lower()
        predicate = {
            "are": "is",
            "like": "likes",
            "prefer": "prefers",
        }.get(predicate_raw, predicate_raw)
        subject = self._normalize_text(match.group("subject"))
        value = self._normalize_text(match.group("value"))
        if not subject or not value:
            return None
        return {
            "subject": subject,
            "predicate": predicate,
            "polarity": "negative" if match.group("negation") else "positive",
            "value": value,
        }

    def _assertions_conflict(self, left: dict[str, str], right: dict[str, str]) -> bool:
        if left.get("subject") != right.get("subject"):
            return False
        if left.get("predicate") != right.get("predicate"):
            return False
        left_polarity = left.get("polarity", "positive")
        right_polarity = right.get("polarity", "positive")
        left_value = left.get("value", "")
        right_value = right.get("value", "")
        if left_polarity != right_polarity and left_value == right_value:
            return True
        # "X is A" vs "X is B" is likely inconsistent.
        if left.get("predicate") == "is" and left_polarity == "positive" and right_polarity == "positive":
            return left_value != right_value
        return False

    def _embedding_client_instance(self) -> Any | None:
        if not self._embedding_enabled:
            return None
        if self._embedding_client is not None:
            return self._embedding_client
        if OpenAI is None:
            self._embedding_last_error = "openai_sdk_missing"
            self._embedding_enabled = False
            return None
        kwargs: dict[str, Any] = {
            "api_key": self._embedding_api_key,
            "timeout": self._embedding_timeout_sec,
        }
        if self._embedding_base_url:
            kwargs["base_url"] = self._embedding_base_url
        try:
            self._embedding_client = OpenAI(**kwargs)
        except Exception as exc:
            self._embedding_last_error = f"client_init_failed:{exc}"
            self._embedding_enabled = False
            return None
        return self._embedding_client

    def _embed_text(self, text: str) -> list[float] | None:
        client = self._embedding_client_instance()
        if client is None:
            return None
        clean = str(text or "").strip()
        if not clean:
            return None
        try:
            response = client.embeddings.create(
                model=self._embedding_model,
                input=clean,
            )
        except Exception as exc:
            self._embedding_last_error = f"embed_failed:{exc}"
            return None
        payload = getattr(response, "data", None)
        if not payload:
            self._embedding_last_error = "embed_failed:empty_response"
            return None
        vector_raw = getattr(payload[0], "embedding", None)
        if not isinstance(vector_raw, list) or not vector_raw:
            self._embedding_last_error = "embed_failed:invalid_payload"
            return None
        vector: list[float] = []
        for value in vector_raw:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                self._embedding_last_error = "embed_failed:non_numeric"
                return None
            if not math.isfinite(numeric):
                self._embedding_last_error = "embed_failed:non_finite"
                return None
            vector.append(numeric)
        self._embedding_last_error = ""
        return vector

    def _refresh_embedding_for_memory(self, memory_id: int, text: str) -> None:
        if not self._embedding_enabled:
            return
        vector = self._embed_text(text)
        try:
            with self._conn:
                cur = self._conn.cursor()
                cur.execute("DELETE FROM memory_embeddings WHERE memory_id = ?", (int(memory_id),))
                if not vector:
                    return
                cur.execute(
                    """
                    INSERT INTO memory_embeddings(memory_id, model, vector, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (int(memory_id), self._embedding_model, json.dumps(vector), time.time()),
                )
        except Exception as exc:
            self._embedding_last_error = f"embedding_store_failed:{exc}"

    def _search_vector(
        self,
        query: str,
        *,
        limit: int,
        max_sensitivity: float | None,
        sources: list[str] | None,
    ) -> list[tuple[MemoryEntry, float]]:
        if not self._embedding_enabled:
            return []
        query_vector = self._embed_text(query)
        if not query_vector:
            return []
        query_np = np.asarray(query_vector, dtype=np.float32)
        query_norm = float(np.linalg.norm(query_np))
        if not math.isfinite(query_norm) or query_norm <= 0.0:
            return []
        sensitivity_clause, sensitivity_params = self._sensitivity_filter(max_sensitivity)
        source_clause, source_params = self._source_filter(sources)
        fetch_limit = min(MAX_SEARCH_FANOUT, max(limit, limit * 6))
        rows = self._conn.cursor().execute(
            (
                "SELECT memory.*, memory_embeddings.vector AS embedding_vector "
                "FROM memory_embeddings "
                "JOIN memory ON memory_embeddings.memory_id = memory.id "
                "WHERE memory_embeddings.model = ? "
                f"{sensitivity_clause} {source_clause} "
                "ORDER BY memory.created_at DESC LIMIT ?"
            ),
            (self._embedding_model, *sensitivity_params, *source_params, fetch_limit),
        ).fetchall()
        scored: list[tuple[MemoryEntry, float]] = []
        for row in rows:
            vector_text = str(row["embedding_vector"] or "")
            if not vector_text:
                continue
            try:
                parsed = json.loads(vector_text)
            except (TypeError, ValueError):
                continue
            if not isinstance(parsed, list) or not parsed:
                continue
            try:
                candidate_np = np.asarray(parsed, dtype=np.float32)
            except Exception:
                continue
            if candidate_np.shape != query_np.shape:
                continue
            candidate_norm = float(np.linalg.norm(candidate_np))
            if not math.isfinite(candidate_norm) or candidate_norm <= 0.0:
                continue
            cosine = float(np.dot(candidate_np, query_np) / (candidate_norm * query_norm))
            if not math.isfinite(cosine):
                continue
            score = self._clamp01((cosine + 1.0) / 2.0)
            if score < self._embedding_min_similarity:
                continue
            entry = self._row_to_memory(row)
            scored.append((entry, score))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

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
            keywords.extend(self._expand_query_tokens(keywords))
            if len(keywords) > 24:
                keywords = keywords[:24]
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

    def _search_encrypted(
        self,
        query: str,
        *,
        limit: int,
        max_sensitivity: float | None,
        sources: list[str] | None,
    ) -> list[MemoryEntry]:
        lowered = self._normalize_text(query)
        query_tokens = set(self._tokenize_words(lowered))
        cur = self._conn.cursor()
        sensitivity_clause, sensitivity_params = self._sensitivity_filter(max_sensitivity)
        source_clause, source_params = self._source_filter(sources)
        fetch_limit = min(MAX_SEARCH_FANOUT, max(limit, limit * 5))
        rows = cur.execute(
            (
                "SELECT * FROM memory WHERE 1=1 "
                f"{sensitivity_clause} {source_clause} "
                "ORDER BY created_at DESC LIMIT ?"
            ),
            (*sensitivity_params, *source_params, fetch_limit),
        ).fetchall()
        results: list[MemoryEntry] = []
        for row in rows:
            entry = self._row_to_memory(row)
            entry_text = self._normalize_text(entry.text)
            if lowered and lowered in entry_text:
                results.append(entry)
                continue
            text_tokens = set(self._tokenize_words(entry_text))
            if query_tokens and (query_tokens & text_tokens):
                results.append(entry)
        return results[:limit]

    def _apply_hybrid_scoring(
        self,
        entries: list[MemoryEntry],
        query: str,
        weight: float,
        *,
        vector_scores: dict[int, float] | None = None,
        vector_weight: float = 0.0,
    ) -> list[MemoryEntry]:
        if not entries:
            return entries
        importance_weight = max(0.0, min(1.0, float(weight)))
        lexical_weight = 1.0 - importance_weight
        vector_weight = self._clamp01(float(vector_weight))
        vector_scores = vector_scores or {}
        query_terms = self._extract_keywords(query)
        if not query_terms:
            query_terms = self._tokenize_words(query)
        expanded_terms = self._expand_query_tokens(query_terms)
        all_terms = list(dict.fromkeys([*query_terms, *expanded_terms]))
        if not all_terms:
            all_terms = self._tokenize_words(query)[:8]
        entry_token_cache: list[set[str]] = [set(self._tokenize_words(entry.text)) for entry in entries]
        doc_count = max(1, len(entries))
        term_idf: dict[str, float] = {}
        for term in all_terms:
            document_frequency = sum(1 for tokens in entry_token_cache if term in tokens)
            term_idf[term] = 1.0 + math.log((doc_count + 1.0) / (1.0 + float(document_frequency)))
        query_mass = sum(term_idf.get(term, 0.0) for term in query_terms)
        if query_mass <= 0.0:
            query_mass = float(max(1, len(query_terms)))
        all_mass = sum(term_idf.get(term, 0.0) for term in all_terms)
        if all_mass <= 0.0:
            all_mass = float(max(1, len(all_terms)))
        query_phrase = self._normalize_text(query)
        query_token_set = set(query_terms)
        for entry in entries:
            entry_tokens = set(self._tokenize_words(entry.text))
            weighted_coverage = sum(term_idf.get(term, 0.0) for term in query_terms if term in entry_tokens) / query_mass
            expansion_coverage = sum(term_idf.get(term, 0.0) for term in all_terms if term in entry_tokens) / all_mass
            phrase_hit = 1.0 if query_phrase and query_phrase in self._normalize_text(entry.text) else 0.0
            token_similarity = self._token_similarity(query_token_set, entry_tokens)
            lexical_score = self._clamp01(
                (0.45 * weighted_coverage)
                + (0.25 * expansion_coverage)
                + (0.2 * token_similarity)
                + (0.1 * phrase_hit)
            )
            recency_prior = self._temporal_prior(entry.created_at, half_life_days=DEFAULT_RECENCY_PRIOR_HALF_LIFE_DAYS)
            retrieval_score = self._clamp01((0.9 * lexical_score) + (0.1 * recency_prior))
            vector_score = vector_scores.get(entry.id)
            if vector_score is not None:
                retrieval_score = self._clamp01(
                    ((1.0 - vector_weight) * retrieval_score) + (vector_weight * self._clamp01(float(vector_score)))
                )
            entry.score = self._clamp01((importance_weight * entry.importance) + (lexical_weight * retrieval_score))
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
                entry_tokens = set(self._tokenize_words(entry.text))
                for chosen in selected:
                    chosen_tokens = set(self._tokenize_words(chosen.text))
                    sim = self._token_similarity(entry_tokens, chosen_tokens)
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
