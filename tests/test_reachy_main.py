"""Tests for Reachy Mini app wrapper readiness state helpers."""

from __future__ import annotations

import threading
from types import SimpleNamespace

from jarvis.main import Jarvis


def _app_stub() -> Jarvis:
    app = Jarvis.__new__(Jarvis)
    app.stop_event = threading.Event()
    return app


def test_readiness_state_tracks_startup_and_stop() -> None:
    app = _app_stub()

    assert app._readiness_state(None) == "starting"

    app.stop_event.set()
    assert app._readiness_state(None) == "stopping"


def test_readiness_state_marks_degraded_when_diagnostics_are_present() -> None:
    app = _app_stub()
    runtime = SimpleNamespace()

    assert app._readiness_state(runtime, blockers=[], diagnostics=["warn-a"]) == "degraded"


def test_readiness_state_prioritizes_blockers() -> None:
    app = _app_stub()
    runtime = SimpleNamespace()

    assert app._readiness_state(runtime, blockers=["block-a"], diagnostics=["warn-a"]) == "blocked"
