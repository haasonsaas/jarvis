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
