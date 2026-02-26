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
    todoist_api_token: str = field(default_factory=lambda: os.environ.get("TODOIST_API_TOKEN", ""))
    todoist_project_id: str = field(default_factory=lambda: os.environ.get("TODOIST_PROJECT_ID", ""))
    todoist_permission_profile: str = field(default_factory=lambda: os.environ.get("TODOIST_PERMISSION_PROFILE", "control"))
    pushover_api_token: str = field(default_factory=lambda: os.environ.get("PUSHOVER_API_TOKEN", ""))
    pushover_user_key: str = field(default_factory=lambda: os.environ.get("PUSHOVER_USER_KEY", ""))
    notification_permission_profile: str = field(default_factory=lambda: os.environ.get("NOTIFICATION_PERMISSION_PROFILE", "allow"))

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
        self.startup_warnings = self._collect_startup_warnings()
        self.backchannel_style = self._normalize_backchannel_style(self.backchannel_style)
        self.persona_style = self._normalize_persona_style(self.persona_style)
        self.home_permission_profile = self._normalize_home_permission_profile(self.home_permission_profile)
        self.todoist_permission_profile = self._normalize_todoist_permission_profile(self.todoist_permission_profile)
        self.notification_permission_profile = self._normalize_notification_permission_profile(self.notification_permission_profile)
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
        if _env_is_set("TODOIST_PERMISSION_PROFILE") and self.todoist_permission_profile == "control":
            raw = os.environ.get("TODOIST_PERMISSION_PROFILE", "")
            if raw.strip().lower() not in {"readonly", "control"}:
                self.startup_warnings.append("TODOIST_PERMISSION_PROFILE invalid; using control.")
        if _env_is_set("NOTIFICATION_PERMISSION_PROFILE") and self.notification_permission_profile == "allow":
            raw = os.environ.get("NOTIFICATION_PERMISSION_PROFILE", "")
            if raw.strip().lower() not in {"off", "allow"}:
                self.startup_warnings.append("NOTIFICATION_PERMISSION_PROFILE invalid; using allow.")

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
        checks: list[tuple[str, str, str]] = [
            ("DOA_CHANGE_THRESHOLD", "float", str(self.doa_change_threshold)),
            ("DOA_TIMEOUT", "float", str(self.doa_timeout)),
            ("MEMORY_SEARCH_LIMIT", "int", str(self.memory_search_limit)),
            ("AUDIT_LOG_MAX_BYTES", "int", str(self.audit_log_max_bytes)),
            ("AUDIT_LOG_BACKUPS", "int", str(self.audit_log_backups)),
        ]
        for name, kind, fallback in checks:
            raw = os.environ.get(name)
            if raw is None or not raw.strip():
                continue
            try:
                if kind == "float":
                    parsed = float(raw)
                    if not math.isfinite(parsed):
                        raise ValueError("non-finite float")
                else:
                    int(raw)
            except ValueError:
                warnings.append(f"{name} invalid; using {fallback}.")
        bool_checks = [
            "REACHY_AUTOMATIC_BODY_YAW",
            "MEMORY_ENABLED",
            "MEMORY_DECAY_ENABLED",
            "MEMORY_MMR_ENABLED",
            "MOTION_ENABLED",
            "HAND_TRACK_ENABLED",
            "HOME_ENABLED",
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
