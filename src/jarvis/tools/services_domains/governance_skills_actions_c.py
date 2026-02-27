"""Harness/signing/sandbox actions for skills governance."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def skills_gov_harness_run(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _expansion_payload_response = s._expansion_payload_response

    fixtures = args.get("fixtures") if isinstance(args.get("fixtures"), list) else []
    passed = 0
    failed = 0
    results: list[dict[str, Any]] = []
    for idx, row in enumerate(fixtures):
        if not isinstance(row, dict):
            failed += 1
            results.append({"index": idx, "status": "failed", "reason": "invalid_fixture"})
            continue
        expected = str(row.get("expected", "")).strip()
        actual = str(row.get("actual", "")).strip()
        name = str(row.get("name", f"fixture-{idx}")).strip()
        if expected and expected in actual:
            passed += 1
            results.append({"name": name, "status": "passed"})
        else:
            failed += 1
            results.append({"name": name, "status": "failed", "expected": expected})
    payload = {"action": "harness_run", "fixture_count": len(fixtures), "passed": passed, "failed": failed, "results": results[:200]}
    record_summary("skills_governance", "ok", start_time, effect=f"harness_passed={passed}", risk="low")
    return _expansion_payload_response(payload)


async def skills_gov_bundle_sign(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    json = s.json
    hashlib = s.hashlib
    hmac = s.hmac
    _config = s._config
    _expansion_payload_response = s._expansion_payload_response

    bundle = args.get("bundle") if isinstance(args.get("bundle"), dict) else {}
    normalized = json.dumps(bundle, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    signature = ""
    signed = False
    if _config is not None and str(_config.skills_signature_key).strip():
        signature = hmac.new(
            str(_config.skills_signature_key).encode("utf-8"),
            normalized.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        signed = True
    payload = {
        "action": "bundle_sign",
        "signed": signed,
        "digest": digest,
        "signature": signature,
        "integrity": "hmac-sha256" if signed else "sha256-only",
    }
    record_summary("skills_governance", "ok", start_time, effect="bundle_sign", risk="low")
    return _expansion_payload_response(payload)


async def skills_gov_sandbox_template(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    SKILL_SANDBOX_TEMPLATES = s.SKILL_SANDBOX_TEMPLATES
    _expansion_payload_response = s._expansion_payload_response

    template = str(args.get("template", "")).strip().lower()
    if template:
        payload = {"action": "sandbox_template", "template": template, "config": dict(SKILL_SANDBOX_TEMPLATES.get(template, {}))}
    else:
        payload = {"action": "sandbox_template", "templates": {name: dict(cfg) for name, cfg in SKILL_SANDBOX_TEMPLATES.items()}}
    record_summary("skills_governance", "ok", start_time, effect="sandbox_template", risk="low")
    return _expansion_payload_response(payload)
