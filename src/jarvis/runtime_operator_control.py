"""Operator control action dispatcher for the Jarvis runtime."""

from __future__ import annotations

import json
from contextlib import suppress
from typing import Any

from jarvis.runtime_constants import (
    VALID_BACKCHANNEL_STYLES,
    VALID_CONTROL_PRESETS,
    VALID_PERSONA_STYLES,
    VALID_VOICE_PROFILE_CONFIRMATIONS,
    VALID_VOICE_PROFILE_PACE,
    VALID_VOICE_PROFILE_TONE,
    VALID_VOICE_PROFILE_VERBOSITY,
)
from jarvis.tools import services as service_tools
from jarvis.voice_attention import VALID_TIMEOUT_PROFILES, VALID_WAKE_MODES


def _tool_json_payload(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return {}
    first = content[0] if isinstance(content[0], dict) else {}
    text = first.get("text")
    if not isinstance(text, str):
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {"raw_text": text}
    return payload if isinstance(payload, dict) else {"value": payload}


async def handle_operator_control(runtime: Any, action: str, payload: dict[str, Any]) -> dict[str, Any]:
    voice = runtime._voice_controller()
    command = str(action or "").strip().lower()
    data = payload if isinstance(payload, dict) else {}
    if not command:
        return {
            "ok": False,
            "error": "invalid_action",
            "message": "action is required",
            "available_actions": runtime._operator_available_actions(),
        }
    if command == "set_wake_mode":
        mode = runtime._parse_control_choice(data.get("mode"), VALID_WAKE_MODES)
        if mode is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "field": "mode",
                "expected": sorted(VALID_WAKE_MODES),
            }
        mode = voice.set_mode(mode)
        runtime._active_control_preset = "custom"
        runtime._publish_voice_status()
        runtime._persist_runtime_state_safe()
        return {"ok": True, "mode": mode}
    if command == "set_sleeping":
        sleeping = runtime._parse_control_bool(data.get("sleeping"))
        if sleeping is None:
            return {"ok": False, "error": "invalid_payload", "field": "sleeping", "expected": "boolean"}
        voice.sleeping = sleeping
        if not sleeping:
            voice.continue_listening()
        runtime._active_control_preset = "custom"
        runtime._publish_voice_status()
        runtime._persist_runtime_state_safe()
        return {"ok": True, "sleeping": voice.sleeping}
    if command == "set_timeout_profile":
        profile = runtime._parse_control_choice(data.get("profile"), VALID_TIMEOUT_PROFILES)
        if profile is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "field": "profile",
                "expected": sorted(VALID_TIMEOUT_PROFILES),
            }
        profile = voice.set_timeout_profile(profile)
        runtime._active_control_preset = "custom"
        runtime._publish_voice_status()
        runtime._persist_runtime_state_safe()
        return {"ok": True, "timeout_profile": profile}
    if command == "set_push_to_talk":
        active = runtime._parse_control_bool(data.get("active"))
        if active is None:
            return {"ok": False, "error": "invalid_payload", "field": "active", "expected": "boolean"}
        voice.set_push_to_talk_active(active)
        runtime._active_control_preset = "custom"
        runtime._publish_voice_status()
        runtime._persist_runtime_state_safe()
        return {"ok": True, "push_to_talk_active": active}
    if command == "set_motion_enabled":
        enabled = runtime._parse_control_bool(data.get("enabled"))
        if enabled is None:
            return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
        runtime.config.motion_enabled = enabled
        if enabled:
            with suppress(Exception):
                runtime.presence.start()
        else:
            with suppress(Exception):
                runtime.presence.stop()
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {"ok": True, "motion_enabled": enabled}
    if command == "set_home_enabled":
        enabled = runtime._parse_control_bool(data.get("enabled"))
        if enabled is None:
            return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
        runtime.config.home_enabled = enabled
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {"ok": True, "home_enabled": enabled}
    if command == "set_safe_mode":
        enabled = runtime._parse_control_bool(data.get("enabled"))
        if enabled is None:
            return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
        runtime.config.safe_mode_enabled = enabled
        service_tools.set_safe_mode(enabled)
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {"ok": True, "safe_mode_enabled": enabled}
    if command == "set_tts_enabled":
        enabled = runtime._parse_control_bool(data.get("enabled"))
        if enabled is None:
            return {"ok": False, "error": "invalid_payload", "field": "enabled", "expected": "boolean"}
        runtime._tts_output_enabled = enabled
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {"ok": True, "tts_enabled": enabled}
    if command == "set_persona_style":
        style = runtime._parse_control_choice(data.get("style"), VALID_PERSONA_STYLES)
        if style is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "field": "style",
                "expected": sorted(VALID_PERSONA_STYLES),
            }
        runtime._set_persona_style(style)
        runtime._personality_preview_snapshot = None
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {"ok": True, "persona_style": style}
    if command == "set_backchannel_style":
        style = runtime._parse_control_choice(data.get("style"), VALID_BACKCHANNEL_STYLES)
        if style is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "field": "style",
                "expected": sorted(VALID_BACKCHANNEL_STYLES),
            }
        runtime.config.backchannel_style = style
        runtime.presence.set_backchannel_style(style)
        runtime._personality_preview_snapshot = None
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {"ok": True, "backchannel_style": style}
    if command == "set_voice_profile":
        user = str(data.get("user", "")).strip().lower()
        if not user:
            return {"ok": False, "error": "invalid_payload", "field": "user", "expected": "non-empty string"}
        verbosity = runtime._parse_control_choice(data.get("verbosity"), VALID_VOICE_PROFILE_VERBOSITY)
        confirmations = runtime._parse_control_choice(data.get("confirmations"), VALID_VOICE_PROFILE_CONFIRMATIONS)
        pace = runtime._parse_control_choice(data.get("pace"), VALID_VOICE_PROFILE_PACE)
        tone = runtime._parse_control_choice(data.get("tone"), VALID_VOICE_PROFILE_TONE)
        profile_patch: dict[str, str] = {}
        if "verbosity" in data:
            if verbosity is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "verbosity",
                    "expected": sorted(VALID_VOICE_PROFILE_VERBOSITY),
                }
            profile_patch["verbosity"] = verbosity
        if "confirmations" in data:
            if confirmations is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "confirmations",
                    "expected": sorted(VALID_VOICE_PROFILE_CONFIRMATIONS),
                }
            profile_patch["confirmations"] = confirmations
        if "pace" in data:
            if pace is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "pace",
                    "expected": sorted(VALID_VOICE_PROFILE_PACE),
                }
            profile_patch["pace"] = pace
        if "tone" in data:
            if tone is None:
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "tone",
                    "expected": sorted(VALID_VOICE_PROFILE_TONE),
                }
            profile_patch["tone"] = tone
        if not profile_patch:
            return {
                "ok": False,
                "error": "invalid_payload",
                "message": "provide at least one of verbosity, confirmations, pace, or tone",
            }
        profiles = getattr(runtime, "_voice_user_profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
        entry = profiles.get(user, {})
        if not isinstance(entry, dict):
            entry = {}
        merged = {**entry, **profile_patch}
        profiles[user] = merged
        runtime._voice_user_profiles = profiles
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        runtime._publish_voice_status()
        return {"ok": True, "user": user, "profile": merged}
    if command == "clear_voice_profile":
        user = str(data.get("user", "")).strip().lower()
        if not user:
            return {"ok": False, "error": "invalid_payload", "field": "user", "expected": "non-empty string"}
        profiles = getattr(runtime, "_voice_user_profiles", {})
        removed = False
        if isinstance(profiles, dict) and user in profiles:
            profiles.pop(user, None)
            removed = True
        runtime._voice_user_profiles = profiles if isinstance(profiles, dict) else {}
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        runtime._publish_voice_status()
        return {"ok": True, "user": user, "removed": removed}
    if command == "list_voice_profiles":
        profiles = getattr(runtime, "_voice_user_profiles", {})
        snapshot = {
            str(name): dict(value)
            for name, value in profiles.items()
            if isinstance(value, dict)
        } if isinstance(profiles, dict) else {}
        active_user = runtime._active_voice_user()
        return {
            "ok": True,
            "active_user": active_user,
            "active_profile": runtime._active_voice_profile(user=active_user),
            "profiles": snapshot,
        }
    if command == "apply_control_preset":
        preset = runtime._parse_control_choice(data.get("preset"), VALID_CONTROL_PRESETS)
        if preset is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "field": "preset",
                "expected": sorted(VALID_CONTROL_PRESETS),
            }
        applied = runtime._apply_control_preset(preset)
        if applied is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "field": "preset",
                "expected": sorted(VALID_CONTROL_PRESETS),
            }
        return {"ok": True, "preset": preset, "runtime_profile": applied}
    if command == "export_runtime_profile":
        return {"ok": True, "runtime_profile": runtime._runtime_profile_snapshot()}
    if command == "import_runtime_profile":
        profile = data.get("profile")
        if not isinstance(profile, dict):
            return {"ok": False, "error": "invalid_payload", "field": "profile", "expected": "object"}
        applied = runtime._apply_runtime_profile(profile, mark_custom=True)
        return {"ok": True, "runtime_profile": applied}
    if command == "preview_personality":
        persona_style = runtime._parse_control_choice(data.get("persona_style"), VALID_PERSONA_STYLES)
        backchannel_style = runtime._parse_control_choice(data.get("backchannel_style"), VALID_BACKCHANNEL_STYLES)
        if persona_style is None and backchannel_style is None:
            return {
                "ok": False,
                "error": "invalid_payload",
                "message": "provide persona_style and/or backchannel_style",
                "expected": {
                    "persona_style": sorted(VALID_PERSONA_STYLES),
                    "backchannel_style": sorted(VALID_BACKCHANNEL_STYLES),
                },
            }
        if getattr(runtime, "_personality_preview_snapshot", None) is None:
            runtime._personality_preview_snapshot = {
                "persona_style": str(getattr(runtime.config, "persona_style", "composed")),
                "backchannel_style": str(getattr(runtime.config, "backchannel_style", "balanced")),
            }
        if persona_style is not None:
            runtime._set_persona_style(persona_style)
        if backchannel_style is not None:
            runtime.config.backchannel_style = backchannel_style
            runtime.presence.set_backchannel_style(backchannel_style)
        runtime._active_control_preset = "custom"
        return {
            "ok": True,
            "preview_active": True,
            "persona_style": str(getattr(runtime.config, "persona_style", "unknown")),
            "backchannel_style": str(getattr(runtime.config, "backchannel_style", "unknown")),
            "baseline": dict(runtime._personality_preview_snapshot or {}),
        }
    if command == "commit_personality_preview":
        was_active = isinstance(getattr(runtime, "_personality_preview_snapshot", None), dict)
        runtime._personality_preview_snapshot = None
        runtime._active_control_preset = "custom"
        runtime._persist_runtime_state_safe()
        return {
            "ok": True,
            "committed": was_active,
            "preview_active": False,
            "persona_style": str(getattr(runtime.config, "persona_style", "unknown")),
            "backchannel_style": str(getattr(runtime.config, "backchannel_style", "unknown")),
        }
    if command == "rollback_personality_preview":
        snapshot = getattr(runtime, "_personality_preview_snapshot", None)
        if not isinstance(snapshot, dict):
            return {
                "ok": True,
                "rolled_back": False,
                "preview_active": False,
                "persona_style": str(getattr(runtime.config, "persona_style", "unknown")),
                "backchannel_style": str(getattr(runtime.config, "backchannel_style", "unknown")),
            }
        persona_style = runtime._parse_control_choice(snapshot.get("persona_style"), VALID_PERSONA_STYLES)
        backchannel_style = runtime._parse_control_choice(snapshot.get("backchannel_style"), VALID_BACKCHANNEL_STYLES)
        if persona_style is not None:
            runtime._set_persona_style(persona_style)
        if backchannel_style is not None:
            runtime.config.backchannel_style = backchannel_style
            runtime.presence.set_backchannel_style(backchannel_style)
        runtime._personality_preview_snapshot = None
        runtime._active_control_preset = "custom"
        return {
            "ok": True,
            "rolled_back": True,
            "preview_active": False,
            "persona_style": str(getattr(runtime.config, "persona_style", "unknown")),
            "backchannel_style": str(getattr(runtime.config, "backchannel_style", "unknown")),
        }
    if command == "clear_inbound_webhooks":
        result = await service_tools.webhook_inbound_clear({})
        text = result.get("content", [{}])[0].get("text", "")
        return {"ok": True, "message": text}
    if command == "list_pending_approvals":
        try:
            limit = int(data.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(200, limit))
        result = await service_tools.home_orchestrator(
            {"action": "approval_list", "status_filter": "pending", "limit": limit}
        )
        payload_data = _tool_json_payload(result)
        return {
            "ok": True,
            "pending_count": int(payload_data.get("pending_count", 0) or 0),
            "approvals": payload_data.get("approvals", []),
            "status_counts": payload_data.get("status_counts", {}),
        }
    if command == "resolve_approval":
        approval_id = str(data.get("approval_id", "")).strip().lower()
        if not approval_id:
            return {"ok": False, "error": "invalid_payload", "field": "approval_id", "expected": "non-empty string"}
        approved = runtime._parse_control_bool(data.get("approved"))
        if approved is None:
            return {"ok": False, "error": "invalid_payload", "field": "approved", "expected": "boolean"}
        notes = str(data.get("notes", "")).strip()
        operator_identity = str(data.get("__operator_identity", "")).strip().lower()
        resolver_id = operator_identity or "operator"
        resolve_result = await service_tools.home_orchestrator(
            {
                "action": "approval_resolve",
                "approval_id": approval_id,
                "approved": approved,
                "notes": notes,
                "resolver_id": resolver_id,
                "__operator_identity": resolver_id,
            }
        )
        resolve_payload = _tool_json_payload(resolve_result)
        execute_now = runtime._parse_control_bool(data.get("execute"))
        execution_payload: dict[str, Any] | None = None
        if bool(approved) and bool(execute_now):
            execution_ticket = str(resolve_payload.get("execution_ticket", "")).strip()
            step_up_token = str(resolve_payload.get("step_up_token", "")).strip()
            if not execution_ticket:
                return {
                    "ok": False,
                    "error": "execution_ticket_missing",
                    "message": "approved execution requires execution_ticket from approval resolution",
                    "approval": resolve_payload,
                }
            execute_result = await service_tools.home_orchestrator(
                {
                    "action": "execute",
                    "approval_id": approval_id,
                    "execution_ticket": execution_ticket,
                    "resolver_id": resolver_id,
                    "requester_id": resolver_id,
                    "__operator_identity": resolver_id,
                    "dry_run": False,
                    "confirm": True,
                    "step_up_token": step_up_token,
                }
            )
            execution_payload = _tool_json_payload(execute_result)
        return {
            "ok": bool(resolve_payload.get("resolved", False)),
            "approval": resolve_payload,
            "execution": execution_payload,
        }
    if command == "dead_letter_status":
        try:
            limit = int(data.get("limit", 20))
        except (TypeError, ValueError):
            limit = 20
        limit = max(1, min(200, limit))
        status_filter = str(data.get("status_filter", "open")).strip().lower() or "open"
        result = await service_tools.dead_letter_list({"limit": limit, "status": status_filter})
        payload_data = _tool_json_payload(result)
        return {"ok": True, "dead_letter_queue": payload_data}
    if command == "dead_letter_replay":
        try:
            limit = int(data.get("limit", 10))
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(50, limit))
        status_filter = str(data.get("status_filter", "open")).strip().lower() or "open"
        entry_id = str(data.get("entry_id", "")).strip()
        args_payload: dict[str, Any] = {"limit": limit, "status": status_filter}
        if entry_id:
            args_payload["entry_id"] = entry_id
        dry_run = runtime._parse_control_bool(data.get("dry_run"))
        if isinstance(dry_run, bool):
            args_payload["dry_run"] = dry_run
        result = await service_tools.dead_letter_replay(args_payload)
        payload_data = _tool_json_payload(result)
        ok = int(payload_data.get("failed_count", 0) or 0) == 0
        return {"ok": ok, "dead_letter_replay": payload_data}
    if command == "list_autonomy_replans":
        try:
            limit = int(data.get("limit", 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(200, limit))
        result = await service_tools.planner_engine({"action": "autonomy_status"})
        payload_data = _tool_json_payload(result)
        rows = payload_data.get("task_progress")
        task_rows = rows if isinstance(rows, list) else []
        replans = [
            row
            for row in task_rows
            if isinstance(row, dict)
            and (
                bool(row.get("needs_replan", False))
                or str(row.get("status", "")).strip().lower() == "needs_replan"
            )
        ][:limit]
        draft_payload: dict[str, Any] = {}
        try:
            draft_result = await service_tools.planner_engine(
                {"action": "autonomy_replan_list", "limit": limit}
            )
            draft_payload = _tool_json_payload(draft_result)
        except Exception:
            draft_payload = {}
        return {
            "ok": True,
            "needs_replan_count": int(payload_data.get("needs_replan_count", 0) or 0),
            "retry_pending_count": int(payload_data.get("retry_pending_count", 0) or 0),
            "failure_taxonomy": (
                payload_data.get("failure_taxonomy")
                if isinstance(payload_data.get("failure_taxonomy"), dict)
                else {}
            ),
            "tasks": replans,
            "draft_count": int(draft_payload.get("draft_count", 0) or 0),
            "drafts": draft_payload.get("drafts", []) if isinstance(draft_payload.get("drafts"), list) else [],
        }
    if command == "apply_autonomy_replan":
        task_id = str(data.get("task_id", "")).strip()
        if not task_id:
            return {"ok": False, "error": "invalid_payload", "field": "task_id", "expected": "non-empty string"}
        operator_identity = str(data.get("__operator_identity", "")).strip().lower()
        resolver_id = operator_identity or str(data.get("resolver_id", "")).strip().lower() or "operator"
        args_payload: dict[str, Any] = {
            "action": "autonomy_replan",
            "task_id": task_id,
            "resolver_id": resolver_id,
            "notes": str(data.get("notes", "")).strip(),
        }
        draft_id = str(data.get("draft_id", "")).strip().lower()
        if draft_id:
            args_payload["draft_id"] = draft_id
        if "execute_at" in data:
            try:
                args_payload["execute_at"] = float(data.get("execute_at"))
            except (TypeError, ValueError):
                return {"ok": False, "error": "invalid_payload", "field": "execute_at", "expected": "number"}
        if "reset_progress" in data:
            reset_progress = runtime._parse_control_bool(data.get("reset_progress"))
            if reset_progress is None:
                return {"ok": False, "error": "invalid_payload", "field": "reset_progress", "expected": "boolean"}
            args_payload["reset_progress"] = reset_progress
        if "plan_steps" in data:
            plan_steps = data.get("plan_steps")
            if not isinstance(plan_steps, list):
                return {"ok": False, "error": "invalid_payload", "field": "plan_steps", "expected": "array"}
            args_payload["plan_steps"] = plan_steps
        if "step_contracts" in data:
            step_contracts = data.get("step_contracts")
            if not isinstance(step_contracts, list):
                return {"ok": False, "error": "invalid_payload", "field": "step_contracts", "expected": "array"}
            if not all(isinstance(item, dict) for item in step_contracts):
                return {
                    "ok": False,
                    "error": "invalid_payload",
                    "field": "step_contracts",
                    "expected": "array<object>",
                }
            args_payload["step_contracts"] = step_contracts
        result = await service_tools.planner_engine(args_payload)
        payload_data = _tool_json_payload(result)
        ok = str(payload_data.get("action", "")).strip().lower() == "autonomy_replan"
        if not ok and "raw_text" in payload_data:
            return {
                "ok": False,
                "error": "autonomy_replan_failed",
                "message": str(payload_data.get("raw_text", "")).strip(),
                "autonomy_replan": payload_data,
            }
        return {"ok": ok, "autonomy_replan": payload_data}
    if command == "copilot_actions":
        status_result = await service_tools.system_status({})
        status_payload = _tool_json_payload(status_result)
        expansion = status_payload.get("expansion") if isinstance(status_payload.get("expansion"), dict) else {}
        proactive = expansion.get("proactive") if isinstance(expansion.get("proactive"), dict) else {}
        planner = expansion.get("planner_engine") if isinstance(expansion.get("planner_engine"), dict) else {}
        dead_letter = (
            status_payload.get("dead_letter_queue")
            if isinstance(status_payload.get("dead_letter_queue"), dict)
            else {}
        )
        suggestions: list[dict[str, Any]] = []
        if int(proactive.get("approval_pending_count", 0) or 0) > 0:
            suggestions.append(
                {
                    "action_id": "pending_approvals",
                    "severity": "high",
                    "title": "Review pending approvals",
                    "command": "list_pending_approvals",
                    "payload": {"limit": 25},
                }
            )
        if int(planner.get("autonomy_needs_replan_count", 0) or 0) > 0:
            suggestions.append(
                {
                    "action_id": "autonomy_replans",
                    "severity": "high",
                    "title": "Review autonomy replans",
                    "command": "list_autonomy_replans",
                    "payload": {"limit": 50},
                }
            )
        if int(dead_letter.get("pending_count", 0) or 0) > 0:
            suggestions.append(
                {
                    "action_id": "dead_letter_replay_dry_run",
                    "severity": "medium",
                    "title": "Dry-run dead-letter replay",
                    "command": "dead_letter_replay",
                    "payload": {"status_filter": "open", "limit": 10, "dry_run": True},
                }
            )
        slo = planner.get("autonomy_slo") if isinstance(planner.get("autonomy_slo"), dict) else {}
        if int(slo.get("alert_count", 0) or 0) > 0:
            suggestions.append(
                {
                    "action_id": "autonomy_slo_alerts",
                    "severity": "high",
                    "title": "Inspect autonomy SLO alerts",
                    "command": "list_autonomy_replans",
                    "payload": {"limit": 50},
                }
            )
        if not suggestions:
            suggestions.append(
                {
                    "action_id": "healthy",
                    "severity": "low",
                    "title": "No urgent copilot actions",
                    "command": "system_status",
                    "payload": {},
                }
            )
        return {"ok": True, "actions": suggestions}
    if command == "copilot_execute":
        action_id = str(data.get("action_id", "")).strip().lower()
        if not action_id:
            return {"ok": False, "error": "invalid_payload", "field": "action_id", "expected": "non-empty string"}
        suggestions = await handle_operator_control(runtime, "copilot_actions", {})
        rows = suggestions.get("actions") if isinstance(suggestions, dict) else []
        if not isinstance(rows, list):
            rows = []
        selected = next(
            (
                row
                for row in rows
                if isinstance(row, dict) and str(row.get("action_id", "")).strip().lower() == action_id
            ),
            None,
        )
        if not isinstance(selected, dict):
            return {"ok": False, "error": "not_found", "message": f"Unknown copilot action_id: {action_id}"}
        target_command = str(selected.get("command", "")).strip().lower()
        payload_override = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        target_payload = dict(selected.get("payload", {})) if isinstance(selected.get("payload"), dict) else {}
        target_payload.update(payload_override)
        if target_command == "system_status":
            status_result = await service_tools.system_status({})
            return {"ok": True, "result": _tool_json_payload(status_result)}
        if target_command == "list_pending_approvals":
            return await handle_operator_control(runtime, "list_pending_approvals", target_payload)
        if target_command == "list_autonomy_replans":
            return await handle_operator_control(runtime, "list_autonomy_replans", target_payload)
        if target_command == "dead_letter_replay":
            return await handle_operator_control(runtime, "dead_letter_replay", target_payload)
        return {
            "ok": False,
            "error": "unsupported_action",
            "message": f"Copilot action '{target_command}' is not executable.",
        }
    if command == "skills_reload":
        runtime._skills.discover()
        runtime._publish_skills_status()
        return {"ok": True, "skills": runtime._skills.status_snapshot()}
    if command == "skills_enable":
        name = str(data.get("name", "")).strip().lower()
        if not name:
            return {"ok": False, "error": "invalid_payload", "field": "name", "expected": "non-empty string"}
        ok, detail = runtime._skills.enable_skill(name)
        runtime._publish_skills_status()
        return {"ok": ok, "detail": detail, "name": name}
    if command == "skills_disable":
        name = str(data.get("name", "")).strip().lower()
        if not name:
            return {"ok": False, "error": "invalid_payload", "field": "name", "expected": "non-empty string"}
        ok, detail = runtime._skills.disable_skill(name)
        runtime._publish_skills_status()
        return {"ok": ok, "detail": detail, "name": name}
    return {
        "ok": False,
        "error": "invalid_action",
        "message": "unknown action",
        "available_actions": runtime._operator_available_actions(),
    }
