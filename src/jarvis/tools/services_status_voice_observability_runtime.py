"""Voice, observability, and skills status snapshot helpers."""

from __future__ import annotations

from typing import Any

def voice_attention_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    default_choreography = {
        "phase": "idle",
        "label": "idle_reset",
        "turn_lean": 0.0,
        "turn_tilt": 0.0,
        "turn_glance_yaw": 0.0,
        "updated_at": 0.0,
    }
    default_stt_diagnostics = {
        "source": "none",
        "fallback_used": False,
        "confidence_score": 0.0,
        "confidence_band": "unknown",
        "avg_logprob": -3.0,
        "avg_no_speech_prob": 1.0,
        "language": "unknown",
        "language_probability": 0.0,
        "segment_count": 0,
        "word_count": 0,
        "char_count": 0,
        "updated_at": 0.0,
        "error": "",
    }
    default_acoustic_scene = {
        "last_doa_angle": None,
        "last_doa_speech": None,
        "last_doa_age_sec": 0.0,
        "attention_confidence": 0.0,
        "attention_source": "unknown",
    }
    default_preference_learning = {
        "user": "",
        "updates": {},
        "applied_at": 0.0,
        "source_text": "",
    }
    default_multimodal_grounding = {
        "overall_confidence": 0.0,
        "confidence_band": "low",
        "attention_source": "unknown",
        "modality_scores": {"presence": 0.0, "stt": 0.0, "source": 0.0, "doa": 0.0},
        "signals": {
            "face_recent": False,
            "hand_recent": False,
            "doa_recent": False,
            "doa_speech": None,
            "stt_band": "unknown",
        },
        "reasons": ["unknown"],
    }
    if not s._runtime_voice_state:
        return {
            "mode": "unknown",
            "followup_active": False,
            "sleeping": False,
            "active_room": "unknown",
            "silence_timeout_sec": 0.0,
            "adaptive_silence_timeout_sec": 0.0,
            "speech_rate_wps": 0.0,
            "interruption_likelihood": 0.0,
            "turn_choreography": default_choreography,
            "stt_diagnostics": default_stt_diagnostics,
            "voice_profile_user": "unknown",
            "voice_profile": {"verbosity": "normal", "confirmations": "standard", "pace": "normal", "tone": "auto"},
            "voice_profile_count": 0,
            "acoustic_scene": default_acoustic_scene,
            "preference_learning": default_preference_learning,
            "multimodal_grounding": default_multimodal_grounding,
        }
    snapshot = {str(key): value for key, value in s._runtime_voice_state.items()}
    snapshot.setdefault("silence_timeout_sec", 0.0)
    snapshot.setdefault("adaptive_silence_timeout_sec", float(snapshot.get("silence_timeout_sec", 0.0) or 0.0))
    snapshot.setdefault("speech_rate_wps", 0.0)
    snapshot.setdefault("interruption_likelihood", 0.0)
    if not isinstance(snapshot.get("turn_choreography"), dict):
        snapshot["turn_choreography"] = default_choreography
    if not isinstance(snapshot.get("stt_diagnostics"), dict):
        snapshot["stt_diagnostics"] = default_stt_diagnostics
    else:
        stt_diag = {str(key): value for key, value in snapshot["stt_diagnostics"].items()}
        for key, value in default_stt_diagnostics.items():
            stt_diag.setdefault(key, value)
        snapshot["stt_diagnostics"] = stt_diag
    snapshot.setdefault("voice_profile_user", "unknown")
    if not isinstance(snapshot.get("voice_profile"), dict):
        snapshot["voice_profile"] = {
            "verbosity": "normal",
            "confirmations": "standard",
            "pace": "normal",
            "tone": "auto",
        }
    else:
        profile = {str(key): value for key, value in snapshot["voice_profile"].items()}
        profile.setdefault("verbosity", "normal")
        profile.setdefault("confirmations", "standard")
        profile.setdefault("pace", "normal")
        profile.setdefault("tone", "auto")
        snapshot["voice_profile"] = profile
    snapshot.setdefault("voice_profile_count", 0)
    if not isinstance(snapshot.get("acoustic_scene"), dict):
        snapshot["acoustic_scene"] = default_acoustic_scene
    else:
        acoustic_scene = {
            str(key): value for key, value in snapshot["acoustic_scene"].items()
        }
        for key, value in default_acoustic_scene.items():
            acoustic_scene.setdefault(key, value)
        snapshot["acoustic_scene"] = acoustic_scene
    if not isinstance(snapshot.get("preference_learning"), dict):
        snapshot["preference_learning"] = default_preference_learning
    else:
        preference_learning = {
            str(key): value
            for key, value in snapshot["preference_learning"].items()
        }
        for key, value in default_preference_learning.items():
            preference_learning.setdefault(key, value)
        if not isinstance(preference_learning.get("updates"), dict):
            preference_learning["updates"] = {}
        snapshot["preference_learning"] = preference_learning
    if not isinstance(snapshot.get("multimodal_grounding"), dict):
        snapshot["multimodal_grounding"] = default_multimodal_grounding
    else:
        multimodal_grounding = {
            str(key): value for key, value in snapshot["multimodal_grounding"].items()
        }
        for key, value in default_multimodal_grounding.items():
            multimodal_grounding.setdefault(key, value)
        if not isinstance(multimodal_grounding.get("modality_scores"), dict):
            multimodal_grounding["modality_scores"] = dict(
                default_multimodal_grounding["modality_scores"]
            )
        if not isinstance(multimodal_grounding.get("signals"), dict):
            multimodal_grounding["signals"] = dict(
                default_multimodal_grounding["signals"]
            )
        reasons = multimodal_grounding.get("reasons")
        if not isinstance(reasons, list):
            multimodal_grounding["reasons"] = ["unknown"]
        snapshot["multimodal_grounding"] = multimodal_grounding
    return snapshot


def observability_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    default_intent_metrics = {
        "turn_count": 0.0,
        "answer_intent_count": 0.0,
        "action_intent_count": 0.0,
        "hybrid_intent_count": 0.0,
        "answer_sample_count": 0.0,
        "completion_sample_count": 0.0,
        "answer_quality_success_rate": 0.0,
        "completion_success_rate": 0.0,
        "correction_count": 0.0,
        "correction_frequency": 0.0,
        "preference_update_turns": 0.0,
        "preference_update_fields": 0.0,
    }
    default_multimodal_metrics = {
        "turn_count": 0.0,
        "avg_confidence": 0.0,
        "low_confidence_count": 0.0,
        "low_confidence_rate": 0.0,
    }
    if not s._runtime_observability_state:
        return {
            "enabled": False,
            "uptime_sec": 0.0,
            "restart_count": 0,
            "alerts": [],
            "intent_metrics": default_intent_metrics,
            "multimodal_metrics": default_multimodal_metrics,
            "latency_dashboards": {
                "sample_count": 0,
                "overall_total_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
                "by_intent": {},
                "by_tool_mix": {},
                "by_wake_mode": {},
            },
            "policy_decision_analytics": {
                "decision_count": 0,
                "by_tool": {},
                "by_status": {},
                "by_reason": {},
                "by_user": {},
                "by_user_tool": {},
            },
            "router_canary_analytics": {
                "sample_count": 0,
                "router_decision_count": 0,
                "canary_turn_count": 0,
                "canary_coverage": 0.0,
                "fallback_count": 0,
                "shadow_compare_count": 0,
                "shadow_agreement_count": 0,
                "shadow_disagreement_count": 0,
                "shadow_agreement_rate": 0.0,
                "recent_disagreements": [],
            },
            "budget_metrics": {
                "window_sec": 3600.0,
                "sample_count": 0,
                "latency_p95_ms": {
                    "stt_ms": 0.0,
                    "llm_first_sentence_ms": 0.0,
                    "tts_first_audio_ms": 0.0,
                },
                "tokens_per_hour": 0.0,
                "cost_usd_per_hour": 0.0,
            },
        }
    snapshot = {str(key): value for key, value in s._runtime_observability_state.items()}
    if not isinstance(snapshot.get("intent_metrics"), dict):
        snapshot["intent_metrics"] = default_intent_metrics
    else:
        intent_metrics = {
            str(key): value for key, value in snapshot["intent_metrics"].items()
        }
        for key, value in default_intent_metrics.items():
            intent_metrics.setdefault(key, value)
        snapshot["intent_metrics"] = intent_metrics
    if not isinstance(snapshot.get("multimodal_metrics"), dict):
        snapshot["multimodal_metrics"] = default_multimodal_metrics
    else:
        multimodal_metrics = {
            str(key): value for key, value in snapshot["multimodal_metrics"].items()
        }
        for key, value in default_multimodal_metrics.items():
            multimodal_metrics.setdefault(key, value)
        snapshot["multimodal_metrics"] = multimodal_metrics
    if not isinstance(snapshot.get("latency_dashboards"), dict):
        snapshot["latency_dashboards"] = {
            "sample_count": 0,
            "overall_total_ms": {"p50": 0.0, "p95": 0.0, "p99": 0.0},
            "by_intent": {},
            "by_tool_mix": {},
            "by_wake_mode": {},
        }
    if not isinstance(snapshot.get("policy_decision_analytics"), dict):
        snapshot["policy_decision_analytics"] = {
            "decision_count": 0,
            "by_tool": {},
            "by_status": {},
            "by_reason": {},
            "by_user": {},
            "by_user_tool": {},
        }
    if not isinstance(snapshot.get("router_canary_analytics"), dict):
        snapshot["router_canary_analytics"] = {
            "sample_count": 0,
            "router_decision_count": 0,
            "canary_turn_count": 0,
            "canary_coverage": 0.0,
            "fallback_count": 0,
            "shadow_compare_count": 0,
            "shadow_agreement_count": 0,
            "shadow_disagreement_count": 0,
            "shadow_agreement_rate": 0.0,
            "recent_disagreements": [],
        }
    if not isinstance(snapshot.get("budget_metrics"), dict):
        snapshot["budget_metrics"] = {
            "window_sec": 3600.0,
            "sample_count": 0,
            "latency_p95_ms": {
                "stt_ms": 0.0,
                "llm_first_sentence_ms": 0.0,
                "tts_first_audio_ms": 0.0,
            },
            "tokens_per_hour": 0.0,
            "cost_usd_per_hour": 0.0,
        }
    return snapshot


def skills_status_snapshot(services_module: Any) -> dict[str, Any]:
    s = services_module
    if not s._runtime_skills_state:
        if s._skill_registry is not None:
            return s._skill_registry.status_snapshot()
        return {
            "enabled": False,
            "loaded_count": 0,
            "enabled_count": 0,
            "skills": [],
        }
    return {str(key): value for key, value in s._runtime_skills_state.items()}

