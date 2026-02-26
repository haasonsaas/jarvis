from __future__ import annotations

import hashlib
import hmac
import json

from jarvis.skills import SkillRegistry


def _write_manifest(path, payload: dict):
    path.mkdir(parents=True, exist_ok=True)
    (path / "skill.json").write_text(json.dumps(payload, indent=2))


def _signature(secret: str, *, name: str, version: str, namespace: str, capabilities: list[str]) -> str:
    body = "|".join([name, version, namespace, ",".join(capabilities)]).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_skill_registry_discovers_valid_manifest(tmp_path):
    skills_dir = tmp_path / "skills"
    _write_manifest(
        skills_dir / "weather_plus",
        {
            "name": "weather_plus",
            "version": "1.2.3",
            "namespace": "skill.weather_plus",
            "capabilities": ["forecast", "alerts"],
            "allowed_network_domains": ["api.weather.test"],
            "allowed_paths": ["/tmp"],
        },
    )

    registry = SkillRegistry(skills_dir=str(skills_dir), enabled=True)
    snapshot = registry.discover()

    assert snapshot["enabled"] is True
    assert snapshot["loaded_count"] == 1
    assert snapshot["enabled_count"] == 1
    assert snapshot["skills"][0]["name"] == "weather_plus"
    assert snapshot["skills"][0]["namespace"] == "skill.weather_plus"


def test_skill_registry_blocks_when_not_allowlisted(tmp_path):
    skills_dir = tmp_path / "skills"
    _write_manifest(
        skills_dir / "music",
        {
            "name": "music",
            "version": "0.1.0",
            "namespace": "skill.music",
        },
    )

    registry = SkillRegistry(skills_dir=str(skills_dir), allowlist=["weather_plus"], enabled=True)
    snapshot = registry.discover()
    skill = snapshot["skills"][0]

    assert skill["status"] == "blocked"
    assert skill["load_error"] == "not_allowlisted"
    assert snapshot["enabled_count"] == 0


def test_skill_registry_signature_requirement(tmp_path):
    skills_dir = tmp_path / "skills"
    secret = "skill-secret"
    name = "lighting"
    version = "2.0.0"
    namespace = "skill.lighting"
    capabilities = ["dim", "scene"]
    sig = _signature(secret, name=name, version=version, namespace=namespace, capabilities=capabilities)

    _write_manifest(
        skills_dir / "lighting",
        {
            "name": name,
            "version": version,
            "namespace": namespace,
            "capabilities": capabilities,
            "signature": sig,
        },
    )

    registry = SkillRegistry(
        skills_dir=str(skills_dir),
        enabled=True,
        require_signature=True,
        signature_key=secret,
    )
    snapshot = registry.discover()

    assert snapshot["loaded_count"] == 1
    assert snapshot["enabled_count"] == 1
    assert snapshot["skills"][0]["signature_valid"] is True


def test_skill_registry_enable_disable(tmp_path):
    skills_dir = tmp_path / "skills"
    _write_manifest(
        skills_dir / "planner",
        {
            "name": "planner",
            "version": "1.0.0",
            "namespace": "skill.planner",
        },
    )

    registry = SkillRegistry(skills_dir=str(skills_dir), enabled=True)
    registry.discover()

    ok, detail = registry.disable_skill("planner")
    assert ok is True
    assert detail == "disabled"
    assert registry.status_snapshot()["enabled_count"] == 0

    ok, detail = registry.enable_skill("planner")
    assert ok is True
    assert detail == "enabled"
    assert registry.status_snapshot()["enabled_count"] == 1

    # Persisted lifecycle state should survive a new registry instance.
    second = SkillRegistry(skills_dir=str(skills_dir), enabled=True)
    second.discover()
    assert second.status_snapshot()["enabled_count"] == 1
