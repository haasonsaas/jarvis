"""Tests for jarvis.memory."""

import sqlite3
from pathlib import Path

import pytest

from jarvis.memory import MemoryStore


def test_memory_store_accepts_relative_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = MemoryStore("memory.sqlite")
    try:
        store.add_memory("Relative path works.")
    finally:
        store.close()
    assert (Path(tmp_path) / "memory.sqlite").exists()


def test_update_task_step_returns_false_for_missing_step(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        plan_id = store.add_task_plan("Test", ["A", "B"])
        updated = store.update_task_step(plan_id, 99, "done")
    finally:
        store.close()
    assert updated is False


def test_add_task_plan_requires_non_empty_steps(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        with pytest.raises(ValueError):
            store.add_task_plan("Plan", ["  ", "\n"])
    finally:
        store.close()


def test_update_task_step_rejects_invalid_status(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        plan_id = store.add_task_plan("Plan", ["step"])
        with pytest.raises(ValueError):
            store.update_task_step(plan_id, 0, "finished")
    finally:
        store.close()


def test_recent_tolerates_invalid_tags_payload(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        memory_id = store.add_memory("Note", tags=["valid"])
        store._conn.execute("UPDATE memory SET tags = ? WHERE id = ?", ("{not-json", memory_id))
        store._conn.commit()
        rows = store.recent(limit=1)
        assert len(rows) == 1
        assert rows[0].tags == []
    finally:
        store.close()


def test_memory_store_close_is_idempotent(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    store.close()
    store.close()  # should not raise


def test_memory_store_enables_foreign_keys(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        value = store._conn.execute("PRAGMA foreign_keys;").fetchone()[0]
        assert int(value) == 1
    finally:
        store.close()


def test_memory_store_sets_busy_timeout(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        value = store._conn.execute("PRAGMA busy_timeout;").fetchone()[0]
        assert int(value) == 5000
    finally:
        store.close()


def test_task_plan_reopens_when_step_marked_not_done(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        plan_id = store.add_task_plan("Plan", ["A", "B"])
        assert store.update_task_step(plan_id, 0, "done")
        assert store.update_task_step(plan_id, 1, "done")
        closed = store.list_task_plans(open_only=False)[0]
        assert closed.status == "closed"

        assert store.update_task_step(plan_id, 1, "pending")
        reopened = store.list_task_plans(open_only=False)[0]
        assert reopened.status == "open"
    finally:
        store.close()


def test_search_limits_are_clamped_in_store(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        for idx in range(10):
            store.add_memory(f"memory {idx}")
        results = store.search_v2("memory", limit=10000)
        assert len(results) <= 200
    finally:
        store.close()


def test_recent_bool_limit_uses_default_store_limit(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        for idx in range(10):
            store.add_memory(f"memory {idx}")
        rows = store.recent(limit=True)
        assert len(rows) == 5
    finally:
        store.close()


def test_search_fractional_limit_uses_default_store_limit(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        for idx in range(10):
            store.add_memory(f"memory {idx}")
        rows = store.search_v2("memory", limit=2.7)
        assert len(rows) == 5
    finally:
        store.close()


def test_memory_optimize_and_vacuum_update_status(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        store.optimize()
        store.vacuum()
        status = store.memory_status()
        assert status["last_optimize"] is not None
        assert status["last_vacuum"] is not None
    finally:
        store.close()


def test_get_summary_returns_topic_case_insensitive(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        store.upsert_summary("Persona_Style", "friendly")
        summary = store.get_summary("persona_style")
        assert summary is not None
        assert summary.summary == "friendly"
    finally:
        store.close()


def test_add_task_plan_rolls_back_on_step_insert_failure(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        store._conn.execute(
            """
            CREATE TRIGGER fail_second_step_insert
            BEFORE INSERT ON task_steps
            WHEN NEW.idx = 1
            BEGIN
                SELECT RAISE(FAIL, 'step insert failure');
            END;
            """
        )
        with pytest.raises(sqlite3.DatabaseError):
            store.add_task_plan("Plan", ["A", "B"])
        plan_count = store._conn.execute("SELECT COUNT(*) FROM task_plans").fetchone()[0]
        step_count = store._conn.execute("SELECT COUNT(*) FROM task_steps").fetchone()[0]
        assert int(plan_count) == 0
        assert int(step_count) == 0
    finally:
        store.close()


def test_update_task_step_rolls_back_on_plan_status_failure(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        plan_id = store.add_task_plan("Plan", ["A"])
        store._conn.execute(
            """
            CREATE TRIGGER fail_plan_status_update
            BEFORE UPDATE ON task_plans
            BEGIN
                SELECT RAISE(FAIL, 'plan status update failure');
            END;
            """
        )
        with pytest.raises(sqlite3.DatabaseError):
            store.update_task_step(plan_id, 0, "done")
        step_status = store._conn.execute(
            "SELECT status FROM task_steps WHERE plan_id = ? AND idx = 0",
            (plan_id,),
        ).fetchone()[0]
        plan_status = store._conn.execute(
            "SELECT status FROM task_plans WHERE id = ?",
            (plan_id,),
        ).fetchone()[0]
        assert step_status == "pending"
        assert plan_status == "open"
    finally:
        store.close()


def test_timer_store_lifecycle(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        now = 1_700_000_000.0
        timer_id = store.add_timer(
            due_at=now + 120.0,
            duration_sec=120.0,
            label="tea",
            created_at=now,
        )
        active = store.list_timers(status="active", include_expired=False, now=now)
        assert [timer.id for timer in active] == [timer_id]
        assert active[0].label == "tea"

        assert store.cancel_timer(timer_id) is True
        assert store.cancel_timer(timer_id) is False
        cancelled = store.list_timers(status="cancelled")
        assert [timer.id for timer in cancelled] == [timer_id]
    finally:
        store.close()


def test_expire_timers_moves_due_rows_to_expired(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        now = 1_700_000_000.0
        _ = store.add_timer(
            due_at=now - 5.0,
            duration_sec=30.0,
            label="old",
            created_at=now - 35.0,
        )
        changed = store.expire_timers(now=now)
        assert changed == 1
        active = store.list_timers(status="active", include_expired=False, now=now)
        assert active == []
        expired = store.list_timers(status="expired")
        assert len(expired) == 1
        counts = store.timer_counts()
        assert counts["expired"] == 1
        assert counts["active"] == 0
    finally:
        store.close()
