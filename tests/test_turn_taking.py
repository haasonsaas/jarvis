import pytest

from jarvis.__main__ import Jarvis, TURN_TAKING_THRESHOLD, TURN_TAKING_BARGE_IN_THRESHOLD
from jarvis.presence import Signals


@pytest.fixture
def jarvis_instance():
    args = type("Args", (), {"sim": True, "no_vision": True, "no_tts": True, "debug": False})
    jarvis = Jarvis(args)
    jarvis.presence.signals = Signals()
    return jarvis


def test_turn_taking_threshold_regular(jarvis_instance):
    now = 100.0
    jarvis_instance.presence.signals.face_last_seen = now
    assert jarvis_instance._compute_turn_taking(conf=0.8, doa_speech=False, assistant_busy=False, now=now)


def test_turn_taking_threshold_barge_in(jarvis_instance):
    now = 100.0
    jarvis_instance.presence.signals.doa_last_seen = now
    assert jarvis_instance._compute_turn_taking(
        conf=TURN_TAKING_BARGE_IN_THRESHOLD,
        doa_speech=True,
        assistant_busy=True,
        now=now,
    )


def test_confidence_pause(jarvis_instance):
    assert jarvis_instance._confidence_pause("I think it might work") > 0
