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

    # Quick toggles
    motion_enabled: bool = field(default_factory=lambda: _env_bool("MOTION_ENABLED") is not False)
    hand_track_enabled: bool = field(default_factory=lambda: _env_bool("HAND_TRACK_ENABLED") or False)
    home_enabled: bool = field(default_factory=lambda: _env_bool("HOME_ENABLED") is not False)

    @property
    def has_home_assistant(self) -> bool:
        return bool(self.hass_url and self.hass_token)

    def __post_init__(self) -> None:
        if self.sample_rate != 16000:
            raise ValueError("sample_rate must be 16000 (required by Silero VAD)")
