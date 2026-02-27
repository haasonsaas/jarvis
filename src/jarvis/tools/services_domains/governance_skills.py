"""Skills governance handlers."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s

def _skills_snapshot_rows() -> list[dict[str, Any]]:
    s = _services()
    _skills_status_snapshot = s._skills_status_snapshot
    snapshot = _skills_status_snapshot()
    rows = snapshot.get("skills") if isinstance(snapshot, dict) else None
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    return []

async def skills_governance(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    Path = s.Path
    suppress = s.suppress
    json = s.json
    hashlib = s.hashlib
    hmac = s.hmac
    SKILL_SANDBOX_TEMPLATES = s.SKILL_SANDBOX_TEMPLATES
    _tool_permitted = s._tool_permitted
    _as_str_list = s._as_str_list
    _expansion_payload_response = s._expansion_payload_response
    _record_service_error = s._record_service_error
    _skill_quotas = s._skill_quotas
    _as_int = s._as_int
    _as_float = s._as_float
    _config = s._config

    start_time = time.monotonic()
    if not _tool_permitted("skills_governance"):
        record_summary("skills_governance", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "negotiate":
        requested = sorted(set(_as_str_list(args.get("requested_capabilities"), lower=True)))
        candidates: list[dict[str, Any]] = []
        for row in _skills_snapshot_rows():
            if not bool(row.get("enabled")):
                continue
            capabilities = {item.strip().lower() for item in _as_str_list(row.get("capabilities"), lower=True)}
            if requested and not set(requested).issubset(capabilities):
                continue
            score = (len(capabilities.intersection(requested)) * 10) + len(capabilities)
            candidates.append(
                {
                    "name": str(row.get("name", "")),
                    "namespace": str(row.get("namespace", "")),
                    "capabilities": sorted(capabilities),
                    "score": score,
                }
            )
        candidates.sort(key=lambda item: (-int(item["score"]), str(item["name"])))
        payload = {
            "action": action,
            "requested_capabilities": requested,
            "candidate_count": len(candidates),
            "selected": candidates[0] if candidates else None,
            "candidates": candidates[:10],
        }
        record_summary("skills_governance", "ok", start_time, effect="negotiate", risk="low")
        return _expansion_payload_response(payload)

    if action == "dependency_health":
        rows = _skills_snapshot_rows()
        loaded_names = {str(row.get("name", "")).strip().lower() for row in rows}
        health_rows: list[dict[str, Any]] = []
        for row in rows:
            source_path = str(row.get("source_path", "")).strip()
            dependencies: list[str] = []
            if source_path:
                with suppress(Exception):
                    manifest = json.loads(Path(source_path).read_text())
                    dependencies = _as_str_list((manifest if isinstance(manifest, dict) else {}).get("dependencies"), lower=True)
            missing = [dep for dep in dependencies if dep not in loaded_names]
            health_rows.append(
                {
                    "name": str(row.get("name", "")),
                    "dependencies": dependencies,
                    "missing_dependencies": missing,
                    "status": "degraded" if missing else "healthy",
                }
            )
        payload = {"action": action, "skills": health_rows, "degraded_count": sum(1 for row in health_rows if row["status"] != "healthy")}
        record_summary("skills_governance", "ok", start_time, effect="dependency_health", risk="low")
        return _expansion_payload_response(payload)

    if action == "quota_set":
        name = str(args.get("name", "")).strip().lower()
        if not name:
            _record_service_error("skills_governance", start_time, "missing_fields")
            return {"content": [{"type": "text", "text": "name is required for quota_set."}]}
        _skill_quotas[name] = {
            "rate_per_min": _as_int(args.get("rate_per_min", 60), 60, minimum=1, maximum=10_000),
            "cpu_sec": _as_float(args.get("cpu_sec", 15.0), 15.0, minimum=0.1, maximum=3600.0),
            "outbound_calls": _as_int(args.get("outbound_calls", 100), 100, minimum=0, maximum=100_000),
            "updated_at": time.time(),
        }
        payload = {"action": action, "name": name, "quota": dict(_skill_quotas[name]), "quota_count": len(_skill_quotas)}
        record_summary("skills_governance", "ok", start_time, effect="quota_set", risk="low")
        return _expansion_payload_response(payload)

    if action == "quota_get":
        name = str(args.get("name", "")).strip().lower()
        if name:
            payload = {"action": action, "name": name, "quota": dict(_skill_quotas.get(name, {}))}
        else:
            payload = {"action": action, "quota_count": len(_skill_quotas), "quotas": {k: dict(v) for k, v in sorted(_skill_quotas.items())}}
        record_summary("skills_governance", "ok", start_time, effect="quota_get", risk="low")
        return _expansion_payload_response(payload)

    if action == "quota_check":
        name = str(args.get("name", "")).strip().lower()
        usage = args.get("usage") if isinstance(args.get("usage"), dict) else {}
        quota = _skill_quotas.get(name, {})
        violations: list[str] = []
        if quota:
            if _as_int(usage.get("rate_per_min", 0), 0) > int(quota.get("rate_per_min", 0)):
                violations.append("rate_per_min")
            if _as_float(usage.get("cpu_sec", 0.0), 0.0) > float(quota.get("cpu_sec", 0.0)):
                violations.append("cpu_sec")
            if _as_int(usage.get("outbound_calls", 0), 0) > int(quota.get("outbound_calls", 0)):
                violations.append("outbound_calls")
        payload = {
            "action": action,
            "name": name,
            "quota_found": bool(quota),
            "allowed": not violations,
            "violations": violations,
            "usage": usage,
            "quota": dict(quota),
        }
        record_summary("skills_governance", "ok", start_time, effect="quota_check", risk="low")
        return _expansion_payload_response(payload)

    if action == "harness_run":
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
        payload = {"action": action, "fixture_count": len(fixtures), "passed": passed, "failed": failed, "results": results[:200]}
        record_summary("skills_governance", "ok", start_time, effect=f"harness_passed={passed}", risk="low")
        return _expansion_payload_response(payload)

    if action == "bundle_sign":
        bundle = args.get("bundle") if isinstance(args.get("bundle"), dict) else {}
        normalized = json.dumps(bundle, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        signature = ""
        signed = False
        if _config is not None and str(_config.skills_signature_key).strip():
            signature = hmac.new(str(_config.skills_signature_key).encode("utf-8"), normalized.encode("utf-8"), hashlib.sha256).hexdigest()
            signed = True
        payload = {
            "action": action,
            "signed": signed,
            "digest": digest,
            "signature": signature,
            "integrity": "hmac-sha256" if signed else "sha256-only",
        }
        record_summary("skills_governance", "ok", start_time, effect="bundle_sign", risk="low")
        return _expansion_payload_response(payload)

    if action == "sandbox_template":
        template = str(args.get("template", "")).strip().lower()
        if template:
            payload = {"action": action, "template": template, "config": dict(SKILL_SANDBOX_TEMPLATES.get(template, {}))}
        else:
            payload = {"action": action, "templates": {name: dict(cfg) for name, cfg in SKILL_SANDBOX_TEMPLATES.items()}}
        record_summary("skills_governance", "ok", start_time, effect="sandbox_template", risk="low")
        return _expansion_payload_response(payload)

    _record_service_error("skills_governance", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown skills_governance action."}]}
async def skills_list(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _skill_registry = s._skill_registry
    _record_service_error = s._record_service_error
    suppress = s.suppress
    set_runtime_skills_state = s.set_runtime_skills_state
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("skills_list"):
        record_summary("skills_list", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_list", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    with suppress(Exception):
        _skill_registry.discover()
        set_runtime_skills_state(_skill_registry.status_snapshot())
    record_summary("skills_list", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps(_skill_registry.status_snapshot(), default=str)}]}


async def skills_enable(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _skill_registry = s._skill_registry
    _record_service_error = s._record_service_error
    set_runtime_skills_state = s.set_runtime_skills_state
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("skills_enable"):
        record_summary("skills_enable", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_enable", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_enable", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required."}]}
    ok, detail = _skill_registry.enable_skill(name)
    if not ok:
        _record_service_error("skills_enable", start_time, "policy")
        return {"content": [{"type": "text", "text": f"Unable to enable skill '{name}': {detail}."}]}
    set_runtime_skills_state(_skill_registry.status_snapshot())
    record_summary("skills_enable", "ok", start_time)
    _audit("skills_enable", {"result": "ok", "name": name})
    return {"content": [{"type": "text", "text": f"Enabled skill '{name}'."}]}


async def skills_disable(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _skill_registry = s._skill_registry
    _record_service_error = s._record_service_error
    set_runtime_skills_state = s.set_runtime_skills_state
    _audit = s._audit

    start_time = time.monotonic()
    if not _tool_permitted("skills_disable"):
        record_summary("skills_disable", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_disable", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_disable", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required."}]}
    ok, detail = _skill_registry.disable_skill(name)
    if not ok:
        _record_service_error("skills_disable", start_time, "policy")
        return {"content": [{"type": "text", "text": f"Unable to disable skill '{name}': {detail}."}]}
    set_runtime_skills_state(_skill_registry.status_snapshot())
    record_summary("skills_disable", "ok", start_time)
    _audit("skills_disable", {"result": "ok", "name": name})
    return {"content": [{"type": "text", "text": f"Disabled skill '{name}'."}]}


async def skills_version(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _skill_registry = s._skill_registry
    _record_service_error = s._record_service_error
    json = s.json

    start_time = time.monotonic()
    if not _tool_permitted("skills_version"):
        record_summary("skills_version", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    if _skill_registry is None:
        _record_service_error("skills_version", start_time, "missing_store")
        return {"content": [{"type": "text", "text": "Skill registry is not available."}]}
    name = str(args.get("name", "")).strip().lower()
    if not name:
        _record_service_error("skills_version", start_time, "missing_fields")
        return {"content": [{"type": "text", "text": "name is required."}]}
    version = _skill_registry.skill_version(name)
    if version is None:
        _record_service_error("skills_version", start_time, "not_found")
        return {"content": [{"type": "text", "text": f"Skill '{name}' not found."}]}
    record_summary("skills_version", "ok", start_time)
    return {"content": [{"type": "text", "text": json.dumps({"name": name, "version": version})}]}

