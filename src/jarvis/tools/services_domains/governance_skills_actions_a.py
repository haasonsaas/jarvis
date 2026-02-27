"""Negotiation and dependency actions for skills governance."""

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


async def skills_gov_negotiate(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    _as_str_list = s._as_str_list
    _expansion_payload_response = s._expansion_payload_response

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
        "action": "negotiate",
        "requested_capabilities": requested,
        "candidate_count": len(candidates),
        "selected": candidates[0] if candidates else None,
        "candidates": candidates[:10],
    }
    record_summary("skills_governance", "ok", start_time, effect="negotiate", risk="low")
    return _expansion_payload_response(payload)


async def skills_gov_dependency_health(args: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    del args

    s = _services()
    record_summary = s.record_summary
    Path = s.Path
    suppress = s.suppress
    json = s.json
    _as_str_list = s._as_str_list
    _expansion_payload_response = s._expansion_payload_response

    rows = _skills_snapshot_rows()
    loaded_names = {str(row.get("name", "")).strip().lower() for row in rows}
    health_rows: list[dict[str, Any]] = []
    for row in rows:
        source_path = str(row.get("source_path", "")).strip()
        dependencies: list[str] = []
        if source_path:
            with suppress(Exception):
                manifest = json.loads(Path(source_path).read_text())
                dependencies = _as_str_list(
                    (manifest if isinstance(manifest, dict) else {}).get("dependencies"),
                    lower=True,
                )
        missing = [dep for dep in dependencies if dep not in loaded_names]
        health_rows.append(
            {
                "name": str(row.get("name", "")),
                "dependencies": dependencies,
                "missing_dependencies": missing,
                "status": "degraded" if missing else "healthy",
            }
        )
    payload = {
        "action": "dependency_health",
        "skills": health_rows,
        "degraded_count": sum(1 for row in health_rows if row["status"] != "healthy"),
    }
    record_summary("skills_governance", "ok", start_time, effect="dependency_health", risk="low")
    return _expansion_payload_response(payload)
