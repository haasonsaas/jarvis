"""Runtime state load/apply helpers for services."""

from __future__ import annotations

import json
import time
from typing import Any

from jarvis.tools.services_runtime_state_serialize_runtime import replace_state_dict

def load_expansion_state(services_module: Any) -> None:
    s = services_module
    path = s._expansion_state_path
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        s.log.warning("Failed to load expansion state", exc_info=True)
        return
    if not isinstance(payload, dict):
        return

    proactive = payload.get("proactive_state")
    if isinstance(proactive, dict):
        pending = proactive.get("pending_follow_through")
        s._proactive_state["pending_follow_through"] = (
            [s._json_safe_clone(row) for row in pending if isinstance(row, dict)]
            if isinstance(pending, list)
            else []
        )
        s._proactive_state["digest_snoozed_until"] = s._as_float(
            proactive.get("digest_snoozed_until", 0.0),
            0.0,
            minimum=0.0,
        )
        s._proactive_state["last_briefing_at"] = s._as_float(
            proactive.get("last_briefing_at", 0.0),
            0.0,
            minimum=0.0,
        )
        s._proactive_state["last_digest_at"] = s._as_float(
            proactive.get("last_digest_at", 0.0),
            0.0,
            minimum=0.0,
        )
        s._proactive_state["nudge_decisions_total"] = s._as_int(
            proactive.get("nudge_decisions_total", 0),
            0,
            minimum=0,
        )
        s._proactive_state["nudge_interrupt_total"] = s._as_int(
            proactive.get("nudge_interrupt_total", 0),
            0,
            minimum=0,
        )
        s._proactive_state["nudge_notify_total"] = s._as_int(
            proactive.get("nudge_notify_total", 0),
            0,
            minimum=0,
        )
        s._proactive_state["nudge_defer_total"] = s._as_int(
            proactive.get("nudge_defer_total", 0),
            0,
            minimum=0,
        )
        s._proactive_state["nudge_deduped_total"] = s._as_int(
            proactive.get("nudge_deduped_total", 0),
            0,
            minimum=0,
        )
        s._proactive_state["last_nudge_decision_at"] = s._as_float(
            proactive.get("last_nudge_decision_at", 0.0),
            0.0,
            minimum=0.0,
        )
        s._proactive_state["last_nudge_dedupe_at"] = s._as_float(
            proactive.get("last_nudge_dedupe_at", 0.0),
            0.0,
            minimum=0.0,
        )
        recent_dispatches = proactive.get("nudge_recent_dispatches")
        s._proactive_state["nudge_recent_dispatches"] = []
        if isinstance(recent_dispatches, list):
            for row in recent_dispatches[-s.NUDGE_RECENT_DISPATCH_MAX :]:
                if not isinstance(row, dict):
                    continue
                fingerprint = str(row.get("fingerprint", "")).strip()
                if not fingerprint:
                    continue
                dispatched_at = s._as_float(row.get("dispatched_at", 0.0), 0.0, minimum=0.0)
                s._proactive_state["nudge_recent_dispatches"].append(
                    {"fingerprint": fingerprint, "dispatched_at": dispatched_at}
                )

    replace_state_dict(s, s._memory_partition_overlays, payload.get("memory_partition_overlays"))
    replace_state_dict(s, s._memory_quality_last, payload.get("memory_quality_last"))
    replace_state_dict(s, s._identity_trust_policies, payload.get("identity_trust_policies"))
    replace_state_dict(s, s._household_profiles, payload.get("household_profiles"))
    replace_state_dict(s, s._home_area_policies, payload.get("home_area_policies"))
    replace_state_dict(s, s._home_task_runs, payload.get("home_task_runs"))
    replace_state_dict(s, s._home_automation_drafts, payload.get("home_automation_drafts"))
    replace_state_dict(s, s._home_automation_applied, payload.get("home_automation_applied"))
    replace_state_dict(s, s._skill_quotas, payload.get("skill_quotas"))
    replace_state_dict(s, s._planner_task_graphs, payload.get("planner_task_graphs"))
    replace_state_dict(s, s._deferred_actions, payload.get("deferred_actions"))
    replace_state_dict(s, s._autonomy_checkpoints, payload.get("autonomy_checkpoints"))
    replace_state_dict(s, s._micro_expression_library, payload.get("micro_expression_library"))
    replace_state_dict(s, s._gaze_calibrations, payload.get("gaze_calibrations"))
    replace_state_dict(s, s._gesture_envelopes, payload.get("gesture_envelopes"))

    autonomy_history = payload.get("autonomy_cycle_history")
    s._autonomy_cycle_history.clear()
    if isinstance(autonomy_history, list):
        for row in autonomy_history[-s.AUTONOMY_CYCLE_HISTORY_MAX :]:
            if isinstance(row, dict):
                s._autonomy_cycle_history.append(
                    {str(key): s._json_safe_clone(value) for key, value in row.items()}
                )

    s._guest_sessions.clear()
    guest_sessions = payload.get("guest_sessions")
    if isinstance(guest_sessions, dict):
        now = time.time()
        for raw_token, raw_row in guest_sessions.items():
            token = str(raw_token).strip()
            if not token or not isinstance(raw_row, dict):
                continue
            expires_at = s._as_float(raw_row.get("expires_at", 0.0), 0.0, minimum=0.0)
            if expires_at <= now:
                continue
            issued_at = s._as_float(raw_row.get("issued_at", 0.0), 0.0, minimum=0.0)
            guest_id = str(raw_row.get("guest_id", "guest")).strip().lower() or "guest"
            capabilities = sorted(set(s._as_str_list(raw_row.get("capabilities"), lower=True)))
            s._guest_sessions[token] = {
                "token": token,
                "guest_id": guest_id,
                "capabilities": capabilities,
                "issued_at": issued_at,
                "expires_at": expires_at,
            }

    quality_rows = payload.get("quality_reports")
    s._quality_reports.clear()
    if isinstance(quality_rows, list):
        for row in quality_rows[-s.CACHED_QUALITY_REPORT_MAX :]:
            if isinstance(row, dict):
                s._quality_reports.append({str(key): s._json_safe_clone(value) for key, value in row.items()})

    privacy_posture = payload.get("privacy_posture")
    if isinstance(privacy_posture, dict):
        s._privacy_posture["state"] = str(privacy_posture.get("state", "normal")).strip().lower() or "normal"
        s._privacy_posture["reason"] = str(privacy_posture.get("reason", "startup")).strip() or "startup"
        s._privacy_posture["updated_at"] = s._as_float(
            privacy_posture.get("updated_at", 0.0),
            0.0,
            minimum=0.0,
        )

    motion_envelope = payload.get("motion_safety_envelope")
    if isinstance(motion_envelope, dict):
        s._motion_safety_envelope["proximity_limit_cm"] = s._as_float(
            motion_envelope.get(
                "proximity_limit_cm",
                s._motion_safety_envelope.get("proximity_limit_cm", 35.0),
            ),
            s._as_float(s._motion_safety_envelope.get("proximity_limit_cm", 35.0), 35.0),
            minimum=5.0,
            maximum=300.0,
        )
        s._motion_safety_envelope["max_yaw_deg"] = s._as_float(
            motion_envelope.get("max_yaw_deg", s._motion_safety_envelope.get("max_yaw_deg", 45.0)),
            s._as_float(s._motion_safety_envelope.get("max_yaw_deg", 45.0), 45.0),
            minimum=0.0,
            maximum=180.0,
        )
        s._motion_safety_envelope["max_pitch_deg"] = s._as_float(
            motion_envelope.get("max_pitch_deg", s._motion_safety_envelope.get("max_pitch_deg", 20.0)),
            s._as_float(s._motion_safety_envelope.get("max_pitch_deg", 20.0), 20.0),
            minimum=0.0,
            maximum=90.0,
        )
        s._motion_safety_envelope["max_roll_deg"] = s._as_float(
            motion_envelope.get("max_roll_deg", s._motion_safety_envelope.get("max_roll_deg", 15.0)),
            s._as_float(s._motion_safety_envelope.get("max_roll_deg", 15.0), 15.0),
            minimum=0.0,
            maximum=90.0,
        )
        s._motion_safety_envelope["hardware_state"] = (
            str(motion_envelope.get("hardware_state", "normal")).strip().lower() or "normal"
        )
        s._motion_safety_envelope["updated_at"] = s._as_float(
            motion_envelope.get("updated_at", 0.0),
            0.0,
            minimum=0.0,
        )

    release_state = payload.get("release_channel_state")
    if isinstance(release_state, dict):
        channel = str(release_state.get("active_channel", "dev")).strip().lower()
        if channel not in s.RELEASE_CHANNELS:
            channel = "dev"
        s._release_channel_state["active_channel"] = channel
        s._release_channel_state["last_check_at"] = s._as_float(
            release_state.get("last_check_at", 0.0),
            0.0,
            minimum=0.0,
        )
        s._release_channel_state["last_check_channel"] = (
            str(release_state.get("last_check_channel", channel)).strip().lower() or channel
        )
        s._release_channel_state["last_check_passed"] = bool(release_state.get("last_check_passed", False))
        migration_checks = release_state.get("migration_checks")
        s._release_channel_state["migration_checks"] = (
            [s._json_safe_clone(row) for row in migration_checks if isinstance(row, dict)]
            if isinstance(migration_checks, list)
            else []
        )

    s._home_task_seq = s._as_int(payload.get("home_task_seq", 1), 1, minimum=1)
    s._home_automation_seq = s._as_int(payload.get("home_automation_seq", 1), 1, minimum=1)
    s._planner_task_seq = s._as_int(payload.get("planner_task_seq", 1), 1, minimum=1)
    s._deferred_action_seq = s._as_int(payload.get("deferred_action_seq", 1), 1, minimum=1)
    s._prune_guest_sessions()
