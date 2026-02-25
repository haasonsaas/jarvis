"""Tests for jarvis.memory."""

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
