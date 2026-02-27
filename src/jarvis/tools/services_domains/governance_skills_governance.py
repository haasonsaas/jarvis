"""Skill governance action handlers."""

from __future__ import annotations

from typing import Any

from jarvis.tools.services_domains.governance_skills_actions_a import (
    skills_gov_dependency_health,
    skills_gov_negotiate,
)
from jarvis.tools.services_domains.governance_skills_actions_b import (
    skills_gov_quota_check,
    skills_gov_quota_get,
    skills_gov_quota_set,
)
from jarvis.tools.services_domains.governance_skills_actions_c import (
    skills_gov_bundle_sign,
    skills_gov_harness_run,
    skills_gov_sandbox_template,
)


def _services():
    from jarvis.tools import services as s

    return s


async def skills_governance(args: dict[str, Any]) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    time = s.time
    _tool_permitted = s._tool_permitted
    _record_service_error = s._record_service_error

    start_time = time.monotonic()
    if not _tool_permitted("skills_governance"):
        record_summary("skills_governance", "denied", start_time, "policy")
        return {"content": [{"type": "text", "text": "Tool not permitted."}]}
    action = str(args.get("action", "")).strip().lower()

    if action == "negotiate":
        return await skills_gov_negotiate(args, start_time=start_time)
    if action == "dependency_health":
        return await skills_gov_dependency_health(args, start_time=start_time)
    if action == "quota_set":
        return await skills_gov_quota_set(args, start_time=start_time)
    if action == "quota_get":
        return await skills_gov_quota_get(args, start_time=start_time)
    if action == "quota_check":
        return await skills_gov_quota_check(args, start_time=start_time)
    if action == "harness_run":
        return await skills_gov_harness_run(args, start_time=start_time)
    if action == "bundle_sign":
        return await skills_gov_bundle_sign(args, start_time=start_time)
    if action == "sandbox_template":
        return await skills_gov_sandbox_template(args, start_time=start_time)

    _record_service_error("skills_governance", start_time, "invalid_data")
    return {"content": [{"type": "text", "text": "Unknown skills_governance action."}]}
