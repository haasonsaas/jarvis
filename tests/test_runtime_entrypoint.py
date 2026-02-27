from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from jarvis.runtime_entrypoint import (
    maybe_run_backup_or_restore,
    run_jarvis_event_loop,
)


def test_maybe_run_backup_or_restore_returns_false_when_no_maintenance_args() -> None:
    args = SimpleNamespace(backup=None, restore=None, force=False)
    ran = maybe_run_backup_or_restore(
        args,
        config_class=lambda: object(),
        create_backup_bundle_fn=lambda config, path: {},
        restore_backup_bundle_fn=lambda config, path, overwrite=False: {},
    )
    assert ran is False


def test_maybe_run_backup_or_restore_backup_prints_result(capsys) -> None:
    args = SimpleNamespace(backup="/tmp/backup.zip", restore=None, force=False)
    ran = maybe_run_backup_or_restore(
        args,
        config_class=lambda: object(),
        create_backup_bundle_fn=lambda config, path: {"ok": True, "path": path},
        restore_backup_bundle_fn=lambda config, path, overwrite=False: {},
    )
    captured = capsys.readouterr()
    assert ran is True
    assert '"ok": true' in captured.out.lower()
    assert "/tmp/backup.zip" in captured.out


def test_maybe_run_backup_or_restore_failure_raises_system_exit(capsys) -> None:
    args = SimpleNamespace(backup="/tmp/backup.zip", restore=None, force=False)

    with pytest.raises(SystemExit) as exc_info:
        maybe_run_backup_or_restore(
            args,
            config_class=lambda: object(),
            create_backup_bundle_fn=lambda config, path: (_ for _ in ()).throw(RuntimeError("boom")),
            restore_backup_bundle_fn=lambda config, path, overwrite=False: {},
        )

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert '"ok": false' in captured.out.lower()
    assert "boom" in captured.out


def test_run_jarvis_event_loop_bootstraps_and_cleans_up() -> None:
    class _FakeTask:
        def __init__(self) -> None:
            self.cancelled = False

        def cancel(self) -> None:
            self.cancelled = True

    class _FakeLoop:
        def __init__(self) -> None:
            self.calls: list[object] = []
            self.task = _FakeTask()
            self.closed = False

        def create_task(self, coro):
            self.calls.append(("create_task", coro))
            return self.task

        def run_until_complete(self, awaitable):
            self.calls.append(("run_until_complete", awaitable))
            return None

        def shutdown_asyncgens(self):
            return "shutdown_asyncgens"

        def shutdown_default_executor(self):
            return "shutdown_default_executor"

        def close(self):
            self.closed = True

    fake_loop = _FakeLoop()
    jarvis = SimpleNamespace(run=lambda: "run-coro")
    signal_calls: list[tuple[object, object]] = []

    with patch("jarvis.runtime_entrypoint.asyncio.new_event_loop", return_value=fake_loop), \
         patch("jarvis.runtime_entrypoint.asyncio.set_event_loop") as set_event_loop, \
         patch("jarvis.runtime_entrypoint.signal.signal", side_effect=lambda sig, handler: signal_calls.append((sig, handler))):
        run_jarvis_event_loop(jarvis)

    set_event_loop.assert_called_once_with(fake_loop)
    assert fake_loop.closed is True
    assert any(call[0] == "create_task" for call in fake_loop.calls)
    assert len(signal_calls) >= 1
