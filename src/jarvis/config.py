import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return val


def _env_bool(name: str) -> bool | None:
    val = os.environ.get(name)
    if val is None:
        return None
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    val = os.environ.get(name)
    if val is None or not val.strip():
        return default
    try:
        return float(val)
    except ValueError:
        return default


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
        if _env_is_set("BACKCHANNEL_STYLE") and self.backchannel_style == "balanced":
            raw = os.environ.get("BACKCHANNEL_STYLE", "")
            if raw.strip().lower() not in {"quiet", "balanced", "expressive"}:
                self.startup_warnings.append("BACKCHANNEL_STYLE invalid; using balanced.")
        if _env_is_set("PERSONA_STYLE") and self.persona_style == "composed":
            raw = os.environ.get("PERSONA_STYLE", "")
            if raw.strip().lower() not in {"terse", "composed", "friendly"}:
                self.startup_warnings.append("PERSONA_STYLE invalid; using composed.")

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

    def _collect_startup_warnings(self) -> list[str]:
        warnings: list[str] = []
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
                    float(raw)
                else:
                    int(raw)
            except ValueError:
                warnings.append(f"{name} invalid; using {fallback}.")
        return warnings
