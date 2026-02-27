from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.backup_restore import create_backup_bundle, restore_backup_bundle
from jarvis.config import Config
from jarvis.__main__ import parse_args

pytestmark = pytest.mark.fast


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def test_parse_args_supports_backup_and_restore_flags():
    backup = parse_args(["--backup", "/tmp/jarvis-backup.tar.gz"])
    assert backup.backup == "/tmp/jarvis-backup.tar.gz"
    assert backup.restore is None
    assert backup.force is False

    restore = parse_args(["--restore", "/tmp/jarvis-backup.tar.gz", "--force"])
    assert restore.restore == "/tmp/jarvis-backup.tar.gz"
    assert restore.backup is None
    assert restore.force is True


def test_create_backup_bundle_includes_core_state_files(tmp_path):
    memory = tmp_path / "memory.sqlite"
    runtime = tmp_path / "runtime-state.json"
    recovery = tmp_path / "recovery-journal.jsonl"
    audit = tmp_path / "audit.jsonl"
    audit_backup = tmp_path / "audit.jsonl.1"
    operator_settings = tmp_path / "operator-settings.json"
    bundle = tmp_path / "bundle.tar.gz"

    _write(memory, "memory-v1")
    _write(runtime, json.dumps({"runtime": {"safe_mode_enabled": True}, "voice": {"mode": "wake_word"}}))
    _write(recovery, '{"tool":"smart_home"}\n')
    _write(audit, '{"action":"smart_home"}\n')
    _write(audit_backup, '{"action":"smart_home_backup"}\n')
    _write(operator_settings, json.dumps({"operator_server": {"enabled": True}}))

    config = Config(
        memory_path=str(memory),
        runtime_state_path=str(runtime),
        recovery_journal_path=str(recovery),
        audit_log_backups=1,
    )
    result = create_backup_bundle(config, bundle, audit_log_path=audit)

    assert result["ok"] is True
    assert bundle.exists()
    labels = {item["label"] for item in result["included"]}
    assert "memory" in labels
    assert "runtime_state" in labels
    assert "recovery_journal" in labels
    assert "audit_log" in labels
    assert "audit_log_backup_1" in labels
    assert "operator_settings" in labels


def test_restore_backup_bundle_restores_files_with_force(tmp_path):
    memory = tmp_path / "memory.sqlite"
    runtime = tmp_path / "runtime-state.json"
    recovery = tmp_path / "recovery-journal.jsonl"
    audit = tmp_path / "audit.jsonl"
    operator_settings = tmp_path / "operator-settings.json"
    bundle = tmp_path / "bundle.tar.gz"

    _write(memory, "memory-original")
    _write(runtime, json.dumps({"runtime": {"safe_mode_enabled": True}, "voice": {"mode": "wake_word"}}))
    _write(recovery, '{"entry":"original"}\n')
    _write(audit, '{"action":"original"}\n')
    _write(operator_settings, json.dumps({"source": "original"}))

    config = Config(
        memory_path=str(memory),
        runtime_state_path=str(runtime),
        recovery_journal_path=str(recovery),
        audit_log_backups=1,
    )
    create_backup_bundle(config, bundle, audit_log_path=audit)

    _write(memory, "memory-mutated")
    _write(runtime, json.dumps({"runtime": {"safe_mode_enabled": False}}))
    _write(recovery, '{"entry":"mutated"}\n')
    _write(audit, '{"action":"mutated"}\n')
    _write(operator_settings, json.dumps({"source": "mutated"}))

    restored = restore_backup_bundle(config, bundle, overwrite=True, audit_log_path=audit)

    assert restored["ok"] is True
    assert "memory-original" == memory.read_text(encoding="utf-8")
    assert '"safe_mode_enabled": true' in runtime.read_text(encoding="utf-8").lower()
    assert '{"entry":"original"}\n' == recovery.read_text(encoding="utf-8")
    assert '{"action":"original"}\n' == audit.read_text(encoding="utf-8")
    assert json.loads(operator_settings.read_text(encoding="utf-8"))["source"] == "original"
