"""Contract checks for the Reachy Mini app package layout."""

from __future__ import annotations

from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_root_assets_exist() -> None:
    assert (ROOT / "index.html").exists()
    assert (ROOT / "style.css").exists()


def test_readme_contains_reachy_metadata() -> None:
    content = (ROOT / "README.md").read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "title: Jarvis" in content
    assert " - reachy_mini\n" in content
    assert " - reachy_mini_python_app\n" in content


def test_pyproject_registers_reachy_app_entrypoint() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    entry_points = pyproject["project"]["entry-points"]["reachy_mini_apps"]
    assert entry_points["jarvis"] == "jarvis.main:Jarvis"


def test_main_module_declares_reachy_app_class() -> None:
    content = (ROOT / "src" / "jarvis" / "main.py").read_text(encoding="utf-8")
    assert "class Jarvis(ReachyMiniApp)" in content
