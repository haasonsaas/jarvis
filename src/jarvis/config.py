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

    # Audio — 16kHz is required by Silero VAD (fixed chunk size of 512 samples)
    vad_threshold: float = 0.5
    whisper_model: str = "base.en"
    sample_rate: int = 16000

    # Vision
    yolo_model: str = "yolov8n-face.pt"
    face_track_fps: int = 10

    @property
    def has_home_assistant(self) -> bool:
        return bool(self.hass_url and self.hass_token)

    def __post_init__(self) -> None:
        if self.sample_rate != 16000:
            raise ValueError("sample_rate must be 16000 (required by Silero VAD)")
