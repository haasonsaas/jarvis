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
    # Claude
    anthropic_api_key: str = field(default_factory=lambda: _require_env("ANTHROPIC_API_KEY"))

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
    memory_pii_guardrails_enabled: bool = field(default_factory=lambda: _env_bool("MEMORY_PII_GUARDRAILS_ENABLED") is not False)

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
    pushover_api_token: str = field(default_factory=lambda: os.environ.get("PUSHOVER_API_TOKEN", ""))
    pushover_user_key: str = field(default_factory=lambda: os.environ.get("PUSHOVER_USER_KEY", ""))
    notification_permission_profile: str = field(default_factory=lambda: os.environ.get("NOTIFICATION_PERMISSION_PROFILE", "allow"))
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
    memory_retention_days: float = field(default_factory=lambda: _env_nonnegative_float("MEMORY_RETENTION_DAYS", 0.0))
    audit_retention_days: float = field(default_factory=lambda: _env_nonnegative_float("AUDIT_RETENTION_DAYS", 0.0))

    # Quick toggles
    motion_enabled: bool = field(default_factory=lambda: _env_bool("MOTION_ENABLED") is not False)
    hand_track_enabled: bool = field(default_factory=lambda: _env_bool("HAND_TRACK_ENABLED") or False)
    home_enabled: bool = field(default_factory=lambda: _env_bool("HOME_ENABLED") is not False)
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
        self.startup_warnings = self._collect_startup_warnings()
        self.backchannel_style = self._normalize_backchannel_style(self.backchannel_style)
        self.persona_style = self._normalize_persona_style(self.persona_style)
        self.home_permission_profile = self._normalize_home_permission_profile(self.home_permission_profile)
        self.home_conversation_permission_profile = self._normalize_home_conversation_permission_profile(
            self.home_conversation_permission_profile
        )
        self.todoist_permission_profile = self._normalize_todoist_permission_profile(self.todoist_permission_profile)
        self.notification_permission_profile = self._normalize_notification_permission_profile(self.notification_permission_profile)
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
            if raw.strip().lower() not in {"terse", "composed", "friendly"}:
                self.startup_warnings.append("PERSONA_STYLE invalid; using composed.")
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
        if normalized in {"terse", "composed", "friendly"}:
            return normalized
        return "composed"

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
        checks: list[tuple[str, str, str]] = [
            ("DOA_CHANGE_THRESHOLD", "float", str(self.doa_change_threshold)),
            ("DOA_TIMEOUT", "float", str(self.doa_timeout)),
            ("MEMORY_SEARCH_LIMIT", "int", str(self.memory_search_limit)),
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
            "MEMORY_PII_GUARDRAILS_ENABLED",
            "MOTION_ENABLED",
            "HAND_TRACK_ENABLED",
            "HOME_ENABLED",
            "HOME_REQUIRE_CONFIRM_EXECUTE",
            "HOME_CONVERSATION_ENABLED",
            "IDENTITY_ENFORCEMENT_ENABLED",
            "IDENTITY_REQUIRE_APPROVAL",
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
