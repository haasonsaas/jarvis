from __future__ import annotations

import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("module_name", "blocked_module"),
    [
        ("jarvis.tools.services_domains.planner_runtime", "jarvis.tools.services"),
        ("jarvis.tools.services_domains.integrations_runtime", "jarvis.tools.services"),
        ("jarvis.runtime_telemetry", "jarvis.__main__"),
        ("jarvis.runtime_state", "jarvis.__main__"),
        ("jarvis.runtime_startup", "jarvis.__main__"),
        ("jarvis.runtime_voice_profile", "jarvis.__main__"),
    ],
)
def test_runtime_module_import_boundary(module_name: str, blocked_module: str) -> None:
    code = (
        "import importlib, sys;"
        f"importlib.import_module('{module_name}');"
        f"print('loaded=' + str('{blocked_module}' in sys.modules))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "loaded=False" in proc.stdout.strip()
