import time

from jarvis.__main__ import Jarvis, INTENDED_QUERY_MIN_ATTENTION
from jarvis.presence import Signals


def _jarvis_instance():
    args = type("Args", (), {"sim": True, "no_vision": True, "no_tts": True, "debug": False})
    jarvis = Jarvis(args)
    jarvis.presence.signals = Signals()
    return jarvis


def test_requires_confirmation_low_attention():
    jarvis = _jarvis_instance()
    now = time.monotonic()
    assert jarvis._attention_confidence(now) == 0.0
    assert jarvis._requires_confirmation(now)


def test_requires_confirmation_with_face():
    jarvis = _jarvis_instance()
    now = time.monotonic()
    jarvis.presence.signals.face_last_seen = now
    assert jarvis._attention_confidence(now) >= INTENDED_QUERY_MIN_ATTENTION
    assert not jarvis._requires_confirmation(now)


def test_requires_confirmation_with_doa_speech():
    jarvis = _jarvis_instance()
    now = time.monotonic()
    jarvis._last_doa_speech = True
    assert not jarvis._requires_confirmation(now)
