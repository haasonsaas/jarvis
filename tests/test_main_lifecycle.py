"""Lifecycle robustness tests for jarvis.__main__.Jarvis."""

import json
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock, patch

from jarvis.__main__ import Jarvis, TELEMETRY_SERVICE_ERROR_DETAILS, TELEMETRY_STORAGE_ERROR_DETAILS
from jarvis.presence import State
from jarvis.voice_attention import VoiceAttentionConfig, VoiceAttentionController


def test_stop_is_noop_when_not_started():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._started = False
    Jarvis.stop(jarvis)  # should not raise


def test_stop_suppresses_component_errors_and_resets_started():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._started = True
    jarvis._output_stream = MagicMock()
    jarvis._output_stream.stop.side_effect = RuntimeError("stream stop failed")
    jarvis._output_stream.close.side_effect = RuntimeError("stream close failed")
    jarvis.face_tracker = MagicMock()
    jarvis.face_tracker.stop.side_effect = RuntimeError("face stop failed")
    jarvis.hand_tracker = MagicMock()
    jarvis.hand_tracker.stop.side_effect = RuntimeError("hand stop failed")
    jarvis._use_robot_audio = True
    jarvis.robot = MagicMock()
    jarvis.robot.stop_audio.side_effect = RuntimeError("audio stop failed")
    jarvis.robot.disconnect.side_effect = RuntimeError("disconnect failed")
    jarvis.presence = MagicMock()
    jarvis.presence.stop.side_effect = RuntimeError("presence stop failed")
    jarvis.config = SimpleNamespace(motion_enabled=True)

    Jarvis.stop(jarvis)
    assert jarvis._started is False
    assert jarvis._output_stream is None
    assert jarvis.face_tracker is None
    assert jarvis.hand_tracker is None


@pytest.mark.asyncio
async def test_run_cleans_up_when_start_fails():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis.start = MagicMock(side_effect=RuntimeError("start failed"))
    jarvis.stop = MagicMock()
    jarvis._listen_task = None
    jarvis._tts_task = None
    jarvis._filler_task = None
    jarvis.brain = MagicMock()
    jarvis.brain.close = AsyncMock()

    with pytest.raises(RuntimeError):
        await Jarvis.run(jarvis)

    jarvis.brain.close.assert_awaited_once()
    jarvis.stop.assert_called_once()


def test_startup_summary_lines_include_core_status():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis.robot = SimpleNamespace(sim=True)
    jarvis.args = SimpleNamespace(no_vision=False)
    jarvis.tts = None
    jarvis.config = SimpleNamespace(
        motion_enabled=True,
        hand_track_enabled=False,
        home_enabled=True,
        home_conversation_enabled=False,
        memory_enabled=True,
        memory_path="/tmp/memory.sqlite",
        persona_style="composed",
        startup_warnings=[],
        tool_allowlist=["a"],
        tool_denylist=["b", "c"],
    )

    lines = Jarvis._startup_summary_lines(jarvis)
    joined = "\n".join(lines)
    assert "Mode: simulation" in joined
    assert "Memory: enabled" in joined
    assert "Config warnings: 0" in joined
    assert "Tool policy: allow=1 deny=2" in joined
    assert "Error taxonomy: total=" in joined


def test_parse_memory_correction_command_forget():
    command = Jarvis._parse_memory_correction_command("forget memory 42")
    assert command == ("memory_forget", {"memory_id": 42})


def test_parse_memory_correction_command_update():
    command = Jarvis._parse_memory_correction_command("update memory 7 to Call me Captain.")
    assert command == ("memory_update", {"memory_id": 7, "text": "Call me Captain."})


def test_parse_memory_correction_command_rejects_ambiguous_phrases():
    assert Jarvis._parse_memory_correction_command("forget this") is None


def test_classify_user_intent():
    assert Jarvis._classify_user_intent("What time is it?") == "answer"
    assert Jarvis._classify_user_intent("Turn on the kitchen lights.") == "action"
    assert Jarvis._classify_user_intent("Can you turn on the lights and tell me the weather?") == "hybrid"


def test_looks_like_user_correction():
    assert Jarvis._looks_like_user_correction("Actually, I meant the bedroom lamp.") is True
    assert Jarvis._looks_like_user_correction("No, I meant tomorrow morning.") is True
    assert Jarvis._looks_like_user_correction("What time is it?") is False


def test_followup_carryover_candidate_accepts_short_slot_reply_when_previous_request_unresolved():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._followup_carryover = {
        "text": "Turn on the lights in the living room.",
        "intent": "action",
        "timestamp": 100.0,
        "unresolved": True,
    }

    assert Jarvis._is_followup_carryover_candidate(jarvis, "the bedroom", now_ts=130.0) is True


def test_followup_carryover_candidate_rejects_explicit_new_action():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._followup_carryover = {
        "text": "Turn on the lights in the living room.",
        "intent": "action",
        "timestamp": 100.0,
        "unresolved": True,
    }

    assert Jarvis._is_followup_carryover_candidate(jarvis, "turn on the kitchen lights", now_ts=130.0) is False


def test_with_followup_carryover_augments_prompt_for_unresolved_followup():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._followup_carryover = {
        "text": "Set the bedroom lights to warm white.",
        "intent": "action",
        "timestamp": 200.0,
        "unresolved": True,
    }

    augmented, applied = Jarvis._with_followup_carryover(jarvis, "and in the office", now_ts=220.0)
    assert applied is True
    assert "Follow-up intent carryover:" in augmented
    assert "Previous request: Set the bedroom lights to warm white." in augmented
    assert "unresolved slots" in augmented


def test_with_followup_carryover_skips_acknowledgement_only_replies():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._followup_carryover = {
        "text": "Set the bedroom lights to warm white.",
        "intent": "action",
        "timestamp": 200.0,
        "unresolved": True,
    }

    augmented, applied = Jarvis._with_followup_carryover(jarvis, "okay", now_ts=220.0)
    assert applied is False
    assert augmented == "okay"


def test_update_followup_carryover_tracks_resolution_status():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._followup_carryover = {}

    Jarvis._update_followup_carryover(jarvis, "Turn on the porch light.", "action", resolved=False, now_ts=300.0)
    assert jarvis._followup_carryover["unresolved"] is True
    assert jarvis._followup_carryover["intent"] == "action"
    assert jarvis._followup_carryover["timestamp"] == 300.0

    Jarvis._update_followup_carryover(jarvis, "Turn on the porch light.", "action", resolved=True, now_ts=320.0)
    assert jarvis._followup_carryover["unresolved"] is False

    Jarvis._update_followup_carryover(jarvis, "What is the weather?", "answer", resolved=None, now_ts=340.0)
    assert jarvis._followup_carryover["unresolved"] is False
    assert jarvis._followup_carryover["intent"] == "answer"


def test_apply_turn_choreography_sets_presence_bias_fields():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis.presence = SimpleNamespace(signals=SimpleNamespace(turn_lean=0.0, turn_tilt=0.0, turn_glance_yaw=0.0))
    jarvis._turn_choreography = {}
    jarvis._observability = None

    Jarvis._apply_turn_choreography(jarvis, State.THINKING)
    assert jarvis.presence.signals.turn_lean == 0.5
    assert jarvis.presence.signals.turn_tilt == 2.0
    assert jarvis.presence.signals.turn_glance_yaw == 8.0

    snapshot = Jarvis._turn_choreography_snapshot(jarvis)
    assert snapshot["phase"] == "thinking"
    assert snapshot["label"] == "think_glance_away"


def test_publish_voice_status_includes_turn_choreography():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._voice_attention = VoiceAttentionController(VoiceAttentionConfig(wake_words=["jarvis"]))
    jarvis.presence = SimpleNamespace(signals=SimpleNamespace(state=State.LISTENING))
    jarvis._turn_choreography = {}
    jarvis._observability = None

    with patch("jarvis.__main__.set_runtime_voice_state") as set_runtime:
        Jarvis._publish_voice_status(jarvis)

    payload = set_runtime.call_args.args[0]
    assert payload["presence_state"] == "listening"
    assert payload["turn_choreography"]["phase"] == "listening"
    assert payload["turn_choreography"]["label"] == "listen_lean_in"
    assert "stt_diagnostics" in payload
    assert payload["stt_diagnostics"]["confidence_band"] == "unknown"


def test_start_requires_sounddevice_for_local_tts_playback():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._started = False
    jarvis.robot = SimpleNamespace(connect=MagicMock(), sim=True)
    jarvis.presence = SimpleNamespace(start=MagicMock())
    jarvis.config = SimpleNamespace(
        motion_enabled=False,
        sample_rate=16000,
    )
    jarvis.args = SimpleNamespace(no_vision=True)
    jarvis.tts = object()
    jarvis.stop = MagicMock()

    with patch("jarvis.__main__.sd", None), patch("jarvis.__main__._SOUNDDEVICE_IMPORT_ERROR", "PortAudio missing"):
        with pytest.raises(RuntimeError, match="local audio playback"):
            Jarvis.start(jarvis)

    jarvis.stop.assert_called_once()


def test_error_taxonomy_doc_matches_constants():
    from jarvis.tool_errors import TOOL_SERVICE_ERROR_CODES

    doc_path = Path(__file__).resolve().parents[1] / "docs" / "operations" / "error-taxonomy.md"
    text = doc_path.read_text(encoding="utf-8")
    start = "<!-- SERVICE_ERROR_CODES_START -->"
    end = "<!-- SERVICE_ERROR_CODES_END -->"
    assert start in text and end in text

    block = text.split(start, 1)[1].split(end, 1)[0]
    documented = {line.strip() for line in block.splitlines() if line.strip()}
    assert documented == TOOL_SERVICE_ERROR_CODES


def test_telemetry_snapshot_averages():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._telemetry = {
        "turns": 10.0,
        "barge_ins": 2.0,
        "stt_latency_total_ms": 1000.0,
        "stt_latency_count": 4.0,
        "llm_first_sentence_total_ms": 1200.0,
        "llm_first_sentence_count": 3.0,
        "tts_first_audio_total_ms": 500.0,
        "tts_first_audio_count": 2.0,
        "service_errors": 3.0,
        "storage_errors": 1.0,
        "fallback_responses": 4.0,
    }
    snapshot = Jarvis._telemetry_snapshot(jarvis)
    assert snapshot["turns"] == 10.0
    assert snapshot["barge_ins"] == 2.0
    assert snapshot["avg_stt_latency_ms"] == 250.0
    assert snapshot["avg_llm_first_sentence_ms"] == 400.0
    assert snapshot["avg_tts_first_audio_ms"] == 250.0
    assert snapshot["service_errors"] == 3.0
    assert snapshot["storage_errors"] == 1.0
    assert snapshot["unknown_summary_details"] == 0.0
    assert snapshot["fallback_responses"] == 4.0
    intent = snapshot["intent_metrics"]
    assert intent["answer_quality_success_rate"] == 0.0
    assert intent["completion_success_rate"] == 0.0
    assert intent["correction_frequency"] == 0.0


def test_telemetry_snapshot_intent_metric_rates():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._telemetry = {
        "intent_turns_total": 10.0,
        "intent_answer_turns": 4.0,
        "intent_action_turns": 3.0,
        "intent_hybrid_turns": 3.0,
        "intent_answer_total": 8.0,
        "intent_answer_success": 6.0,
        "intent_completion_total": 5.0,
        "intent_completion_success": 4.0,
        "intent_corrections": 2.0,
    }
    jarvis._telemetry_error_counts = {}

    snapshot = Jarvis._telemetry_snapshot(jarvis)
    intent = snapshot["intent_metrics"]
    assert intent["turn_count"] == 10.0
    assert intent["answer_intent_count"] == 4.0
    assert intent["action_intent_count"] == 3.0
    assert intent["hybrid_intent_count"] == 3.0
    assert intent["answer_sample_count"] == 8.0
    assert intent["completion_sample_count"] == 5.0
    assert intent["answer_quality_success_rate"] == pytest.approx(0.75)
    assert intent["completion_success_rate"] == pytest.approx(0.8)
    assert intent["correction_count"] == 2.0
    assert intent["correction_frequency"] == pytest.approx(0.2)


def test_refresh_tool_error_counters():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._telemetry = {"service_errors": 0.0, "storage_errors": 0.0}
    from unittest.mock import patch

    with patch("jarvis.__main__.list_summaries", return_value=[
        {"status": "error", "detail": "timeout"},
        {"status": "error", "detail": "storage_error"},
        {"status": "ok", "detail": "noop"},
    ]):
        Jarvis._refresh_tool_error_counters(jarvis)

    assert jarvis._telemetry["service_errors"] == 1.0
    assert jarvis._telemetry["storage_errors"] == 1.0
    assert jarvis._telemetry["unknown_summary_details"] == 0.0


def test_refresh_tool_error_counters_classifies_missing_store_as_storage():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._telemetry = {"service_errors": 0.0, "storage_errors": 0.0}
    from unittest.mock import patch

    with patch("jarvis.__main__.list_summaries", return_value=[
        {"status": "error", "detail": "missing_store"},
        {"status": "error", "detail": "storage_error"},
        {"status": "error", "detail": "invalid_plan"},
    ]):
        Jarvis._refresh_tool_error_counters(jarvis)

    assert jarvis._telemetry["service_errors"] == 1.0
    assert jarvis._telemetry["storage_errors"] == 2.0
    assert jarvis._telemetry["unknown_summary_details"] == 0.0


def test_refresh_tool_error_counters_includes_network_taxonomy():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._telemetry = {"service_errors": 0.0, "storage_errors": 0.0}
    from unittest.mock import patch

    with patch("jarvis.__main__.list_summaries", return_value=[
        {"status": "error", "detail": "network_client_error"},
        {"status": "error", "detail": "http_error"},
        {"status": "error", "detail": "unknown_error"},
    ]):
        Jarvis._refresh_tool_error_counters(jarvis)

    assert jarvis._telemetry["service_errors"] == 3.0
    assert jarvis._telemetry["storage_errors"] == 0.0
    assert jarvis._telemetry["unknown_summary_details"] == 0.0


def test_refresh_tool_error_counters_tracks_unknown_summary_detail_count():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._telemetry = {"service_errors": 0.0, "storage_errors": 0.0, "unknown_summary_details": 0.0}
    from unittest.mock import patch

    with patch("jarvis.__main__.list_summaries", return_value=[
        {"status": "error", "detail": "timeout"},
        {"status": "error", "detail": "not_a_real_code"},
        {"status": "error", "detail": "another_unknown"},
    ]):
        Jarvis._refresh_tool_error_counters(jarvis)

    assert jarvis._telemetry["service_errors"] == 1.0
    assert jarvis._telemetry["storage_errors"] == 0.0
    assert jarvis._telemetry["unknown_summary_details"] == 2.0


def test_refresh_tool_error_counters_reports_per_code_totals():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._telemetry = {"service_errors": 0.0, "storage_errors": 0.0, "unknown_summary_details": 0.0}
    from unittest.mock import patch

    with patch("jarvis.__main__.list_summaries", return_value=[
        {"status": "error", "detail": "timeout"},
        {"status": "error", "detail": "timeout"},
        {"status": "error", "detail": "storage_error"},
        {"status": "error", "detail": "unknown_error"},
        {"status": "error", "detail": "not_a_real_code"},
        {"status": "ok", "detail": "timeout"},
    ]):
        Jarvis._refresh_tool_error_counters(jarvis)

    assert jarvis._telemetry_error_counts == {
        "storage_error": 1.0,
        "timeout": 2.0,
        "unknown_error": 1.0,
    }

    snapshot = Jarvis._telemetry_snapshot(jarvis)
    assert snapshot["service_error_counts"] == jarvis._telemetry_error_counts
    assert snapshot["unknown_summary_details"] == 1.0


def test_telemetry_snapshot_guards_non_finite_values():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._telemetry = {
        "turns": float("nan"),
        "barge_ins": float("inf"),
        "stt_latency_total_ms": float("inf"),
        "stt_latency_count": 1.0,
        "llm_first_sentence_total_ms": 100.0,
        "llm_first_sentence_count": float("nan"),
        "tts_first_audio_total_ms": 100.0,
        "tts_first_audio_count": 0.0,
        "service_errors": float("nan"),
        "storage_errors": float("inf"),
        "unknown_summary_details": float("nan"),
        "fallback_responses": float("inf"),
    }
    jarvis._telemetry_error_counts = {"timeout": float("nan"), "auth": 2.0}

    snapshot = Jarvis._telemetry_snapshot(jarvis)
    assert snapshot["turns"] == 0.0
    assert snapshot["barge_ins"] == 0.0
    assert snapshot["avg_stt_latency_ms"] == 0.0
    assert snapshot["avg_llm_first_sentence_ms"] == 0.0
    assert snapshot["service_errors"] == 0.0
    assert snapshot["storage_errors"] == 0.0
    assert snapshot["unknown_summary_details"] == 0.0
    assert snapshot["fallback_responses"] == 0.0
    assert snapshot["service_error_counts"] == {"auth": 2.0}


def test_telemetry_error_taxonomy_matches_service_error_codes():
    from jarvis.tools.services import SERVICE_ERROR_CODES
    from jarvis.tool_errors import TOOL_STORAGE_ERROR_DETAILS

    assert TELEMETRY_STORAGE_ERROR_DETAILS == TOOL_STORAGE_ERROR_DETAILS
    assert TELEMETRY_STORAGE_ERROR_DETAILS.issubset(SERVICE_ERROR_CODES)
    assert TELEMETRY_SERVICE_ERROR_DETAILS == (SERVICE_ERROR_CODES - TELEMETRY_STORAGE_ERROR_DETAILS)


@pytest.mark.asyncio
async def test_operator_control_handler_validates_and_applies_runtime_controls():
    jarvis = Jarvis.__new__(Jarvis)
    jarvis._voice_attention = VoiceAttentionController(VoiceAttentionConfig(wake_words=["jarvis"]))
    jarvis._publish_voice_status = MagicMock()
    jarvis._publish_skills_status = MagicMock()
    jarvis._save_runtime_state = MagicMock()
    jarvis._tts_output_enabled = True
    jarvis.config = SimpleNamespace(
        motion_enabled=True,
        home_enabled=True,
        safe_mode_enabled=False,
        persona_style="composed",
        backchannel_style="balanced",
    )
    jarvis.presence = SimpleNamespace(
        start=MagicMock(),
        stop=MagicMock(),
        set_backchannel_style=MagicMock(),
    )
    jarvis.brain = SimpleNamespace(_memory=None)
    jarvis._skills = SimpleNamespace(
        discover=MagicMock(),
        status_snapshot=lambda: {"enabled": True},
        enable_skill=lambda name: (True, f"enabled:{name}"),
        disable_skill=lambda name: (True, f"disabled:{name}"),
    )

    invalid_mode = await Jarvis._operator_control_handler(
        jarvis,
        "set_wake_mode",
        {"mode": "invalid"},
    )
    assert invalid_mode["ok"] is False
    assert invalid_mode["error"] == "invalid_payload"

    tts_result = await Jarvis._operator_control_handler(
        jarvis,
        "set_tts_enabled",
        {"enabled": "false"},
    )
    assert tts_result == {"ok": True, "tts_enabled": False}
    assert jarvis._tts_output_enabled is False

    invalid_bool = await Jarvis._operator_control_handler(
        jarvis,
        "set_home_enabled",
        {"enabled": "maybe"},
    )
    assert invalid_bool["ok"] is False
    assert invalid_bool["error"] == "invalid_payload"

    with patch("jarvis.__main__.service_tools.set_safe_mode") as set_safe_mode:
        safe_mode_result = await Jarvis._operator_control_handler(
            jarvis,
            "set_safe_mode",
            {"enabled": True},
        )
    assert safe_mode_result == {"ok": True, "safe_mode_enabled": True}
    assert jarvis.config.safe_mode_enabled is True
    set_safe_mode.assert_called_once_with(True)

    persona_result = await Jarvis._operator_control_handler(
        jarvis,
        "set_persona_style",
        {"style": "friendly"},
    )
    assert persona_result == {"ok": True, "persona_style": "friendly"}
    assert jarvis.config.persona_style == "friendly"

    sleep_result = await Jarvis._operator_control_handler(
        jarvis,
        "set_sleeping",
        {"sleeping": True},
    )
    assert sleep_result == {"ok": True, "sleeping": True}
    assert jarvis._voice_attention.sleeping is True

    wake_result = await Jarvis._operator_control_handler(
        jarvis,
        "set_sleeping",
        {"sleeping": False},
    )
    assert wake_result == {"ok": True, "sleeping": False}
    assert jarvis._voice_attention.sleeping is False

    backchannel_result = await Jarvis._operator_control_handler(
        jarvis,
        "set_backchannel_style",
        {"style": "quiet"},
    )
    assert backchannel_result == {"ok": True, "backchannel_style": "quiet"}
    assert jarvis.config.backchannel_style == "quiet"
    jarvis.presence.set_backchannel_style.assert_called_with("quiet")

    unknown = await Jarvis._operator_control_handler(jarvis, "nope", {})
    assert unknown["ok"] is False
    assert unknown["error"] == "invalid_action"
    assert "available_actions" in unknown
    assert "set_sleeping" in unknown["available_actions"]
    assert "set_safe_mode" in unknown["available_actions"]


def test_runtime_state_persists_and_restores_runtime_controls(tmp_path):
    state_path = tmp_path / "runtime-state.json"

    save_target = Jarvis.__new__(Jarvis)
    save_target._runtime_state_path = state_path
    save_target._voice_attention = VoiceAttentionController(VoiceAttentionConfig(wake_words=["jarvis"]))
    save_target._voice_attention.set_mode("wake_word")
    save_target._voice_attention.set_timeout_profile("long")
    save_target._voice_attention.set_push_to_talk_active(True)
    save_target._voice_attention.sleeping = True
    save_target.config = SimpleNamespace(
        motion_enabled=False,
        home_enabled=False,
        safe_mode_enabled=True,
        persona_style="friendly",
        backchannel_style="expressive",
    )
    save_target._tts_output_enabled = False
    save_target._awaiting_confirmation = True
    save_target._pending_text = "arm the system"
    Jarvis._save_runtime_state(save_target)

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["runtime"]["motion_enabled"] is False
    assert payload["runtime"]["home_enabled"] is False
    assert payload["runtime"]["safe_mode_enabled"] is True
    assert payload["runtime"]["tts_enabled"] is False
    assert payload["runtime"]["persona_style"] == "friendly"
    assert payload["runtime"]["backchannel_style"] == "expressive"

    load_target = Jarvis.__new__(Jarvis)
    load_target._runtime_state_path = state_path
    load_target._voice_attention = VoiceAttentionController(VoiceAttentionConfig(wake_words=["jarvis"]))
    load_target.config = SimpleNamespace(
        motion_enabled=True,
        home_enabled=True,
        safe_mode_enabled=False,
        persona_style="composed",
        backchannel_style="balanced",
    )
    load_target.brain = SimpleNamespace(_memory=None)
    load_target.presence = SimpleNamespace(set_backchannel_style=MagicMock())
    load_target._tts_output_enabled = True
    load_target._awaiting_confirmation = False
    load_target._pending_text = None
    with patch("jarvis.__main__.service_tools.set_safe_mode") as set_safe_mode:
        Jarvis._load_runtime_state(load_target)
    set_safe_mode.assert_called_once_with(True)

    assert load_target._voice_attention.mode == "wake_word"
    assert load_target._voice_attention.timeout_profile == "long"
    assert load_target._voice_attention.push_to_talk_active is True
    assert load_target._voice_attention.sleeping is True
    assert load_target.config.motion_enabled is False
    assert load_target.config.home_enabled is False
    assert load_target.config.safe_mode_enabled is True
    assert load_target._tts_output_enabled is False
    assert load_target.config.persona_style == "friendly"
    assert load_target.config.backchannel_style == "expressive"
    assert load_target._awaiting_confirmation is True
    assert load_target._pending_text == "arm the system"
    load_target.presence.set_backchannel_style.assert_called_with("expressive")
