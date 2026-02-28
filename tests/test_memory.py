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


def test_reminder_store_lifecycle(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        now = 1_700_000_000.0
        reminder_id = store.add_reminder(
            text="take medicine",
            due_at=now + 300.0,
            created_at=now,
        )

        pending = store.list_reminders(status="pending", now=now)
        assert [reminder.id for reminder in pending] == [reminder_id]
        assert pending[0].text == "take medicine"
        assert pending[0].notified_at is None

        assert store.mark_reminder_notified(reminder_id, notified_at=now + 60.0) is True
        pending_after_notify = store.list_reminders(status="pending", include_notified=False, now=now)
        assert pending_after_notify == []

        assert store.complete_reminder(reminder_id, completed_at=now + 120.0) is True
        assert store.complete_reminder(reminder_id, completed_at=now + 121.0) is False
        completed = store.list_reminders(status="completed")
        assert [reminder.id for reminder in completed] == [reminder_id]
        assert completed[0].completed_at == pytest.approx(now + 120.0)
    finally:
        store.close()


def test_list_reminders_due_only_filter(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        now = 1_700_000_000.0
        _ = store.add_reminder(text="overdue", due_at=now - 5.0, created_at=now - 10.0)
        _ = store.add_reminder(text="future", due_at=now + 600.0, created_at=now - 5.0)

        due = store.list_reminders(status="pending", due_only=True, now=now)
        assert len(due) == 1
        assert due[0].text == "overdue"
    finally:
        store.close()


def test_prune_retention_removes_old_non_active_data(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        cutoff = 1_700_000_000.0
        old_ts = cutoff - 10_000.0
        new_ts = cutoff + 10_000.0

        old_memory = store.add_memory("old memory")
        new_memory = store.add_memory("new memory")
        store._conn.execute("UPDATE memory SET created_at = ? WHERE id = ?", (old_ts, old_memory))
        store._conn.execute("UPDATE memory SET created_at = ? WHERE id = ?", (new_ts, new_memory))

        old_plan = store.add_task_plan("old plan", ["a"])
        new_plan = store.add_task_plan("new plan", ["b"])
        store._conn.execute("UPDATE task_plans SET created_at = ? WHERE id = ?", (old_ts, old_plan))
        store._conn.execute("UPDATE task_plans SET created_at = ? WHERE id = ?", (new_ts, new_plan))

        store.upsert_summary("old_topic", "old summary")
        store.upsert_summary("new_topic", "new summary")
        store._conn.execute("UPDATE memory_summaries SET updated_at = ? WHERE topic = 'old_topic'", (old_ts,))
        store._conn.execute("UPDATE memory_summaries SET updated_at = ? WHERE topic = 'new_topic'", (new_ts,))

        old_timer = store.add_timer(due_at=old_ts + 60.0, duration_sec=60.0, label="old", created_at=old_ts)
        _ = store.cancel_timer(old_timer, cancelled_at=old_ts + 30.0)
        _ = store.add_timer(due_at=new_ts + 60.0, duration_sec=60.0, label="new-active", created_at=old_ts)

        old_reminder = store.add_reminder(text="old completed", due_at=old_ts + 120.0, created_at=old_ts)
        _ = store.complete_reminder(old_reminder, completed_at=old_ts + 300.0)
        _ = store.add_reminder(text="old pending", due_at=old_ts + 180.0, created_at=old_ts)

        store._conn.commit()

        deleted = store.prune_retention(cutoff_ts=cutoff)
        assert deleted["memory"] >= 1
        assert deleted["task_plans"] >= 1
        assert deleted["task_steps"] >= 1
        assert deleted["memory_summaries"] >= 1
        assert deleted["timers"] >= 1
        assert deleted["reminders"] >= 1

        remaining_memory = [row.id for row in store.recent(limit=10)]
        assert new_memory in remaining_memory
        assert old_memory not in remaining_memory

        plans = store.list_task_plans(open_only=False)
        assert any(plan.id == new_plan for plan in plans)
        assert all(plan.id != old_plan for plan in plans)

        summaries = store.list_summaries(limit=10)
        topics = {item.topic for item in summaries}
        assert "new_topic" in topics
        assert "old_topic" not in topics

        active_timers = store.list_timers(status="active", include_expired=True, now=cutoff + 1.0)
        assert any(timer.label == "new-active" for timer in active_timers)
    finally:
        store.close()


def test_memory_store_encryption_round_trip(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"), encryption_key="top-secret")
    try:
        memory_id = store.add_memory("secret note", kind="note")
        raw_text = store._conn.execute("SELECT text FROM memory WHERE id = ?", (memory_id,)).fetchone()[0]
        assert str(raw_text).startswith("enc:v1:")

        rows = store.search_v2("secret", limit=5)
        assert rows
        assert rows[0].text == "secret note"

        reminder_id = store.add_reminder(text="secret reminder", due_at=1_700_000_500.0, created_at=1_700_000_000.0)
        raw_reminder = store._conn.execute("SELECT text FROM reminders WHERE id = ?", (reminder_id,)).fetchone()[0]
        assert str(raw_reminder).startswith("enc:v1:")
        reminders = store.list_reminders(status="pending")
        assert reminders[0].text == "secret reminder"

        status = store.memory_status()
        assert status["encrypted"] is True
        assert status["fts"] is False
    finally:
        store.close()


def test_memory_store_encryption_reads_legacy_plaintext(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"), encryption_key="top-secret")
    try:
        store._conn.execute(
            "INSERT INTO memory(created_at, kind, text, tags, importance, sensitivity, source) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (1_700_000_000.0, "note", "legacy row", "[]", 0.5, 0.0, "user"),
        )
        store._conn.commit()

        rows = store.search_v2("legacy", limit=5)
        assert rows
        assert rows[0].text == "legacy row"
    finally:
        store.close()


def test_search_v2_prefers_stronger_lexical_match_when_importance_weight_is_lower(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        best_id = store.add_memory(
            "Project atlas launch deadline is Friday.",
            importance=0.2,
            source="notes",
        )
        _ = store.add_memory(
            "Atlas launch planning note.",
            importance=1.0,
            source="notes",
        )

        rows = store.search_v2(
            "project atlas launch deadline",
            limit=2,
            hybrid_weight=0.2,
        )
        assert rows
        assert rows[0].id == best_id
    finally:
        store.close()


def test_inspect_memory_candidate_detects_duplicates_and_contradictions(tmp_path):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        contradiction_id = store.add_memory("favorite color is blue", source="profile")
        duplicate_id = store.add_memory("buy oat milk every week", source="profile")

        contradiction_report = store.inspect_memory_candidate("favorite color is not blue", limit=5, fanout=50)
        contradiction_ids = [row["memory_id"] for row in contradiction_report["contradictions"]]
        assert contradiction_id in contradiction_ids

        duplicate_report = store.inspect_memory_candidate("buy oat milk every week", limit=5, fanout=50)
        duplicate_ids = [row["memory_id"] for row in duplicate_report["near_duplicates"]]
        assert duplicate_id in duplicate_ids
    finally:
        store.close()


def test_add_memory_refreshes_embedding_when_enabled(tmp_path, monkeypatch):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        store._embedding_enabled = True
        calls: list[tuple[int, str]] = []

        def _fake_refresh(memory_id: int, text: str) -> None:
            calls.append((int(memory_id), text))

        monkeypatch.setattr(store, "_refresh_embedding_for_memory", _fake_refresh)
        memory_id = store.add_memory("Lights should be warm white")
        assert calls == [(memory_id, "Lights should be warm white")]
    finally:
        store.close()


def test_search_v2_uses_vector_results_when_lexical_misses(tmp_path, monkeypatch):
    store = MemoryStore(str(tmp_path / "memory.sqlite"))
    try:
        target_id = store.add_memory("Configure evening lights to warm white.", importance=0.2)
        _ = store.add_memory("Buy paper towels this weekend.", importance=0.9)
        store._embedding_enabled = True
        target = next(entry for entry in store.recent(limit=20) if entry.id == target_id)

        def _fake_vector_search(*_args, **_kwargs):
            return [(target, 0.99)]

        monkeypatch.setattr(store, "_search_vector", _fake_vector_search)
        rows = store.search_v2("make the room cozy for movie night", limit=1, hybrid_weight=0.2)
        assert rows
        assert rows[0].id == target_id
    finally:
        store.close()
