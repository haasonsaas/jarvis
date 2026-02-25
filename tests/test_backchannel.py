import time

from jarvis.presence import PresenceLoop, State


def test_backchannel_nod_triggers(mock_robot):
    presence = PresenceLoop(mock_robot)
    sig = presence.signals
    sig.state = State.LISTENING
    sig.vad_energy = 0.4
    sig.face_last_seen = time.monotonic()

    before = presence._backchannel_next_allowed
    nod = presence._backchannel_nod(time.monotonic(), sig, time.monotonic())
    assert nod != 0.0
    assert presence._backchannel_next_allowed > before


def test_backchannel_requires_attention(mock_robot):
    presence = PresenceLoop(mock_robot)
    sig = presence.signals
    sig.state = State.LISTENING
    sig.vad_energy = 0.4

    nod = presence._backchannel_nod(time.monotonic(), sig, time.monotonic())
    assert nod == 0.0
