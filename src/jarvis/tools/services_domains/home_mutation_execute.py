"""Smart-home mutation execution and dry-run response."""

from __future__ import annotations

from typing import Any


def _services():
    from jarvis.tools import services as s

    return s


async def home_mutation_apply(context: dict[str, Any], *, start_time: float) -> dict[str, Any]:
    s = _services()
    record_summary = s.record_summary
    asyncio = s.asyncio
    json = s.json
    aiohttp = s.aiohttp
    log = s.log
    _config = s._config
    _record_service_error = s._record_service_error
    SENSITIVE_DOMAINS = s.SENSITIVE_DOMAINS
    _audit = s._audit
    _identity_enriched_audit = s._identity_enriched_audit
    _redact_sensitive_for_audit = s._redact_sensitive_for_audit
    _ha_headers = s._ha_headers
    _effective_act_timeout = s._effective_act_timeout
    _recovery_operation = s._recovery_operation
    _ha_invalidate_state = s._ha_invalidate_state
    _touch_action = s._touch_action
    _integration_record_success = s._integration_record_success

    from jarvis.tools.robot import tool_feedback

    domain = str(context.get("domain", "")).strip().lower()
    action = str(context.get("action", "")).strip().lower()
    entity_id = str(context.get("entity_id", "")).strip().lower()
    data = context.get("data") if isinstance(context.get("data"), dict) else {}
    dry_run = bool(context.get("dry_run", False))
    confirm = bool(context.get("confirm", False))
    safe_mode_forced = bool(context.get("safe_mode_forced", False))
    identity_context = context.get("identity_context")
    identity_chain = context.get("identity_chain") if isinstance(context.get("identity_chain"), list) else []
    current_state = str(context.get("current_state", "unknown"))

    _audit(
        "smart_home",
        _identity_enriched_audit(
            {
                "domain": domain,
                "action": action,
                "entity_id": entity_id,
                "data": _redact_sensitive_for_audit(data),
                "dry_run": dry_run,
                "confirm": confirm,
                "safe_mode_forced": safe_mode_forced,
                "state": current_state,
                "policy_decision": "dry_run" if dry_run else "allowed",
            },
            identity_context,
            [*identity_chain, "decision:dry_run" if dry_run else "decision:execute"],
        ),
    )

    if dry_run:
        tool_feedback("start")
        tool_feedback("done")
        record_summary(
            "smart_home",
            "dry_run",
            start_time,
            effect=f"no-op {domain}.{action} {entity_id}",
            risk="low",
        )
        return {
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"DRY RUN: Would call {domain}.{action} on {entity_id}"
                        f"{' with ' + json.dumps(data, default=str) if data else ''}. "
                        f"{'Safe mode forced dry-run. ' if safe_mode_forced else ''}"
                        f"Set dry_run=false to execute."
                    ),
                }
            ]
        }

    url = f"{_config.hass_url}/api/services/{domain}/{action}"
    headers = {**_ha_headers(), "Content-Type": "application/json"}
    payload = {"entity_id": entity_id, **data}
    timeout = aiohttp.ClientTimeout(total=_effective_act_timeout(10.0))
    with _recovery_operation(
        "smart_home",
        operation=f"{domain}.{action}",
        context={"entity_id": entity_id, "domain": domain},
    ) as recovery:
        try:
            tool_feedback("start")
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        tool_feedback("done")
                        _ha_invalidate_state(entity_id)
                        _touch_action(domain, action, entity_id)
                        _integration_record_success("home_assistant")
                        recovery.mark_completed(detail="ok", context={"http_status": resp.status})
                        record_summary(
                            "smart_home",
                            "ok",
                            start_time,
                            effect=f"executed {domain}.{action} {entity_id}",
                            risk="medium" if domain in SENSITIVE_DOMAINS else "low",
                        )
                        return {"content": [{"type": "text", "text": f"Done: {domain}.{action} on {entity_id}"}]}
                    if resp.status == 401:
                        tool_feedback("done")
                        recovery.mark_failed("auth", context={"http_status": resp.status})
                        _record_service_error("smart_home", start_time, "auth")
                        return {
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Home Assistant authentication failed. Check HASS_TOKEN.",
                                }
                            ]
                        }
                    if resp.status == 404:
                        tool_feedback("done")
                        recovery.mark_failed("not_found", context={"http_status": resp.status})
                        _record_service_error("smart_home", start_time, "not_found")
                        return {"content": [{"type": "text", "text": f"Service not found: {domain}.{action}"}]}
                    try:
                        text = await resp.text()
                    except Exception:
                        text = "<body unavailable>"
                    tool_feedback("done")
                    recovery.mark_failed("http_error", context={"http_status": resp.status})
                    _record_service_error("smart_home", start_time, "http_error")
                    return {"content": [{"type": "text", "text": f"Home Assistant error ({resp.status}): {text[:200]}"}]}
        except asyncio.TimeoutError:
            tool_feedback("done")
            recovery.mark_failed("timeout")
            _record_service_error("smart_home", start_time, "timeout")
            return {"content": [{"type": "text", "text": "Home Assistant request timed out."}]}
        except asyncio.CancelledError:
            tool_feedback("done")
            recovery.mark_cancelled()
            _record_service_error("smart_home", start_time, "cancelled")
            return {"content": [{"type": "text", "text": "Home Assistant request was cancelled."}]}
        except aiohttp.ClientError as e:
            tool_feedback("done")
            recovery.mark_failed("network_client_error")
            _record_service_error("smart_home", start_time, "network_client_error")
            return {"content": [{"type": "text", "text": f"Failed to reach Home Assistant: {e}"}]}
        except Exception:
            tool_feedback("done")
            recovery.mark_failed("unexpected")
            _record_service_error("smart_home", start_time, "unexpected")
            log.exception("Unexpected smart_home failure")
            return {"content": [{"type": "text", "text": "Unexpected Home Assistant error."}]}
