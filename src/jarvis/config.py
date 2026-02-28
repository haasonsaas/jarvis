import math
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if val is None or not val.strip():
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return val.strip()


def _require_openai_api_key() -> str:
    return _require_env("OPENAI_API_KEY")


def _env_bool(name: str) -> bool | None:
    val = os.environ.get(name)
    if val is None:
        return None
    normalized = val.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None or not val.strip():
        return default
    try:
        parsed = float(val)
    except ValueError:
        return default
    if not math.isfinite(parsed):
        return default
    return parsed


def _env_positive_float(name: str, default: float) -> float:
    parsed = _env_float(name, default)
    if parsed <= 0.0:
        return default
    return parsed


def _env_nonnegative_float(name: str, default: float) -> float:
    parsed = _env_float(name, default)
    if parsed < 0.0:
        return default
    return parsed


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    if val is None or not val.strip():
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _env_list(name: str) -> list[str]:
    val = os.environ.get(name)
    if not val:
        return []
    return [item.strip() for item in val.split(",") if item.strip()]


def _env_key_value_map(name: str) -> dict[str, str]:
    val = os.environ.get(name)
    if not val:
        return {}
    mapping: dict[str, str] = {}
    for item in val.split(","):
        part = item.strip()
        if not part or "=" not in part:
            continue
        key_raw, value_raw = part.split("=", 1)
        key = key_raw.strip().lower()
        value = value_raw.strip().lower()
        if not key or not value:
            continue
        mapping[key] = value
    return mapping


def _env_is_set(name: str) -> bool:
    val = os.environ.get(name)
    return val is not None and bool(val.strip())


@dataclass
class Config:
    # OpenAI model API key.
    openai_api_key: str = field(default_factory=_require_openai_api_key)
    openai_model: str = field(default_factory=lambda: os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"))
    llm_cost_input_per_1k_tokens: float = field(
        default_factory=lambda: _env_nonnegative_float("LLM_COST_INPUT_PER_1K_TOKENS", 0.0)
    )
    llm_cost_output_per_1k_tokens: float = field(
        default_factory=lambda: _env_nonnegative_float("LLM_COST_OUTPUT_PER_1K_TOKENS", 0.0)
    )
    openai_router_model: str = field(default_factory=lambda: os.environ.get("OPENAI_ROUTER_MODEL", ""))
    openai_router_shadow_model: str = field(default_factory=lambda: os.environ.get("OPENAI_ROUTER_SHADOW_MODEL", ""))
    router_shadow_enabled: bool = field(default_factory=lambda: _env_bool("ROUTER_SHADOW_ENABLED") or False)
    router_canary_percent: float = field(default_factory=lambda: _env_float("ROUTER_CANARY_PERCENT", 0.0))
    router_timeout_sec: float = field(default_factory=lambda: _env_positive_float("ROUTER_TIMEOUT_SEC", 2.0))
    policy_router_min_confidence: float = field(
        default_factory=lambda: _env_float("POLICY_ROUTER_MIN_CONFIDENCE", 0.55)
    )
    interruption_router_timeout_sec: float = field(
        default_factory=lambda: _env_positive_float("INTERRUPTION_ROUTER_TIMEOUT_SEC", 1.5)
    )
    interruption_resume_min_confidence: float = field(
        default_factory=lambda: _env_float("INTERRUPTION_RESUME_MIN_CONFIDENCE", 0.6)
    )
    semantic_turn_enabled: bool = field(default_factory=lambda: _env_bool("SEMANTIC_TURN_ENABLED") is not False)
    semantic_turn_router_timeout_sec: float = field(
        default_factory=lambda: _env_positive_float("SEMANTIC_TURN_ROUTER_TIMEOUT_SEC", 0.8)
    )
    semantic_turn_min_confidence: float = field(
        default_factory=lambda: _env_float("SEMANTIC_TURN_MIN_CONFIDENCE", 0.6)
    )
    semantic_turn_extension_sec: float = field(
        default_factory=lambda: _env_positive_float("SEMANTIC_TURN_EXTENSION_SEC", 0.6)
    )
    semantic_turn_max_transcript_chars: int = field(
        default_factory=lambda: _env_int("SEMANTIC_TURN_MAX_TRANSCRIPT_CHARS", 220)
    )

    # ElevenLabs TTS
    elevenlabs_api_key: str = field(default_factory=lambda: os.environ.get("ELEVENLABS_API_KEY", ""))
    elevenlabs_voice_id: str = field(default_factory=lambda: os.environ.get("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB"))

    # Home Assistant
    hass_url: str = field(default_factory=lambda: os.environ.get("HASS_URL", ""))
    hass_token: str = field(default_factory=lambda: os.environ.get("HASS_TOKEN", ""))

    # Reachy Mini
    reachy_host: str | None = field(default_factory=lambda: os.environ.get("REACHY_MINI_HOST"))
    reachy_connection_mode: str | None = field(default_factory=lambda: os.environ.get("REACHY_CONNECTION_MODE"))
    reachy_media_backend: str | None = field(default_factory=lambda: os.environ.get("REACHY_MEDIA_BACKEND"))
    reachy_automatic_body_yaw: bool | None = field(default_factory=lambda: _env_bool("REACHY_AUTOMATIC_BODY_YAW"))

    # Audio — 16kHz is required by Silero VAD (fixed chunk size of 512 samples)
    vad_threshold: float = 0.5
    whisper_model: str = "base.en"
    sample_rate: int = 16000
    doa_change_threshold: float = field(default_factory=lambda: _env_float("DOA_CHANGE_THRESHOLD", 0.04))
    doa_timeout: float = field(default_factory=lambda: _env_float("DOA_TIMEOUT", 1.0))
    wake_mode: str = field(default_factory=lambda: os.environ.get("WAKE_MODE", "always_listening"))
    wake_calibration_profile: str = field(default_factory=lambda: os.environ.get("WAKE_CALIBRATION_PROFILE", "default"))
    wake_words: list[str] = field(default_factory=lambda: _env_list("WAKE_WORDS") or ["jarvis"])
    wake_word_sensitivity: float = field(default_factory=lambda: _env_float("WAKE_WORD_SENSITIVITY", 0.82))
    voice_followup_window_sec: float = field(default_factory=lambda: _env_positive_float("VOICE_FOLLOWUP_WINDOW_SEC", 6.0))
    voice_timeout_profile: str = field(default_factory=lambda: os.environ.get("VOICE_TIMEOUT_PROFILE", "normal"))
    voice_timeout_short_sec: float = field(default_factory=lambda: _env_positive_float("VOICE_TIMEOUT_SHORT_SEC", 0.55))
    voice_timeout_normal_sec: float = field(default_factory=lambda: _env_positive_float("VOICE_TIMEOUT_NORMAL_SEC", 0.8))
    voice_timeout_long_sec: float = field(default_factory=lambda: _env_positive_float("VOICE_TIMEOUT_LONG_SEC", 1.2))
    barge_threshold_always_listening: float = field(
        default_factory=lambda: _env_float("BARGE_THRESHOLD_ALWAYS_LISTENING", 0.4)
    )
    barge_threshold_wake_word: float = field(default_factory=lambda: _env_float("BARGE_THRESHOLD_WAKE_WORD", 0.45))
    barge_threshold_push_to_talk: float = field(default_factory=lambda: _env_float("BARGE_THRESHOLD_PUSH_TO_TALK", 0.5))
    voice_min_post_wake_chars: int = field(default_factory=lambda: _env_int("VOICE_MIN_POST_WAKE_CHARS", 4))
    voice_room_default: str = field(default_factory=lambda: os.environ.get("VOICE_ROOM_DEFAULT", "main"))
    stt_fallback_enabled: bool = field(default_factory=lambda: _env_bool("STT_FALLBACK_ENABLED") is not False)
    whisper_model_fallback: str = field(default_factory=lambda: os.environ.get("WHISPER_MODEL_FALLBACK", "tiny.en"))
    tts_fallback_text_only: bool = field(default_factory=lambda: _env_bool("TTS_FALLBACK_TEXT_ONLY") is not False)
    model_failover_enabled: bool = field(default_factory=lambda: _env_bool("MODEL_FAILOVER_ENABLED") is not False)
    model_secondary_mode: str = field(default_factory=lambda: os.environ.get("MODEL_SECONDARY_MODE", "offline_stub"))
    startup_strict: bool = field(default_factory=lambda: _env_bool("STARTUP_STRICT") or False)
    runtime_state_path: str = field(
        default_factory=lambda: os.environ.get("RUNTIME_STATE_PATH", os.path.expanduser("~/.jarvis/runtime-state.json"))
    )
    expansion_state_path: str = field(
        default_factory=lambda: os.environ.get(
            "EXPANSION_STATE_PATH",
            os.path.expanduser("~/.jarvis/expansion-state.json"),
        )
    )
    policy_engine_path: str = field(
        default_factory=lambda: os.environ.get("POLICY_ENGINE_PATH", "config/policy-engine-v1.json")
    )
    release_channel_config_path: str = field(
        default_factory=lambda: os.environ.get("RELEASE_CHANNEL_CONFIG_PATH", "config/release-channels.json")
    )
    notes_capture_dir: str = field(
        default_factory=lambda: os.environ.get("NOTES_CAPTURE_DIR", os.path.expanduser("~/.jarvis/notes"))
    )
    quality_report_dir: str = field(
        default_factory=lambda: os.environ.get(
            "QUALITY_REPORT_DIR",
            os.path.expanduser("~/.jarvis/quality-reports"),
        )
    )
    watchdog_enabled: bool = field(default_factory=lambda: _env_bool("WATCHDOG_ENABLED") is not False)
    watchdog_listening_timeout_sec: float = field(
        default_factory=lambda: _env_positive_float("WATCHDOG_LISTENING_TIMEOUT_SEC", 30.0)
    )
    watchdog_thinking_timeout_sec: float = field(
        default_factory=lambda: _env_positive_float("WATCHDOG_THINKING_TIMEOUT_SEC", 60.0)
    )
    watchdog_speaking_timeout_sec: float = field(
        default_factory=lambda: _env_positive_float("WATCHDOG_SPEAKING_TIMEOUT_SEC", 45.0)
    )
    turn_timeout_act_sec: float = field(default_factory=lambda: _env_positive_float("TURN_TIMEOUT_ACT_SEC", 30.0))
    operator_server_enabled: bool = field(default_factory=lambda: _env_bool("OPERATOR_SERVER_ENABLED") is not False)
    operator_server_host: str = field(default_factory=lambda: os.environ.get("OPERATOR_SERVER_HOST", "127.0.0.1"))
    operator_server_port: int = field(default_factory=lambda: _env_int("OPERATOR_SERVER_PORT", 8765))
    operator_auth_mode: str = field(default_factory=lambda: os.environ.get("OPERATOR_AUTH_MODE", ""))
    operator_auth_token: str = field(default_factory=lambda: os.environ.get("OPERATOR_AUTH_TOKEN", ""))
    webhook_inbound_enabled: bool = field(default_factory=lambda: _env_bool("WEBHOOK_INBOUND_ENABLED") or False)
    webhook_inbound_token: str = field(default_factory=lambda: os.environ.get("WEBHOOK_INBOUND_TOKEN", ""))
    observability_enabled: bool = field(default_factory=lambda: _env_bool("OBSERVABILITY_ENABLED") is not False)
    observability_db_path: str = field(
        default_factory=lambda: os.environ.get("OBSERVABILITY_DB_PATH", os.path.expanduser("~/.jarvis/telemetry.sqlite"))
    )
    observability_state_path: str = field(
        default_factory=lambda: os.environ.get("OBSERVABILITY_STATE_PATH", os.path.expanduser("~/.jarvis/observability-state.json"))
    )
    observability_event_log_path: str = field(
        default_factory=lambda: os.environ.get("OBSERVABILITY_EVENT_LOG_PATH", os.path.expanduser("~/.jarvis/events.jsonl"))
    )
    recovery_journal_path: str = field(
        default_factory=lambda: os.environ.get(
            "RECOVERY_JOURNAL_PATH",
            os.path.expanduser("~/.jarvis/recovery-journal.jsonl"),
        )
    )
    dead_letter_queue_path: str = field(
        default_factory=lambda: os.environ.get(
            "DEAD_LETTER_QUEUE_PATH",
            os.path.expanduser("~/.jarvis/dead-letter-queue.jsonl"),
        )
    )
    observability_failure_burst_threshold: int = field(
        default_factory=lambda: _env_int("OBSERVABILITY_FAILURE_BURST_THRESHOLD", 5)
    )
    observability_snapshot_interval_sec: float = field(
        default_factory=lambda: _env_positive_float("OBSERVABILITY_SNAPSHOT_INTERVAL_SEC", 30.0)
    )
    observability_latency_budget_p95_ms: float = field(
        default_factory=lambda: _env_nonnegative_float("OBSERVABILITY_LATENCY_BUDGET_P95_MS", 3500.0)
    )
    observability_tokens_budget_per_hour: float = field(
        default_factory=lambda: _env_nonnegative_float("OBSERVABILITY_TOKENS_BUDGET_PER_HOUR", 0.0)
    )
    observability_cost_budget_usd_per_hour: float = field(
        default_factory=lambda: _env_nonnegative_float("OBSERVABILITY_COST_BUDGET_USD_PER_HOUR", 0.0)
    )
    observability_budget_window_sec: float = field(
        default_factory=lambda: _env_positive_float("OBSERVABILITY_BUDGET_WINDOW_SEC", 3600.0)
    )
    observability_alert_cooldown_sec: float = field(
        default_factory=lambda: _env_positive_float("OBSERVABILITY_ALERT_COOLDOWN_SEC", 300.0)
    )
    skills_enabled: bool = field(default_factory=lambda: _env_bool("SKILLS_ENABLED") is not False)
    skills_dir: str = field(default_factory=lambda: os.environ.get("SKILLS_DIR", os.path.expanduser("~/.jarvis/skills")))
    skills_state_path: str = field(
        default_factory=lambda: os.environ.get("SKILLS_STATE_PATH", os.path.expanduser("~/.jarvis/skills/.state.json"))
    )
    skills_allowlist: list[str] = field(default_factory=lambda: _env_list("SKILLS_ALLOWLIST"))
    skills_require_signature: bool = field(default_factory=lambda: _env_bool("SKILLS_REQUIRE_SIGNATURE") or False)
    skills_signature_key: str = field(default_factory=lambda: os.environ.get("SKILLS_SIGNATURE_KEY", ""))
    memory_encryption_enabled: bool = field(default_factory=lambda: _env_bool("MEMORY_ENCRYPTION_ENABLED") or False)
    audit_encryption_enabled: bool = field(default_factory=lambda: _env_bool("AUDIT_ENCRYPTION_ENABLED") or False)
    data_encryption_key: str = field(default_factory=lambda: os.environ.get("JARVIS_DATA_KEY", ""))

    # Vision
    yolo_model: str = "yolov8n-face.pt"
    face_track_fps: int = 10

    # Memory + planning
    memory_enabled: bool = field(default_factory=lambda: _env_bool("MEMORY_ENABLED") is not False)
    memory_path: str = field(default_factory=lambda: os.environ.get("MEMORY_PATH", os.path.expanduser("~/.jarvis/memory.sqlite")))
    memory_search_limit: int = field(default_factory=lambda: _env_int("MEMORY_SEARCH_LIMIT", 5))
    memory_max_sensitivity: float = field(default_factory=lambda: _env_float("MEMORY_MAX_SENSITIVITY", 0.4))
    memory_hybrid_weight: float = field(default_factory=lambda: _env_float("MEMORY_HYBRID_WEIGHT", 0.7))
    memory_decay_half_life_days: float = field(default_factory=lambda: _env_float("MEMORY_DECAY_HALF_LIFE_DAYS", 30.0))
    memory_decay_enabled: bool = field(default_factory=lambda: _env_bool("MEMORY_DECAY_ENABLED") or False)
    memory_mmr_lambda: float = field(default_factory=lambda: _env_float("MEMORY_MMR_LAMBDA", 0.7))
    memory_mmr_enabled: bool = field(default_factory=lambda: _env_bool("MEMORY_MMR_ENABLED") or False)
    memory_embedding_enabled: bool = field(default_factory=lambda: _env_bool("MEMORY_EMBEDDING_ENABLED") or False)
    memory_embedding_model: str = field(
        default_factory=lambda: os.environ.get("MEMORY_EMBEDDING_MODEL", "text-embedding-3-small")
    )
    memory_embedding_base_url: str = field(default_factory=lambda: os.environ.get("MEMORY_EMBEDDING_BASE_URL", ""))
    memory_embedding_vector_weight: float = field(
        default_factory=lambda: _env_float("MEMORY_EMBEDDING_VECTOR_WEIGHT", 0.65)
    )
    memory_embedding_min_similarity: float = field(
        default_factory=lambda: _env_float("MEMORY_EMBEDDING_MIN_SIMILARITY", 0.2)
    )
    memory_embedding_timeout_sec: float = field(
        default_factory=lambda: _env_positive_float("MEMORY_EMBEDDING_TIMEOUT_SEC", 6.0)
    )
    memory_conflict_resolution_enabled: bool = field(
        default_factory=lambda: _env_bool("MEMORY_CONFLICT_RESOLUTION_ENABLED") or False
    )
    memory_conflict_resolution_model: str = field(
        default_factory=lambda: os.environ.get("MEMORY_CONFLICT_RESOLUTION_MODEL", "gpt-4.1-mini")
    )
    memory_conflict_resolution_base_url: str = field(
        default_factory=lambda: os.environ.get("MEMORY_CONFLICT_RESOLUTION_BASE_URL", "")
    )
    memory_conflict_resolution_timeout_sec: float = field(
        default_factory=lambda: _env_positive_float("MEMORY_CONFLICT_RESOLUTION_TIMEOUT_SEC", 4.0)
    )
    memory_prompt_sanitization_enabled: bool = field(
        default_factory=lambda: _env_bool("MEMORY_PROMPT_SANITIZATION_ENABLED") is not False
    )
    memory_pii_guardrails_enabled: bool = field(default_factory=lambda: _env_bool("MEMORY_PII_GUARDRAILS_ENABLED") is not False)
    memory_ingestion_min_confidence: float = field(
        default_factory=lambda: _env_float("MEMORY_INGESTION_MIN_CONFIDENCE", 0.0)
    )
    memory_ingestion_policy: str = field(default_factory=lambda: os.environ.get("MEMORY_INGESTION_POLICY", ""))
    memory_ingest_async_enabled: bool = field(default_factory=lambda: _env_bool("MEMORY_INGEST_ASYNC_ENABLED") or False)
    memory_ingest_queue_max: int = field(default_factory=lambda: _env_int("MEMORY_INGEST_QUEUE_MAX", 256))

    # Tool policy
    tool_allowlist: list[str] = field(default_factory=lambda: _env_list("TOOL_ALLOWLIST"))
    tool_denylist: list[str] = field(default_factory=lambda: _env_list("TOOL_DENYLIST"))

    # Backchannel preferences
    backchannel_style: str = field(default_factory=lambda: os.environ.get("BACKCHANNEL_STYLE", "balanced"))
    persona_style: str = field(default_factory=lambda: os.environ.get("PERSONA_STYLE", "composed"))

    # Service audit retention
    audit_log_max_bytes: int = field(default_factory=lambda: _env_int("AUDIT_LOG_MAX_BYTES", 1_000_000))
    audit_log_backups: int = field(default_factory=lambda: _env_int("AUDIT_LOG_BACKUPS", 3))
    home_permission_profile: str = field(default_factory=lambda: os.environ.get("HOME_PERMISSION_PROFILE", "control"))
    home_require_confirm_execute: bool = field(default_factory=lambda: _env_bool("HOME_REQUIRE_CONFIRM_EXECUTE") or False)
    home_conversation_enabled: bool = field(default_factory=lambda: _env_bool("HOME_CONVERSATION_ENABLED") or False)
    home_conversation_permission_profile: str = field(
        default_factory=lambda: os.environ.get("HOME_CONVERSATION_PERMISSION_PROFILE", "readonly")
    )
    todoist_api_token: str = field(default_factory=lambda: os.environ.get("TODOIST_API_TOKEN", ""))
    todoist_project_id: str = field(default_factory=lambda: os.environ.get("TODOIST_PROJECT_ID", ""))
    todoist_permission_profile: str = field(default_factory=lambda: os.environ.get("TODOIST_PERMISSION_PROFILE", "control"))
    todoist_timeout_sec: float = field(default_factory=lambda: _env_positive_float("TODOIST_TIMEOUT_SEC", 10.0))
    notion_api_token: str = field(default_factory=lambda: os.environ.get("NOTION_API_TOKEN", ""))
    notion_database_id: str = field(default_factory=lambda: os.environ.get("NOTION_DATABASE_ID", ""))
    pushover_api_token: str = field(default_factory=lambda: os.environ.get("PUSHOVER_API_TOKEN", ""))
    pushover_user_key: str = field(default_factory=lambda: os.environ.get("PUSHOVER_USER_KEY", ""))
    notification_permission_profile: str = field(default_factory=lambda: os.environ.get("NOTIFICATION_PERMISSION_PROFILE", "allow"))
    nudge_policy: str = field(default_factory=lambda: os.environ.get("NUDGE_POLICY", "adaptive"))
    nudge_quiet_hours_start: str = field(default_factory=lambda: os.environ.get("NUDGE_QUIET_HOURS_START", "22:00"))
    nudge_quiet_hours_end: str = field(default_factory=lambda: os.environ.get("NUDGE_QUIET_HOURS_END", "07:00"))
    pushover_timeout_sec: float = field(default_factory=lambda: _env_positive_float("PUSHOVER_TIMEOUT_SEC", 10.0))
    email_smtp_host: str = field(default_factory=lambda: os.environ.get("EMAIL_SMTP_HOST", ""))
    email_smtp_port: int = field(default_factory=lambda: _env_int("EMAIL_SMTP_PORT", 587))
    email_smtp_username: str = field(default_factory=lambda: os.environ.get("EMAIL_SMTP_USERNAME", ""))
    email_smtp_password: str = field(default_factory=lambda: os.environ.get("EMAIL_SMTP_PASSWORD", ""))
    email_from: str = field(default_factory=lambda: os.environ.get("EMAIL_FROM", ""))
    email_default_to: str = field(default_factory=lambda: os.environ.get("EMAIL_DEFAULT_TO", ""))
    email_use_tls: bool = field(default_factory=lambda: _env_bool("EMAIL_USE_TLS") is not False)
    email_permission_profile: str = field(default_factory=lambda: os.environ.get("EMAIL_PERMISSION_PROFILE", "readonly"))
    email_timeout_sec: float = field(default_factory=lambda: _env_positive_float("EMAIL_TIMEOUT_SEC", 10.0))
    weather_units: str = field(default_factory=lambda: os.environ.get("WEATHER_UNITS", "metric"))
    weather_timeout_sec: float = field(default_factory=lambda: _env_positive_float("WEATHER_TIMEOUT_SEC", 8.0))
    webhook_allowlist: list[str] = field(default_factory=lambda: _env_list("WEBHOOK_ALLOWLIST"))
    webhook_auth_token: str = field(default_factory=lambda: os.environ.get("WEBHOOK_AUTH_TOKEN", ""))
    webhook_timeout_sec: float = field(default_factory=lambda: _env_positive_float("WEBHOOK_TIMEOUT_SEC", 8.0))
    slack_webhook_url: str = field(default_factory=lambda: os.environ.get("SLACK_WEBHOOK_URL", ""))
    discord_webhook_url: str = field(default_factory=lambda: os.environ.get("DISCORD_WEBHOOK_URL", ""))
    identity_enforcement_enabled: bool = field(default_factory=lambda: _env_bool("IDENTITY_ENFORCEMENT_ENABLED") or False)
    identity_default_user: str = field(default_factory=lambda: os.environ.get("IDENTITY_DEFAULT_USER", "owner"))
    identity_default_profile: str = field(default_factory=lambda: os.environ.get("IDENTITY_DEFAULT_PROFILE", "control"))
    identity_user_profiles: dict[str, str] = field(default_factory=lambda: _env_key_value_map("IDENTITY_USER_PROFILES"))
    identity_trusted_users: list[str] = field(default_factory=lambda: _env_list("IDENTITY_TRUSTED_USERS"))
    identity_require_approval: bool = field(default_factory=lambda: _env_bool("IDENTITY_REQUIRE_APPROVAL") is not False)
    identity_approval_code: str = field(default_factory=lambda: os.environ.get("IDENTITY_APPROVAL_CODE", ""))
    plan_preview_require_ack: bool = field(default_factory=lambda: _env_bool("PLAN_PREVIEW_REQUIRE_ACK") or False)
    memory_retention_days: float = field(default_factory=lambda: _env_nonnegative_float("MEMORY_RETENTION_DAYS", 0.0))
    audit_retention_days: float = field(default_factory=lambda: _env_nonnegative_float("AUDIT_RETENTION_DAYS", 0.0))
    autonomy_llm_replan_enabled: bool = field(
        default_factory=lambda: _env_bool("AUTONOMY_LLM_REPLAN_ENABLED") or False
    )

    # Quick toggles
    motion_enabled: bool = field(default_factory=lambda: _env_bool("MOTION_ENABLED") is not False)
    hand_track_enabled: bool = field(default_factory=lambda: _env_bool("HAND_TRACK_ENABLED") or False)
    home_enabled: bool = field(default_factory=lambda: _env_bool("HOME_ENABLED") is not False)
    safe_mode_enabled: bool = field(default_factory=lambda: _env_bool("SAFE_MODE_ENABLED") or False)
    startup_warnings: list[str] = field(default_factory=list)

    @property
    def has_home_assistant(self) -> bool:
        return bool(self.hass_url and self.hass_token)

    def __post_init__(self) -> None:
        if self.sample_rate != 16000:
            raise ValueError("sample_rate must be 16000 (required by Silero VAD)")
        if not (0.0 <= self.vad_threshold <= 1.0):
            raise ValueError("vad_threshold must be between 0.0 and 1.0")
        if self.doa_change_threshold <= 0.0:
            raise ValueError("doa_change_threshold must be > 0")
        if self.doa_timeout <= 0.0:
            raise ValueError("doa_timeout must be > 0")
        if self.wake_word_sensitivity < 0.5 or self.wake_word_sensitivity > 0.99:
            raise ValueError("wake_word_sensitivity must be between 0.5 and 0.99")
        if self.voice_followup_window_sec <= 0.0:
            raise ValueError("voice_followup_window_sec must be > 0")
        if self.voice_timeout_short_sec <= 0.0:
            raise ValueError("voice_timeout_short_sec must be > 0")
        if self.voice_timeout_normal_sec <= 0.0:
            raise ValueError("voice_timeout_normal_sec must be > 0")
        if self.voice_timeout_long_sec <= 0.0:
            raise ValueError("voice_timeout_long_sec must be > 0")
        for value, label in [
            (self.barge_threshold_always_listening, "barge_threshold_always_listening"),
            (self.barge_threshold_wake_word, "barge_threshold_wake_word"),
            (self.barge_threshold_push_to_talk, "barge_threshold_push_to_talk"),
        ]:
            if value < 0.05 or value > 0.95:
                raise ValueError(f"{label} must be between 0.05 and 0.95")
        if self.voice_min_post_wake_chars < 1:
            raise ValueError("voice_min_post_wake_chars must be >= 1")
        if self.operator_server_port <= 0 or self.operator_server_port > 65535:
            raise ValueError("operator_server_port must be between 1 and 65535")
        if self.observability_failure_burst_threshold < 1:
            raise ValueError("observability_failure_burst_threshold must be >= 1")
        if self.observability_snapshot_interval_sec <= 0.0:
            raise ValueError("observability_snapshot_interval_sec must be > 0")
        if self.observability_latency_budget_p95_ms < 0.0:
            raise ValueError("observability_latency_budget_p95_ms must be >= 0")
        if self.observability_tokens_budget_per_hour < 0.0:
            raise ValueError("observability_tokens_budget_per_hour must be >= 0")
        if self.observability_cost_budget_usd_per_hour < 0.0:
            raise ValueError("observability_cost_budget_usd_per_hour must be >= 0")
        if self.observability_budget_window_sec <= 0.0:
            raise ValueError("observability_budget_window_sec must be > 0")
        if self.observability_alert_cooldown_sec <= 0.0:
            raise ValueError("observability_alert_cooldown_sec must be > 0")
        if self.llm_cost_input_per_1k_tokens < 0.0:
            raise ValueError("llm_cost_input_per_1k_tokens must be >= 0")
        if self.llm_cost_output_per_1k_tokens < 0.0:
            raise ValueError("llm_cost_output_per_1k_tokens must be >= 0")
        if self.watchdog_listening_timeout_sec <= 0.0:
            raise ValueError("watchdog_listening_timeout_sec must be > 0")
        if self.watchdog_thinking_timeout_sec <= 0.0:
            raise ValueError("watchdog_thinking_timeout_sec must be > 0")
        if self.watchdog_speaking_timeout_sec <= 0.0:
            raise ValueError("watchdog_speaking_timeout_sec must be > 0")
        if self.turn_timeout_act_sec <= 0.0:
            raise ValueError("turn_timeout_act_sec must be > 0")
        if self.router_timeout_sec <= 0.0:
            raise ValueError("router_timeout_sec must be > 0")
        if self.router_canary_percent < 0.0 or self.router_canary_percent > 100.0:
            raise ValueError("router_canary_percent must be between 0.0 and 100.0")
        if self.policy_router_min_confidence < 0.0 or self.policy_router_min_confidence > 1.0:
            raise ValueError("policy_router_min_confidence must be between 0.0 and 1.0")
        if self.interruption_router_timeout_sec <= 0.0:
            raise ValueError("interruption_router_timeout_sec must be > 0")
        if self.interruption_resume_min_confidence < 0.0 or self.interruption_resume_min_confidence > 1.0:
            raise ValueError("interruption_resume_min_confidence must be between 0.0 and 1.0")
        if self.semantic_turn_router_timeout_sec <= 0.0:
            raise ValueError("semantic_turn_router_timeout_sec must be > 0")
        if self.semantic_turn_min_confidence < 0.0 or self.semantic_turn_min_confidence > 1.0:
            raise ValueError("semantic_turn_min_confidence must be between 0.0 and 1.0")
        if self.semantic_turn_extension_sec <= 0.0:
            raise ValueError("semantic_turn_extension_sec must be > 0")
        if self.semantic_turn_max_transcript_chars < 20:
            raise ValueError("semantic_turn_max_transcript_chars must be >= 20")
        if self.face_track_fps <= 0:
            raise ValueError("face_track_fps must be > 0")
        if self.memory_search_limit < 1:
            raise ValueError("memory_search_limit must be >= 1")
        if not (0.0 <= self.memory_max_sensitivity <= 1.0):
            raise ValueError("memory_max_sensitivity must be between 0.0 and 1.0")
        if not (0.0 <= self.memory_hybrid_weight <= 1.0):
            raise ValueError("memory_hybrid_weight must be between 0.0 and 1.0")
        if self.memory_decay_half_life_days <= 0.0:
            raise ValueError("memory_decay_half_life_days must be > 0")
        if not (0.0 <= self.memory_mmr_lambda <= 1.0):
            raise ValueError("memory_mmr_lambda must be between 0.0 and 1.0")
        if not (0.0 <= self.memory_embedding_vector_weight <= 1.0):
            raise ValueError("memory_embedding_vector_weight must be between 0.0 and 1.0")
        if not (0.0 <= self.memory_embedding_min_similarity <= 1.0):
            raise ValueError("memory_embedding_min_similarity must be between 0.0 and 1.0")
        if self.memory_embedding_timeout_sec <= 0.0:
            raise ValueError("memory_embedding_timeout_sec must be > 0")
        if self.memory_conflict_resolution_timeout_sec <= 0.0:
            raise ValueError("memory_conflict_resolution_timeout_sec must be > 0")
        if not (0.0 <= self.memory_ingestion_min_confidence <= 1.0):
            raise ValueError("memory_ingestion_min_confidence must be between 0.0 and 1.0")
        if self.memory_ingest_queue_max < 8:
            raise ValueError("memory_ingest_queue_max must be >= 8")
        if self.audit_log_max_bytes <= 0:
            raise ValueError("audit_log_max_bytes must be > 0")
        if self.audit_log_backups < 1:
            raise ValueError("audit_log_backups must be >= 1")
        if self.todoist_timeout_sec <= 0.0:
            raise ValueError("todoist_timeout_sec must be > 0")
        if self.pushover_timeout_sec <= 0.0:
            raise ValueError("pushover_timeout_sec must be > 0")
        if self.email_smtp_port <= 0 or self.email_smtp_port > 65535:
            raise ValueError("email_smtp_port must be between 1 and 65535")
        if self.email_timeout_sec <= 0.0:
            raise ValueError("email_timeout_sec must be > 0")
        if self.weather_timeout_sec <= 0.0:
            raise ValueError("weather_timeout_sec must be > 0")
        if self.webhook_timeout_sec <= 0.0:
            raise ValueError("webhook_timeout_sec must be > 0")
        if self.memory_retention_days < 0.0:
            raise ValueError("memory_retention_days must be >= 0")
        if self.audit_retention_days < 0.0:
            raise ValueError("audit_retention_days must be >= 0")
        if not str(self.operator_auth_mode).strip():
            self.operator_auth_mode = "token" if self.operator_auth_token.strip() else "off"
        self.startup_warnings = self._collect_startup_warnings()
        self.backchannel_style = self._normalize_backchannel_style(self.backchannel_style)
        self.persona_style = self._normalize_persona_style(self.persona_style)
        if not str(self.memory_conflict_resolution_model).strip():
            self.memory_conflict_resolution_model = "gpt-4.1-mini"
        if not str(self.openai_router_model).strip():
            self.openai_router_model = self.openai_model
        if self.router_shadow_enabled and not str(self.openai_router_shadow_model).strip():
            self.openai_router_shadow_model = self.openai_router_model
        self.wake_mode = self._normalize_wake_mode(self.wake_mode)
        self.wake_calibration_profile = self._normalize_wake_calibration_profile(self.wake_calibration_profile)
        self.voice_timeout_profile = self._normalize_voice_timeout_profile(self.voice_timeout_profile)
        self.model_secondary_mode = self._normalize_model_secondary_mode(self.model_secondary_mode)
        self.operator_auth_mode = self._normalize_operator_auth_mode(self.operator_auth_mode)
        self.home_permission_profile = self._normalize_home_permission_profile(self.home_permission_profile)
        self.home_conversation_permission_profile = self._normalize_home_conversation_permission_profile(
            self.home_conversation_permission_profile
        )
        self.todoist_permission_profile = self._normalize_todoist_permission_profile(self.todoist_permission_profile)
        self.notification_permission_profile = self._normalize_notification_permission_profile(self.notification_permission_profile)
        self.nudge_policy = self._normalize_nudge_policy(self.nudge_policy)
        self.nudge_quiet_hours_start = self._normalize_hhmm(self.nudge_quiet_hours_start)
        self.nudge_quiet_hours_end = self._normalize_hhmm(self.nudge_quiet_hours_end)
        self.email_permission_profile = self._normalize_email_permission_profile(self.email_permission_profile)
        self.weather_units = self._normalize_weather_units(self.weather_units)
        self.identity_default_user = self._normalize_identity_default_user(self.identity_default_user)
        self.identity_default_profile = self._normalize_identity_profile(self.identity_default_profile)
        self.identity_user_profiles = self._normalize_identity_user_profiles(self.identity_user_profiles)
        self.identity_trusted_users = self._normalize_identity_trusted_users(self.identity_trusted_users)
        if _env_is_set("BACKCHANNEL_STYLE") and self.backchannel_style == "balanced":
            raw = os.environ.get("BACKCHANNEL_STYLE", "")
            if raw.strip().lower() not in {"quiet", "balanced", "expressive"}:
                self.startup_warnings.append("BACKCHANNEL_STYLE invalid; using balanced.")
        if _env_is_set("PERSONA_STYLE") and self.persona_style == "composed":
            raw = os.environ.get("PERSONA_STYLE", "")
            if raw.strip().lower() not in {"terse", "composed", "friendly", "jarvis"}:
                self.startup_warnings.append("PERSONA_STYLE invalid; using composed.")
        if _env_is_set("WAKE_MODE") and self.wake_mode == "always_listening":
            raw = os.environ.get("WAKE_MODE", "")
            if raw.strip().lower() not in {"always_listening", "wake_word", "push_to_talk"}:
                self.startup_warnings.append("WAKE_MODE invalid; using always_listening.")
        if _env_is_set("WAKE_CALIBRATION_PROFILE") and self.wake_calibration_profile == "default":
            raw = os.environ.get("WAKE_CALIBRATION_PROFILE", "")
            if raw.strip().lower() not in {"default", "quiet_room", "noisy_room", "tv_room", "far_field"}:
                self.startup_warnings.append("WAKE_CALIBRATION_PROFILE invalid; using default.")
        if _env_is_set("VOICE_TIMEOUT_PROFILE") and self.voice_timeout_profile == "normal":
            raw = os.environ.get("VOICE_TIMEOUT_PROFILE", "")
            if raw.strip().lower() not in {"short", "normal", "long"}:
                self.startup_warnings.append("VOICE_TIMEOUT_PROFILE invalid; using normal.")
        if _env_is_set("MODEL_SECONDARY_MODE") and self.model_secondary_mode == "offline_stub":
            raw = os.environ.get("MODEL_SECONDARY_MODE", "")
            if raw.strip().lower() not in {"offline_stub", "retry_once"}:
                self.startup_warnings.append("MODEL_SECONDARY_MODE invalid; using offline_stub.")
        if _env_is_set("OPERATOR_AUTH_MODE") and self.operator_auth_mode == "token":
            raw = os.environ.get("OPERATOR_AUTH_MODE", "")
            if raw.strip().lower() not in {"off", "token", "session"}:
                self.startup_warnings.append("OPERATOR_AUTH_MODE invalid; using token.")
        if _env_is_set("HOME_PERMISSION_PROFILE") and self.home_permission_profile == "control":
            raw = os.environ.get("HOME_PERMISSION_PROFILE", "")
            if raw.strip().lower() not in {"readonly", "control"}:
                self.startup_warnings.append("HOME_PERMISSION_PROFILE invalid; using control.")
        if (
            _env_is_set("HOME_CONVERSATION_PERMISSION_PROFILE")
            and self.home_conversation_permission_profile == "readonly"
        ):
            raw = os.environ.get("HOME_CONVERSATION_PERMISSION_PROFILE", "")
            if raw.strip().lower() not in {"readonly", "control"}:
                self.startup_warnings.append("HOME_CONVERSATION_PERMISSION_PROFILE invalid; using readonly.")
        if _env_is_set("TODOIST_PERMISSION_PROFILE") and self.todoist_permission_profile == "control":
            raw = os.environ.get("TODOIST_PERMISSION_PROFILE", "")
            if raw.strip().lower() not in {"readonly", "control"}:
                self.startup_warnings.append("TODOIST_PERMISSION_PROFILE invalid; using control.")
        if _env_is_set("NOTIFICATION_PERMISSION_PROFILE") and self.notification_permission_profile == "allow":
            raw = os.environ.get("NOTIFICATION_PERMISSION_PROFILE", "")
            if raw.strip().lower() not in {"off", "allow"}:
                self.startup_warnings.append("NOTIFICATION_PERMISSION_PROFILE invalid; using allow.")
        if _env_is_set("NUDGE_POLICY") and self.nudge_policy == "adaptive":
            raw = os.environ.get("NUDGE_POLICY", "")
            if raw.strip().lower() not in {"interrupt", "defer", "adaptive"}:
                self.startup_warnings.append("NUDGE_POLICY invalid; using adaptive.")
        if _env_is_set("NUDGE_QUIET_HOURS_START"):
            raw = os.environ.get("NUDGE_QUIET_HOURS_START", "")
            if raw.strip() and not self.nudge_quiet_hours_start:
                self.startup_warnings.append("NUDGE_QUIET_HOURS_START invalid; expected HH:MM.")
        if _env_is_set("NUDGE_QUIET_HOURS_END"):
            raw = os.environ.get("NUDGE_QUIET_HOURS_END", "")
            if raw.strip() and not self.nudge_quiet_hours_end:
                self.startup_warnings.append("NUDGE_QUIET_HOURS_END invalid; expected HH:MM.")
        if _env_is_set("EMAIL_PERMISSION_PROFILE") and self.email_permission_profile == "readonly":
            raw = os.environ.get("EMAIL_PERMISSION_PROFILE", "")
            if raw.strip().lower() not in {"readonly", "control"}:
                self.startup_warnings.append("EMAIL_PERMISSION_PROFILE invalid; using readonly.")
        if _env_is_set("WEATHER_UNITS") and self.weather_units == "metric":
            raw = os.environ.get("WEATHER_UNITS", "")
            if raw.strip().lower() not in {"metric", "imperial"}:
                self.startup_warnings.append("WEATHER_UNITS invalid; using metric.")
        if _env_is_set("IDENTITY_DEFAULT_PROFILE") and self.identity_default_profile == "control":
            raw = os.environ.get("IDENTITY_DEFAULT_PROFILE", "")
            if raw.strip().lower() not in {"deny", "readonly", "control", "trusted"}:
                self.startup_warnings.append("IDENTITY_DEFAULT_PROFILE invalid; using control.")
        if _env_is_set("IDENTITY_USER_PROFILES"):
            raw_map = os.environ.get("IDENTITY_USER_PROFILES", "")
            for segment in raw_map.split(","):
                part = segment.strip()
                if not part:
                    continue
                if "=" not in part:
                    self.startup_warnings.append("IDENTITY_USER_PROFILES has invalid entry; expected user=profile.")
                    continue
                user_text, profile_text = part.split("=", 1)
                if not user_text.strip():
                    self.startup_warnings.append("IDENTITY_USER_PROFILES has invalid entry; empty user id.")
                    continue
                if profile_text.strip().lower() not in {"deny", "readonly", "control", "trusted"}:
                    self.startup_warnings.append(
                        f"IDENTITY_USER_PROFILES has invalid profile for user '{user_text.strip()}'; using control."
                    )

    @staticmethod
    def _normalize_backchannel_style(style: str) -> str:
        normalized = (style or "balanced").strip().lower()
        if normalized in {"quiet", "balanced", "expressive"}:
            return normalized
        return "balanced"

    @staticmethod
    def _normalize_persona_style(style: str) -> str:
        normalized = (style or "composed").strip().lower()
        aliases = {
            "witty": "jarvis",
            "classic": "jarvis",
            "classic_jarvis": "jarvis",
            "jarvis_classic": "jarvis",
        }
        normalized = aliases.get(normalized, normalized)
        if normalized in {"terse", "composed", "friendly", "jarvis"}:
            return normalized
        return "composed"

    @staticmethod
    def _normalize_wake_mode(mode: str) -> str:
        normalized = (mode or "always_listening").strip().lower()
        if normalized in {"always_listening", "wake_word", "push_to_talk"}:
            return normalized
        return "always_listening"

    @staticmethod
    def _normalize_wake_calibration_profile(profile: str) -> str:
        normalized = (profile or "default").strip().lower()
        if normalized in {"default", "quiet_room", "noisy_room", "tv_room", "far_field"}:
            return normalized
        return "default"

    @staticmethod
    def _normalize_voice_timeout_profile(profile: str) -> str:
        normalized = (profile or "normal").strip().lower()
        if normalized in {"short", "normal", "long"}:
            return normalized
        return "normal"

    @staticmethod
    def _normalize_model_secondary_mode(mode: str) -> str:
        normalized = (mode or "offline_stub").strip().lower()
        if normalized in {"offline_stub", "retry_once"}:
            return normalized
        return "offline_stub"

    @staticmethod
    def _normalize_operator_auth_mode(mode: str) -> str:
        normalized = (mode or "token").strip().lower()
        if normalized in {"off", "token", "session"}:
            return normalized
        return "token"

    @staticmethod
    def _normalize_home_permission_profile(profile: str) -> str:
        normalized = (profile or "control").strip().lower()
        if normalized in {"readonly", "control"}:
            return normalized
        return "control"

    @staticmethod
    def _normalize_home_conversation_permission_profile(profile: str) -> str:
        normalized = (profile or "readonly").strip().lower()
        if normalized in {"readonly", "control"}:
            return normalized
        return "readonly"

    @staticmethod
    def _normalize_todoist_permission_profile(profile: str) -> str:
        normalized = (profile or "control").strip().lower()
        if normalized in {"readonly", "control"}:
            return normalized
        return "control"

    @staticmethod
    def _normalize_notification_permission_profile(profile: str) -> str:
        normalized = (profile or "allow").strip().lower()
        if normalized in {"off", "allow"}:
            return normalized
        return "allow"

    @staticmethod
    def _normalize_nudge_policy(policy: str) -> str:
        normalized = (policy or "adaptive").strip().lower()
        if normalized in {"interrupt", "defer", "adaptive"}:
            return normalized
        return "adaptive"

    @staticmethod
    def _normalize_hhmm(value: str) -> str:
        text = (value or "").strip()
        if not text:
            return ""
        if ":" not in text:
            return ""
        parts = text.split(":")
        if len(parts) != 2:
            return ""
        hours_text = parts[0].strip()
        minutes_text = parts[1].strip()
        if not (hours_text.isdigit() and minutes_text.isdigit() and len(minutes_text) == 2):
            return ""
        hours = int(hours_text)
        minutes = int(minutes_text)
        if hours < 0 or hours > 23 or minutes < 0 or minutes > 59:
            return ""
        return f"{hours:02d}:{minutes:02d}"

    @staticmethod
    def _normalize_weather_units(units: str) -> str:
        normalized = (units or "metric").strip().lower()
        if normalized in {"metric", "imperial"}:
            return normalized
        return "metric"

    @staticmethod
    def _normalize_email_permission_profile(profile: str) -> str:
        normalized = (profile or "readonly").strip().lower()
        if normalized in {"readonly", "control"}:
            return normalized
        return "readonly"

    @staticmethod
    def _normalize_identity_default_user(value: str) -> str:
        normalized = (value or "owner").strip().lower()
        return normalized or "owner"

    @staticmethod
    def _normalize_identity_profile(profile: str) -> str:
        normalized = (profile or "control").strip().lower()
        if normalized in {"deny", "readonly", "control", "trusted"}:
            return normalized
        return "control"

    @classmethod
    def _normalize_identity_user_profiles(cls, profiles: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_user, raw_profile in profiles.items():
            user = str(raw_user or "").strip().lower()
            if not user:
                continue
            normalized[user] = cls._normalize_identity_profile(str(raw_profile))
        return normalized

    @staticmethod
    def _normalize_identity_trusted_users(users: list[str]) -> list[str]:
        return sorted({str(user).strip().lower() for user in users if str(user).strip()})

    def _collect_startup_warnings(self) -> list[str]:
        warnings: list[str] = []
        if bool(self.nudge_quiet_hours_start) != bool(self.nudge_quiet_hours_end):
            warnings.append("Quiet-window config incomplete; set both NUDGE_QUIET_HOURS_START and NUDGE_QUIET_HOURS_END.")
        if self.nudge_quiet_hours_start and self.nudge_quiet_hours_end and self.nudge_quiet_hours_start == self.nudge_quiet_hours_end:
            warnings.append("NUDGE_QUIET_HOURS_START equals NUDGE_QUIET_HOURS_END; quiet-window deferral is disabled.")
        if self.safe_mode_enabled:
            warnings.append("SAFE_MODE_ENABLED=true; mutating actions run in restricted mode until disabled.")
        has_hass_url = bool((self.hass_url or "").strip())
        has_hass_token = bool((self.hass_token or "").strip())
        if has_hass_url != has_hass_token:
            warnings.append("Home Assistant config incomplete; set both HASS_URL and HASS_TOKEN.")
        if (
            _env_is_set("HOME_PERMISSION_PROFILE")
            and self.home_permission_profile == "control"
            and not has_hass_url
            and not has_hass_token
        ):
            warnings.append("HOME_PERMISSION_PROFILE=control set while HASS_URL/HASS_TOKEN are empty.")
        if (
            _env_is_set("HOME_CONVERSATION_PERMISSION_PROFILE")
            and self.home_conversation_permission_profile == "control"
            and not has_hass_url
            and not has_hass_token
        ):
            warnings.append(
                "HOME_CONVERSATION_PERMISSION_PROFILE=control set while HASS_URL/HASS_TOKEN are empty."
            )
        has_todoist_token = bool((self.todoist_api_token or "").strip())
        has_todoist_project = bool((self.todoist_project_id or "").strip())
        if has_todoist_project and not has_todoist_token:
            warnings.append("Todoist config incomplete; set TODOIST_API_TOKEN when TODOIST_PROJECT_ID is set.")
        if (
            _env_is_set("TODOIST_PERMISSION_PROFILE")
            and self.todoist_permission_profile == "control"
            and not has_todoist_token
        ):
            warnings.append("TODOIST_PERMISSION_PROFILE=control set while TODOIST_API_TOKEN is empty.")
        has_notion_token = bool((self.notion_api_token or "").strip())
        has_notion_database = bool((self.notion_database_id or "").strip())
        if has_notion_token != has_notion_database:
            warnings.append("Notion config incomplete; set both NOTION_API_TOKEN and NOTION_DATABASE_ID.")
        has_pushover_token = bool((self.pushover_api_token or "").strip())
        has_pushover_user = bool((self.pushover_user_key or "").strip())
        if has_pushover_token != has_pushover_user:
            warnings.append("Pushover config incomplete; set both PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY.")
        if (
            _env_is_set("NOTIFICATION_PERMISSION_PROFILE")
            and self.notification_permission_profile == "allow"
            and not has_pushover_token
            and not has_pushover_user
        ):
            warnings.append("NOTIFICATION_PERMISSION_PROFILE=allow set while Pushover credentials are empty.")
        has_email_host = bool((self.email_smtp_host or "").strip())
        has_email_from = bool((self.email_from or "").strip())
        has_email_to = bool((self.email_default_to or "").strip())
        if has_email_host and (not has_email_from or not has_email_to):
            warnings.append("Email config incomplete; set EMAIL_FROM and EMAIL_DEFAULT_TO when EMAIL_SMTP_HOST is set.")
        if (
            _env_is_set("EMAIL_PERMISSION_PROFILE")
            and self.email_permission_profile == "control"
            and not has_email_host
        ):
            warnings.append("EMAIL_PERMISSION_PROFILE=control set while EMAIL_SMTP_HOST is empty.")
        if has_hass_token and len(self.hass_token.strip()) < 20:
            warnings.append("HASS_TOKEN appears unusually short; verify token scope and rotation policy.")
        if has_todoist_token and len(self.todoist_api_token.strip()) < 20:
            warnings.append("TODOIST_API_TOKEN appears unusually short; verify token scope.")
        if has_pushover_token and len(self.pushover_api_token.strip()) < 20:
            warnings.append("PUSHOVER_API_TOKEN appears unusually short; verify credential scope.")
        if self.webhook_auth_token.strip() and not self.webhook_allowlist:
            warnings.append("WEBHOOK_AUTH_TOKEN is set while WEBHOOK_ALLOWLIST is empty; webhook_trigger will remain blocked.")
        if self.webhook_inbound_enabled and not self.operator_server_enabled:
            warnings.append("WEBHOOK_INBOUND_ENABLED=true while OPERATOR_SERVER_ENABLED=false; inbound webhook endpoint will be unavailable.")
        if self.webhook_inbound_enabled and not (self.webhook_inbound_token.strip() or self.webhook_auth_token.strip()):
            warnings.append(
                "WEBHOOK_INBOUND_ENABLED=true without WEBHOOK_INBOUND_TOKEN/WEBHOOK_AUTH_TOKEN; inbound endpoint is unauthenticated."
            )
        operator_host = (self.operator_server_host or "").strip().lower()
        operator_non_loopback = (
            self.operator_server_enabled and operator_host and operator_host not in {"127.0.0.1", "localhost", "::1"}
        )
        operator_auth_mode = self._normalize_operator_auth_mode(self.operator_auth_mode)
        operator_token = self.operator_auth_token.strip()
        if operator_non_loopback:
            warnings.append(
                "OPERATOR_SERVER_HOST is non-loopback; operator endpoints may be remotely reachable."
            )
        if self.operator_server_enabled:
            if operator_auth_mode == "off":
                warnings.append("OPERATOR_AUTH_MODE=off (risk: high); operator API routes are unauthenticated.")
                if operator_non_loopback:
                    warnings.append("OPERATOR_AUTH_MODE=off on non-loopback OPERATOR_SERVER_HOST (risk: critical).")
            elif not operator_token:
                warnings.append(f"OPERATOR_AUTH_MODE={operator_auth_mode} without OPERATOR_AUTH_TOKEN (risk: high).")
        if operator_non_loopback and not operator_token:
            warnings.append(
                "OPERATOR_AUTH_TOKEN should be set when OPERATOR_SERVER_HOST is non-loopback."
            )
        if operator_token and len(operator_token) < 8:
            warnings.append("OPERATOR_AUTH_TOKEN appears unusually short; use at least 8 characters.")
        if self.slack_webhook_url.strip() and not self.slack_webhook_url.strip().lower().startswith("https://"):
            warnings.append("SLACK_WEBHOOK_URL should use https.")
        if self.discord_webhook_url.strip() and not self.discord_webhook_url.strip().lower().startswith("https://"):
            warnings.append("DISCORD_WEBHOOK_URL should use https.")
        if self.identity_approval_code.strip() and len(self.identity_approval_code.strip()) < 8:
            warnings.append("IDENTITY_APPROVAL_CODE appears unusually short; use at least 8 characters.")
        if (
            self.identity_enforcement_enabled
            and self.identity_require_approval
            and not self.identity_approval_code.strip()
            and not self.identity_trusted_users
        ):
            warnings.append(
                "IDENTITY_REQUIRE_APPROVAL is enabled without IDENTITY_APPROVAL_CODE or IDENTITY_TRUSTED_USERS."
            )
        if self.plan_preview_require_ack and not self.identity_enforcement_enabled:
            warnings.append(
                "PLAN_PREVIEW_REQUIRE_ACK enabled while IDENTITY_ENFORCEMENT_ENABLED=false; preview gate works but trust controls are relaxed."
            )
        if self.skills_require_signature and not self.skills_signature_key.strip():
            warnings.append("SKILLS_REQUIRE_SIGNATURE enabled without SKILLS_SIGNATURE_KEY; non-signed skills will remain blocked.")
        if (self.memory_encryption_enabled or self.audit_encryption_enabled) and not self.data_encryption_key.strip():
            warnings.append("Encryption enabled without JARVIS_DATA_KEY; encrypted storage features will be disabled.")
        if self.memory_embedding_enabled and not self.openai_api_key.strip():
            warnings.append("MEMORY_EMBEDDING_ENABLED=true without OPENAI_API_KEY; semantic retrieval will be disabled.")
        if self.memory_embedding_enabled and self.memory_encryption_enabled:
            warnings.append(
                "MEMORY_EMBEDDING_ENABLED=true with MEMORY_ENCRYPTION_ENABLED=true; semantic retrieval is disabled for encrypted memory."
            )
        if self.memory_conflict_resolution_enabled and not self.openai_api_key.strip():
            warnings.append(
                "MEMORY_CONFLICT_RESOLUTION_ENABLED=true without OPENAI_API_KEY; conflict resolution will be disabled."
            )
        checks: list[tuple[str, str, str]] = [
            ("DOA_CHANGE_THRESHOLD", "float", str(self.doa_change_threshold)),
            ("DOA_TIMEOUT", "float", str(self.doa_timeout)),
            ("WAKE_WORD_SENSITIVITY", "float", str(self.wake_word_sensitivity)),
            ("VOICE_FOLLOWUP_WINDOW_SEC", "positive_float", str(self.voice_followup_window_sec)),
            ("VOICE_TIMEOUT_SHORT_SEC", "positive_float", str(self.voice_timeout_short_sec)),
            ("VOICE_TIMEOUT_NORMAL_SEC", "positive_float", str(self.voice_timeout_normal_sec)),
            ("VOICE_TIMEOUT_LONG_SEC", "positive_float", str(self.voice_timeout_long_sec)),
            ("BARGE_THRESHOLD_ALWAYS_LISTENING", "float", str(self.barge_threshold_always_listening)),
            ("BARGE_THRESHOLD_WAKE_WORD", "float", str(self.barge_threshold_wake_word)),
            ("BARGE_THRESHOLD_PUSH_TO_TALK", "float", str(self.barge_threshold_push_to_talk)),
            ("VOICE_MIN_POST_WAKE_CHARS", "int", str(self.voice_min_post_wake_chars)),
            ("WATCHDOG_LISTENING_TIMEOUT_SEC", "positive_float", str(self.watchdog_listening_timeout_sec)),
            ("WATCHDOG_THINKING_TIMEOUT_SEC", "positive_float", str(self.watchdog_thinking_timeout_sec)),
            ("WATCHDOG_SPEAKING_TIMEOUT_SEC", "positive_float", str(self.watchdog_speaking_timeout_sec)),
            ("TURN_TIMEOUT_ACT_SEC", "positive_float", str(self.turn_timeout_act_sec)),
            ("ROUTER_TIMEOUT_SEC", "positive_float", str(self.router_timeout_sec)),
            ("ROUTER_CANARY_PERCENT", "float", str(self.router_canary_percent)),
            ("POLICY_ROUTER_MIN_CONFIDENCE", "float", str(self.policy_router_min_confidence)),
            (
                "INTERRUPTION_ROUTER_TIMEOUT_SEC",
                "positive_float",
                str(self.interruption_router_timeout_sec),
            ),
            (
                "INTERRUPTION_RESUME_MIN_CONFIDENCE",
                "float",
                str(self.interruption_resume_min_confidence),
            ),
            (
                "SEMANTIC_TURN_ROUTER_TIMEOUT_SEC",
                "positive_float",
                str(self.semantic_turn_router_timeout_sec),
            ),
            (
                "SEMANTIC_TURN_MIN_CONFIDENCE",
                "float",
                str(self.semantic_turn_min_confidence),
            ),
            (
                "SEMANTIC_TURN_EXTENSION_SEC",
                "positive_float",
                str(self.semantic_turn_extension_sec),
            ),
            (
                "SEMANTIC_TURN_MAX_TRANSCRIPT_CHARS",
                "int",
                str(self.semantic_turn_max_transcript_chars),
            ),
            ("OPERATOR_SERVER_PORT", "int", str(self.operator_server_port)),
            (
                "OBSERVABILITY_FAILURE_BURST_THRESHOLD",
                "int",
                str(self.observability_failure_burst_threshold),
            ),
            (
                "OBSERVABILITY_SNAPSHOT_INTERVAL_SEC",
                "positive_float",
                str(self.observability_snapshot_interval_sec),
            ),
            (
                "OBSERVABILITY_LATENCY_BUDGET_P95_MS",
                "nonnegative_float",
                str(self.observability_latency_budget_p95_ms),
            ),
            (
                "OBSERVABILITY_TOKENS_BUDGET_PER_HOUR",
                "nonnegative_float",
                str(self.observability_tokens_budget_per_hour),
            ),
            (
                "OBSERVABILITY_COST_BUDGET_USD_PER_HOUR",
                "nonnegative_float",
                str(self.observability_cost_budget_usd_per_hour),
            ),
            (
                "OBSERVABILITY_BUDGET_WINDOW_SEC",
                "positive_float",
                str(self.observability_budget_window_sec),
            ),
            (
                "OBSERVABILITY_ALERT_COOLDOWN_SEC",
                "positive_float",
                str(self.observability_alert_cooldown_sec),
            ),
            ("LLM_COST_INPUT_PER_1K_TOKENS", "nonnegative_float", str(self.llm_cost_input_per_1k_tokens)),
            ("LLM_COST_OUTPUT_PER_1K_TOKENS", "nonnegative_float", str(self.llm_cost_output_per_1k_tokens)),
            ("MEMORY_SEARCH_LIMIT", "int", str(self.memory_search_limit)),
            ("MEMORY_EMBEDDING_VECTOR_WEIGHT", "float", str(self.memory_embedding_vector_weight)),
            ("MEMORY_EMBEDDING_MIN_SIMILARITY", "float", str(self.memory_embedding_min_similarity)),
            ("MEMORY_EMBEDDING_TIMEOUT_SEC", "positive_float", str(self.memory_embedding_timeout_sec)),
            (
                "MEMORY_CONFLICT_RESOLUTION_TIMEOUT_SEC",
                "positive_float",
                str(self.memory_conflict_resolution_timeout_sec),
            ),
            ("MEMORY_INGESTION_MIN_CONFIDENCE", "float", str(self.memory_ingestion_min_confidence)),
            ("MEMORY_INGEST_QUEUE_MAX", "int", str(self.memory_ingest_queue_max)),
            ("AUDIT_LOG_MAX_BYTES", "int", str(self.audit_log_max_bytes)),
            ("AUDIT_LOG_BACKUPS", "int", str(self.audit_log_backups)),
            ("MEMORY_RETENTION_DAYS", "nonnegative_float", str(self.memory_retention_days)),
            ("AUDIT_RETENTION_DAYS", "nonnegative_float", str(self.audit_retention_days)),
            ("TODOIST_TIMEOUT_SEC", "positive_float", str(self.todoist_timeout_sec)),
            ("PUSHOVER_TIMEOUT_SEC", "positive_float", str(self.pushover_timeout_sec)),
            ("EMAIL_TIMEOUT_SEC", "positive_float", str(self.email_timeout_sec)),
            ("WEATHER_TIMEOUT_SEC", "positive_float", str(self.weather_timeout_sec)),
            ("WEBHOOK_TIMEOUT_SEC", "positive_float", str(self.webhook_timeout_sec)),
        ]
        for name, kind, fallback in checks:
            raw = os.environ.get(name)
            if raw is None or not raw.strip():
                continue
            try:
                if kind in {"float", "positive_float", "nonnegative_float"}:
                    parsed = float(raw)
                    if not math.isfinite(parsed):
                        raise ValueError("non-finite float")
                    if kind == "positive_float" and parsed <= 0.0:
                        raise ValueError("non-positive float")
                    if kind == "nonnegative_float" and parsed < 0.0:
                        raise ValueError("negative float")
                else:
                    int(raw)
            except ValueError:
                warnings.append(f"{name} invalid; using {fallback}.")
        bool_checks = [
            "REACHY_AUTOMATIC_BODY_YAW",
            "MEMORY_ENABLED",
            "MEMORY_DECAY_ENABLED",
            "MEMORY_MMR_ENABLED",
            "MEMORY_EMBEDDING_ENABLED",
            "MEMORY_CONFLICT_RESOLUTION_ENABLED",
            "MEMORY_PROMPT_SANITIZATION_ENABLED",
            "MEMORY_PII_GUARDRAILS_ENABLED",
            "MEMORY_INGEST_ASYNC_ENABLED",
            "STT_FALLBACK_ENABLED",
            "TTS_FALLBACK_TEXT_ONLY",
            "MODEL_FAILOVER_ENABLED",
            "STARTUP_STRICT",
            "WATCHDOG_ENABLED",
            "ROUTER_SHADOW_ENABLED",
            "OPERATOR_SERVER_ENABLED",
            "WEBHOOK_INBOUND_ENABLED",
            "OBSERVABILITY_ENABLED",
            "SKILLS_ENABLED",
            "SKILLS_REQUIRE_SIGNATURE",
            "MEMORY_ENCRYPTION_ENABLED",
            "AUDIT_ENCRYPTION_ENABLED",
            "MOTION_ENABLED",
            "HAND_TRACK_ENABLED",
            "HOME_ENABLED",
            "SAFE_MODE_ENABLED",
            "HOME_REQUIRE_CONFIRM_EXECUTE",
            "HOME_CONVERSATION_ENABLED",
            "IDENTITY_ENFORCEMENT_ENABLED",
            "IDENTITY_REQUIRE_APPROVAL",
            "PLAN_PREVIEW_REQUIRE_ACK",
            "SEMANTIC_TURN_ENABLED",
        ]
        for name in bool_checks:
            raw = os.environ.get(name)
            if raw is None or not raw.strip():
                continue
            normalized = raw.strip().lower()
            if normalized in {"1", "true", "yes", "y", "on", "0", "false", "no", "n", "off"}:
                continue
            warnings.append(f"{name} invalid boolean; using default behavior.")
        return warnings
