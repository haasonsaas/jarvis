import time

from jarvis.presence import PresenceLoop, State


def test_backchannel_nod_triggers(mock_robot):
    presence = PresenceLoop(mock_robot)
    presence.set_backchannel_style("expressive")
    sig = presence.signals
    sig.state = State.LISTENING
    sig.vad_energy = 0.4
    sig.face_last_seen = time.monotonic()

    before = presence._backchannel_next_allowed
    nod = presence._backchannel_nod(time.monotonic(), sig, time.monotonic())
    assert nod != 0.0
    assert presence._backchannel_next_allowed > before


def test_backchannel_quiet_style_scales_down(mock_robot):
    presence = PresenceLoop(mock_robot)
    sig = presence.signals
    sig.state = State.LISTENING
    sig.vad_energy = 0.4
    sig.face_last_seen = time.monotonic()

    presence.set_backchannel_style("expressive")
    loud = abs(presence._backchannel_nod(time.monotonic(), sig, time.monotonic()))

    presence.set_backchannel_style("quiet")
    quiet = abs(presence._backchannel_nod(time.monotonic(), sig, time.monotonic()))

    assert quiet <= loud


def test_backchannel_requires_attention(mock_robot):
    presence = PresenceLoop(mock_robot)
    sig = presence.signals
    sig.state = State.LISTENING
    sig.vad_energy = 0.4

    nod = presence._backchannel_nod(time.monotonic(), sig, time.monotonic())
    assert nod == 0.0


def test_backchannel_intensity_scales_with_attention(mock_robot):
    presence = PresenceLoop(mock_robot)
    sig = presence.signals
    sig.state = State.LISTENING
    sig.vad_energy = 0.4

    now = time.monotonic()
    sig.doa_last_seen = now
    low = abs(presence._backchannel_nod(now, sig, now))

    sig.doa_last_seen = None
    sig.face_last_seen = time.monotonic()
    mid = abs(presence._backchannel_nod(time.monotonic(), sig, time.monotonic()))

    assert mid >= low
