"""Jarvis — main conversation loop.

Pipeline:
  1. Presence loop runs continuously (idle breathing, micro-behaviors)
  2. VAD detects speech → state = LISTENING → STT captures utterance
  3. On end-of-utterance → state = THINKING → Claude streams response
  4. TTS streams sentences as they arrive → state = SPEAKING
  5. Barge-in: VAD during playback → stop TTS, feed new utterance
  6. Back to idle

Face tracking runs in parallel, feeding into the presence loop signals.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import logging
import signal
import time
import threading
from collections import deque
from contextlib import suppress

import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly

from jarvis.config import Config
from jarvis.robot.controller import RobotController
from jarvis.presence import PresenceLoop, State
from jarvis.audio.vad import VoiceActivityDetector, CHUNK_SAMPLES
from jarvis.audio.stt import SpeechToText
from jarvis.audio.tts import TextToSpeech
from jarvis.brain import Brain
from jarvis.tools.robot import bind as bind_robot_tools
from jarvis.tool_summary import list_summaries

log = logging.getLogger(__name__)

# Audio constants
SILENCE_TIMEOUT = 0.8   # seconds of silence before end-of-utterance
MIN_UTTERANCE = 0.3     # minimum utterance length in seconds
TURN_TAKING_THRESHOLD = 0.55
TURN_TAKING_BARGE_IN_THRESHOLD = 0.4
ATTENTION_RECENCY_SEC = 1.0
THINKING_FILLER_DELAY = 0.35
THINKING_FILLER_TEXT = "One moment."
TTS_TARGET_RMS = 0.08
TTS_GAIN_SMOOTH = 0.2
TTS_SENTENCE_PAUSE_SEC = 0.12
TTS_CONFIDENCE_PAUSE_SEC = 0.18
TTS_LOW_CONFIDENCE_WORDS = {"maybe", "probably", "might", "not sure", "uncertain", "I think", "I believe"}
INTENDED_QUERY_MIN_ATTENTION = 0.35
CONFIRMATION_PHRASE = "Did you mean me?"
AFFIRMATIONS = {"yes", "yeah", "yep", "yup", "correct", "affirmative", "sure", "please"}
NEGATIONS = {"no", "nope", "nah", "negative"}
TELEMETRY_LOG_EVERY_TURNS = 5
TELEMETRY_STORAGE_ERROR_DETAILS = {
    "storage_error",
    "missing_store",
}
TELEMETRY_SERVICE_ERROR_DETAILS = {
    "policy",
    "missing_config",
    "missing_fields",
    "invalid_data",
    "timeout",
    "cancelled",
    "network_client_error",
    "invalid_json",
    "api_error",
    "auth",
    "not_found",
    "unexpected",
    "missing_text",
    "missing_query",
    "missing_entity",
    "missing_plan",
    "invalid_plan",
    "invalid_status",
    "invalid_steps",
    "http_error",
    "summary_unavailable",
    "unknown_error",
}


def _to_mono(audio: np.ndarray) -> np.ndarray:
    """Convert arbitrary audio frame to 1D float32 mono."""
    a = np.asarray(audio, dtype=np.float32)
    if a.ndim == 1:
        return a
    if a.ndim != 2:
        return a.reshape(-1).astype(np.float32, copy=False)

    # Heuristic: if channels appear first, transpose.
    if a.shape[0] <= 8 and a.shape[0] < a.shape[1]:
        a = a.T

    if a.shape[1] == 1:
        return a[:, 0]
    return a.mean(axis=1)


def _resample_audio(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or x.size == 0:
        return x.astype(np.float32, copy=False)

    g = math.gcd(int(sr_in), int(sr_out))
    up = int(sr_out) // g
    down = int(sr_in) // g
    y = resample_poly(x.astype(np.float32, copy=False), up=up, down=down)
    return y.astype(np.float32, copy=False)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Jarvis AI Assistant on Reachy Mini")
    p.add_argument("--sim", action="store_true", help="Simulation mode (no robot)")
    p.add_argument("--no-vision", action="store_true", help="Disable face tracking")
    p.add_argument("--no-motion", action="store_true", help="Disable robot motion")
    p.add_argument("--no-hands", action="store_true", help="Disable hand tracking")
    p.add_argument("--no-home", action="store_true", help="Disable smart home tools")
    p.add_argument("--no-tts", action="store_true", help="Print responses instead of speaking")
    p.add_argument("--debug", action="store_true", help="Verbose logging")
    return p.parse_args()


class Jarvis:
    """Main application orchestrating all subsystems."""

    def __init__(self, args: argparse.Namespace):
        self.config = Config()
        self.args = args

        # Robot
        self.robot = RobotController(
            host=self.config.reachy_host,
            sim=args.sim,
            connection_mode=self.config.reachy_connection_mode,
            media_backend=self.config.reachy_media_backend,
            automatic_body_yaw=self.config.reachy_automatic_body_yaw,
        )

        # Presence loop (the soul)
        self.presence = PresenceLoop(self.robot)
        self.presence.set_backchannel_style(self.config.backchannel_style)
        if getattr(args, "no_motion", False):
            self.config.motion_enabled = False
        if getattr(args, "no_home", False):
            self.config.home_enabled = False
        if getattr(args, "no_hands", False):
            self.config.hand_track_enabled = False

        # Bind tools to robot + presence
        bind_robot_tools(self.robot, self.presence, self.config)

        # Audio
        self.vad = VoiceActivityDetector(
            threshold=self.config.vad_threshold,
            sample_rate=self.config.sample_rate,
        )
        self.stt = SpeechToText(model_size=self.config.whisper_model)
        self.tts = TextToSpeech(
            api_key=self.config.elevenlabs_api_key,
            voice_id=self.config.elevenlabs_voice_id,
            sample_rate=self.config.sample_rate,
        ) if not args.no_tts and self.config.elevenlabs_api_key else None

        # Brain
        self.brain = Brain(self.config, self.presence)

        # Face tracker (lazy init)
        self.face_tracker = None
        self.hand_tracker = None

        # Barge-in control — use a lock for thread safety
        self._lock = threading.Lock()
        self._speaking = False
        self._barge_in = threading.Event()

        self._use_robot_audio = False
        self._robot_input_sr = self.config.sample_rate
        self._robot_output_sr = self.config.sample_rate

        self._last_doa_angle: float | None = None
        self._last_doa_update: float = 0.0
        self._last_doa_speech: bool | None = None
        self._awaiting_confirmation = False
        self._pending_text: str | None = None

        self._tts_queue: asyncio.Queue[tuple[int, str, bool, float]] = asyncio.Queue()
        self._tts_task: asyncio.Task[None] | None = None
        self._response_id = 0
        self._active_response_id = 0
        self._response_started = False
        self._first_sentence_at: float | None = None
        self._first_audio_at: float | None = None
        self._response_start_at: float | None = None
        self._filler_task: asyncio.Task[None] | None = None
        self._tts_gain = 1.0

        self._utterance_queue: asyncio.Queue[np.ndarray] = asyncio.Queue(maxsize=1)
        self._listen_task: asyncio.Task[None] | None = None

        # Audio output stream (persistent, avoids open/close per chunk)
        self._output_stream: sd.OutputStream | None = None
        self._started = False
        self._telemetry: dict[str, float] = {
            "turns": 0.0,
            "barge_ins": 0.0,
            "stt_latency_total_ms": 0.0,
            "stt_latency_count": 0.0,
            "llm_first_sentence_total_ms": 0.0,
            "llm_first_sentence_count": 0.0,
            "tts_first_audio_total_ms": 0.0,
            "tts_first_audio_count": 0.0,
            "service_errors": 0.0,
            "storage_errors": 0.0,
            "fallback_responses": 0.0,
        }

    def start(self) -> None:
        """Initialize all subsystems."""
        if self._started:
            return
        self._started = True
        try:
            self.robot.connect()
            if self.config.motion_enabled:
                self.presence.start()

            self._use_robot_audio = not self.robot.sim

            if not self.args.no_vision and not self.robot.sim:
                from jarvis.vision.face_tracker import FaceTracker
                self.face_tracker = FaceTracker(
                    presence=self.presence,
                    get_frame=self.robot.get_frame,
                    model_path=self.config.yolo_model,
                    fps=self.config.face_track_fps,
                )
                self.face_tracker.start()

                if self.config.hand_track_enabled:
                    from jarvis.vision.hand_tracker import HandTracker
                    self.hand_tracker = HandTracker(
                        presence=self.presence,
                        get_frame=self.robot.get_frame,
                        fps=self.config.face_track_fps,
                    )
                    self.hand_tracker.start()

            if self._use_robot_audio:
                self.robot.start_audio(recording=True, playing=self.tts is not None)
                time.sleep(0.2)  # give media pipelines a moment to warm up
                self._robot_input_sr = self.robot.get_input_audio_samplerate() or self.config.sample_rate
                self._robot_output_sr = self.robot.get_output_audio_samplerate() or self.config.sample_rate
                log.info(
                    "Using Reachy Mini media audio (in=%dHz out=%dHz)",
                    self._robot_input_sr,
                    self._robot_output_sr,
                )
            else:
                if self.tts is not None:
                    # Open persistent audio output stream
                    self._output_stream = sd.OutputStream(
                        samplerate=self.config.sample_rate,
                        channels=1,
                        dtype="float32",
                    )
                    self._output_stream.start()

            log.info("Jarvis is online.")
        except Exception:
            self.stop()
            raise

    def _startup_summary_lines(self) -> list[str]:
        tts_enabled = bool(self.tts is not None)
        tts_reason = "enabled" if tts_enabled else "disabled (no ELEVENLABS_API_KEY or --no-tts)"
        memory_state = "enabled" if self.config.memory_enabled else "disabled"
        warning_count = len(getattr(self.config, "startup_warnings", []))
        return [
            f"Mode: {'simulation' if self.robot.sim else 'hardware'}",
            f"Motion: {'on' if self.config.motion_enabled else 'off'} | Vision: {'on' if not self.args.no_vision and not self.robot.sim else 'off'} | Hands: {'on' if self.config.hand_track_enabled else 'off'}",
            f"Home tools: {'on' if self.config.home_enabled else 'off'}",
            f"TTS: {tts_reason}",
            f"Memory: {memory_state} ({self.config.memory_path})",
            f"Persona style: {self.config.persona_style}",
            f"Config warnings: {warning_count}",
            f"Tool policy: allow={len(self.config.tool_allowlist)} deny={len(self.config.tool_denylist)}",
        ]

    def _refresh_tool_error_counters(self) -> None:
        try:
            recent = list_summaries(limit=200)
        except Exception:
            return
        service_errors = 0
        storage_errors = 0
        for item in recent:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status", ""))
            detail = str(item.get("detail", ""))
            if status != "error":
                continue
            if detail in TELEMETRY_STORAGE_ERROR_DETAILS:
                storage_errors += 1
                continue
            if detail in TELEMETRY_SERVICE_ERROR_DETAILS:
                service_errors += 1
        self._telemetry["service_errors"] = float(service_errors)
        self._telemetry["storage_errors"] = float(storage_errors)

    def _telemetry_snapshot(self) -> dict[str, float]:
        def avg(total_key: str, count_key: str) -> float:
            count = self._telemetry.get(count_key, 0.0)
            if count <= 0:
                return 0.0
            return self._telemetry.get(total_key, 0.0) / count

        return {
            "turns": self._telemetry.get("turns", 0.0),
            "barge_ins": self._telemetry.get("barge_ins", 0.0),
            "avg_stt_latency_ms": avg("stt_latency_total_ms", "stt_latency_count"),
            "avg_llm_first_sentence_ms": avg("llm_first_sentence_total_ms", "llm_first_sentence_count"),
            "avg_tts_first_audio_ms": avg("tts_first_audio_total_ms", "tts_first_audio_count"),
            "service_errors": self._telemetry.get("service_errors", 0.0),
            "storage_errors": self._telemetry.get("storage_errors", 0.0),
            "fallback_responses": self._telemetry.get("fallback_responses", 0.0),
        }

    def stop(self) -> None:
        """Shut down all subsystems."""
        if not self._started:
            return
        if self._output_stream:
            with suppress(Exception):
                self._output_stream.stop()
            with suppress(Exception):
                self._output_stream.close()
            self._output_stream = None
        if self.face_tracker:
            with suppress(Exception):
                self.face_tracker.stop()
            self.face_tracker = None
        if self._use_robot_audio:
            with suppress(Exception):
                self.robot.stop_audio(recording=True, playing=True)
        if self.hand_tracker:
            with suppress(Exception):
                self.hand_tracker.stop()
            self.hand_tracker = None
        if self.config.motion_enabled:
            with suppress(Exception):
                self.presence.stop()
        with suppress(Exception):
            self.robot.disconnect()
        self._started = False
        log.info("Jarvis offline.")

    async def run(self) -> None:
        """Main conversation loop."""
        try:
            self.start()
            if self.tts is not None:
                self._tts_task = asyncio.create_task(self._tts_loop(), name="tts")
            self._listen_task = asyncio.create_task(self._listen_loop(), name="listen")
            print("\n  JARVIS is online. Speak to begin.\n")
            print("  Press Ctrl+C to exit.\n")
            for line in self._startup_summary_lines():
                print(f"  {line}")
            for warning in getattr(self.config, "startup_warnings", []):
                print(f"  WARNING: {warning}")
            print("")

            while True:
                utterance = await self._utterance_queue.get()

                # Transcribe (run in executor to not block event loop)
                self.presence.signals.state = State.THINKING
                text = await asyncio.get_event_loop().run_in_executor(
                    None, self.stt.transcribe, utterance
                )
                stt_elapsed = time.monotonic() - self._last_doa_update if self._last_doa_update else None
                if stt_elapsed is not None:
                    log.info("STT latency: %.0fms", stt_elapsed * 1000.0)
                    self._telemetry["stt_latency_total_ms"] += stt_elapsed * 1000.0
                    self._telemetry["stt_latency_count"] += 1.0
                if not text.strip():
                    self.presence.signals.state = State.IDLE
                    continue

                if self._awaiting_confirmation:
                    normalized = text.strip().lower()
                    if normalized in AFFIRMATIONS and self._pending_text:
                        self._awaiting_confirmation = False
                        text = self._pending_text
                        self._pending_text = None
                    elif normalized in NEGATIONS:
                        self._awaiting_confirmation = False
                        self._pending_text = None
                        if self.tts:
                            await self._tts_queue.put((self._active_response_id, "Understood.", True, 0.0))
                        else:
                            print("  JARVIS: Understood.")
                        self.presence.signals.state = State.IDLE
                        continue
                    else:
                        self._awaiting_confirmation = False
                        self._pending_text = None

                if self._requires_confirmation(time.monotonic()):
                    self._awaiting_confirmation = True
                    self._pending_text = text
                    self._telemetry["fallback_responses"] += 1.0
                    if self.tts:
                        await self._tts_queue.put((self._active_response_id, CONFIRMATION_PHRASE, True, 0.0))
                    else:
                        print(f"  JARVIS: {CONFIRMATION_PHRASE}")
                    self.presence.signals.state = State.LISTENING
                    continue

                # Get response from Claude and play it
                self._telemetry["turns"] += 1.0
                await self._respond_and_speak(text)
                if int(self._telemetry["turns"]) % TELEMETRY_LOG_EVERY_TURNS == 0:
                    self._refresh_tool_error_counters()
                    snapshot = self._telemetry_snapshot()
                    attention_source = self.presence.attention_source()
                    log.info(
                        "Telemetry turns=%d barge_ins=%d stt=%.0fms llm=%.0fms tts=%.0fms service_errors=%d storage_errors=%d fallbacks=%d attention=%s",
                        int(snapshot["turns"]),
                        int(snapshot["barge_ins"]),
                        snapshot["avg_stt_latency_ms"],
                        snapshot["avg_llm_first_sentence_ms"],
                        snapshot["avg_tts_first_audio_ms"],
                        int(snapshot["service_errors"]),
                        int(snapshot["storage_errors"]),
                        int(snapshot["fallback_responses"]),
                        attention_source,
                    )

        except asyncio.CancelledError:
            pass
        finally:
            if self._listen_task is not None:
                self._listen_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._listen_task
                self._listen_task = None
            if self._tts_task is not None:
                self._tts_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._tts_task
                self._tts_task = None
            if self._filler_task is not None:
                self._filler_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._filler_task
                self._filler_task = None
            with suppress(Exception):
                await self.brain.close()
            self.stop()

    async def _enqueue_utterance(self, audio: np.ndarray) -> None:
        try:
            self._utterance_queue.put_nowait(audio)
        except asyncio.QueueFull:
            with suppress(asyncio.QueueEmpty):
                self._utterance_queue.get_nowait()
            await self._utterance_queue.put(audio)

    async def _listen_loop(self) -> None:
        """Continuously segment microphone audio into utterances.

        Runs during the entire app lifetime so barge-in works while Jarvis is speaking.
        """

        chunks: list[np.ndarray] = []
        silence_start: float | None = None
        recording = False

        async def process_chunk(chunk_16k: np.ndarray) -> None:
            nonlocal chunks, silence_start, recording

            # Presence signals
            conf = self.vad.confidence(chunk_16k)
            self.presence.signals.vad_energy = max(0.0, min(1.0, conf))
            doa_angle, doa_speech = self.robot.get_doa()
            now = time.monotonic()
            self._last_doa_speech = doa_speech
            if doa_angle is not None:
                if doa_speech is None or doa_speech:
                    if self._last_doa_angle is None or abs(doa_angle - self._last_doa_angle) >= self.config.doa_change_threshold:
                        self._last_doa_angle = doa_angle
                        self._last_doa_update = now
                        self.presence.signals.doa_angle = doa_angle
                        self.presence.signals.doa_last_seen = now
                else:
                    if self._last_doa_update and (now - self._last_doa_update) > self.config.doa_timeout:
                        self.presence.signals.doa_angle = None
                        self._last_doa_angle = None
            else:
                if self._last_doa_update and (now - self._last_doa_update) > self.config.doa_timeout:
                    self.presence.signals.doa_angle = None
                    self._last_doa_angle = None

            with self._lock:
                assistant_busy = self._speaking

            is_speech = self._compute_turn_taking(
                conf=conf,
                doa_speech=doa_speech,
                assistant_busy=assistant_busy,
                now=now,
            )

            if is_speech:
                if not recording:
                    recording = True
                    self.presence.signals.state = State.LISTENING
                    log.debug("Speech detected")
                silence_start = None
                chunks.append(chunk_16k)

                if assistant_busy and not self._barge_in.is_set():
                    self._barge_in.set()
                    self._flush_output()
                    self._clear_tts_queue()
                    self.presence.signals.state = State.LISTENING
                    self._telemetry["barge_ins"] += 1.0
                    log.info("Barge-in detected")

            elif recording:
                chunks.append(chunk_16k)
                if silence_start is None:
                    silence_start = time.monotonic()
                elif time.monotonic() - silence_start > SILENCE_TIMEOUT:
                    audio = np.concatenate(chunks) if chunks else np.array([], dtype=np.float32)

                    # Reset for the next utterance.
                    self.vad.reset()
                    self.presence.signals.vad_energy = 0.0
                    chunks = []
                    silence_start = None
                    recording = False

                    if audio.size == 0:
                        return

                    duration = len(audio) / self.config.sample_rate
                    if duration >= MIN_UTTERANCE:
                        await self._enqueue_utterance(audio)

        if not self._use_robot_audio:
            with sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=1,
                dtype="float32",
                blocksize=CHUNK_SAMPLES,
            ) as stream:
                while True:
                    data, overflowed = await asyncio.to_thread(stream.read, CHUNK_SAMPLES)
                    if overflowed:
                        log.warning("Audio input buffer overflowed")
                    await process_chunk(data[:, 0])
                    await asyncio.sleep(0)

        else:
            pending_chunks: deque[np.ndarray] = deque()
            pending_len = 0
            while True:
                raw = self.robot.get_audio_sample()
                if raw is None:
                    await asyncio.sleep(0.005)
                    continue

                mono = _to_mono(raw)
                mono_16k = _resample_audio(mono, self._robot_input_sr, self.config.sample_rate)
                if mono_16k.size == 0:
                    await asyncio.sleep(0)
                    continue

                pending_chunks.append(mono_16k)
                pending_len += int(mono_16k.size)

                while pending_len >= CHUNK_SAMPLES:
                    needed = CHUNK_SAMPLES
                    parts: list[np.ndarray] = []
                    while needed > 0 and pending_chunks:
                        head = pending_chunks[0]
                        if head.size <= needed:
                            parts.append(head)
                            pending_chunks.popleft()
                            needed -= int(head.size)
                        else:
                            parts.append(head[:needed])
                            pending_chunks[0] = head[needed:]
                            needed = 0
                    if not parts:
                        break
                    chunk = parts[0] if len(parts) == 1 else np.concatenate(parts)
                    pending_len -= CHUNK_SAMPLES
                    await process_chunk(chunk)

                await asyncio.sleep(0)

    def _flush_output(self) -> None:
        if self._use_robot_audio:
            self.robot.flush_audio_output()
            return

        if self._output_stream is None:
            return

        try:
            self._output_stream.abort()
        except Exception:
            try:
                self._output_stream.stop()
            except Exception:
                pass

        try:
            self._output_stream.start()
        except Exception:
            pass

    def _play_audio_chunk(self, audio_16k: np.ndarray) -> None:
        if audio_16k.size == 0:
            return

        if self._use_robot_audio:
            audio_out = audio_16k
            if self._robot_output_sr != self.config.sample_rate:
                audio_out = _resample_audio(audio_16k, self.config.sample_rate, self._robot_output_sr)
            self.robot.push_audio_sample(audio_out)
            return

        if self._output_stream is not None:
            try:
                self._output_stream.write(audio_16k.reshape(-1, 1))
            except Exception as e:
                log.warning("Audio output write failed: %s", e)

    async def _respond_and_speak(self, text: str) -> None:
        """Get Claude's response and stream TTS with barge-in support."""
        self._barge_in.clear()
        self._clear_tts_queue()
        self._response_id += 1
        self._active_response_id = self._response_id
        self._response_started = False
        self._first_sentence_at = None
        self._first_audio_at = None
        self._response_start_at = time.monotonic()
        self._tts_gain = 1.0

        if self._filler_task is not None:
            self._filler_task.cancel()
        if self.tts is not None:
            self._filler_task = asyncio.create_task(self._thinking_filler(), name="thinking-filler")

        with self._lock:
            self._speaking = True

        response_iter = self.brain.respond(text)

        try:
            async for sentence in response_iter:
                if self._barge_in.is_set():
                    log.info("Barge-in — stopping response")
                    self._flush_output()
                    self._clear_tts_queue()
                    self.robot.stop_sequence()
                    break

                if not self._response_started:
                    self._response_started = True
                    self._first_sentence_at = time.monotonic()
                    if self._response_start_at is not None:
                        latency_ms = (self._first_sentence_at - self._response_start_at) * 1000.0
                        self._telemetry["llm_first_sentence_total_ms"] += latency_ms
                        self._telemetry["llm_first_sentence_count"] += 1.0
                        log.info(
                            "LLM first sentence latency: %.0fms",
                            latency_ms,
                        )
                    if self._filler_task is not None:
                        self._filler_task.cancel()

                if self.tts:
                    pause = self._confidence_pause(sentence)
                    await self._tts_queue.put((self._active_response_id, sentence, False, pause))
                else:
                    print(f"  JARVIS: {sentence}")

        finally:
            with suppress(Exception):
                await response_iter.aclose()
            with self._lock:
                self._speaking = False
            if not self._barge_in.is_set():
                self.presence.signals.state = State.IDLE
            if self._filler_task is not None:
                self._filler_task.cancel()

    async def _tts_loop(self) -> None:
        """Consume sentences and play TTS in order, with barge-in support."""
        assert self.tts is not None
        while True:
            response_id, sentence, is_filler, pause = await self._tts_queue.get()
            if self._barge_in.is_set():
                self._flush_output()
                self.presence.signals.speech_energy = 0.0
                continue

            try:
                async for audio_chunk in self.tts.stream_chunks_async(sentence):
                    if self._barge_in.is_set():
                        self._flush_output()
                        self.presence.signals.speech_energy = 0.0
                        break
                    if not is_filler and response_id == self._active_response_id and self._first_audio_at is None:
                        self._first_audio_at = time.monotonic()
                        if self._response_start_at is not None:
                            latency_ms = (self._first_audio_at - self._response_start_at) * 1000.0
                            self._telemetry["tts_first_audio_total_ms"] += latency_ms
                            self._telemetry["tts_first_audio_count"] += 1.0
                            log.info(
                                "TTS first audio latency: %.0fms",
                                latency_ms,
                            )
                    self.presence.signals.speech_energy = float(
                        max(0.0, min(1.0, float(np.sqrt(np.mean(audio_chunk ** 2)) * 5.0)))
                    )
                    normalized = self._normalize_tts_chunk(audio_chunk)
                    self._play_audio_chunk(normalized)
                    await asyncio.sleep(0)
            except Exception as e:
                log.warning("TTS loop failed for sentence chunk: %s", e)
            self.presence.signals.speech_energy = 0.0
            if pause > 0:
                await asyncio.sleep(pause)

    def _clear_tts_queue(self) -> None:
        while not self._tts_queue.empty():
            try:
                self._tts_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def _compute_turn_taking(
        self,
        conf: float,
        doa_speech: bool | None,
        assistant_busy: bool,
        now: float,
    ) -> bool:
        attention = 0.0
        if self.presence.signals.face_last_seen and (now - self.presence.signals.face_last_seen) <= ATTENTION_RECENCY_SEC:
            attention = 1.0
        elif self.presence.signals.hand_last_seen and (now - self.presence.signals.hand_last_seen) <= ATTENTION_RECENCY_SEC:
            attention = 0.8
        elif self.presence.signals.doa_last_seen and (now - self.presence.signals.doa_last_seen) <= ATTENTION_RECENCY_SEC:
            attention = 0.5

        doa_score = 1.0 if doa_speech else 0.0
        score = (0.55 * conf) + (0.3 * doa_score) + (0.15 * attention)
        threshold = TURN_TAKING_BARGE_IN_THRESHOLD if assistant_busy else TURN_TAKING_THRESHOLD

        if assistant_busy:
            if doa_speech is True:
                return score >= (threshold - 0.05)
            if conf >= 0.8 and attention >= 0.8:
                return True
            if conf < 0.35 and attention < 0.6 and doa_speech is False:
                return False

        if conf >= 0.9 and attention >= 0.8:
            return True
        if conf < 0.25 and attention < 0.5 and doa_speech is False:
            return False
        return score >= threshold

    def _attention_confidence(self, now: float) -> float:
        if self.presence.signals.face_last_seen and (now - self.presence.signals.face_last_seen) <= ATTENTION_RECENCY_SEC:
            return 1.0
        if self.presence.signals.hand_last_seen and (now - self.presence.signals.hand_last_seen) <= ATTENTION_RECENCY_SEC:
            return 0.8
        if self.presence.signals.doa_last_seen and (now - self.presence.signals.doa_last_seen) <= ATTENTION_RECENCY_SEC:
            return 0.5
        return 0.0

    def _requires_confirmation(self, now: float) -> bool:
        attention = self._attention_confidence(now)
        if attention >= INTENDED_QUERY_MIN_ATTENTION:
            return False
        if self._last_doa_speech is True:
            return False
        return True

    async def _thinking_filler(self) -> None:
        await asyncio.sleep(THINKING_FILLER_DELAY)
        if self._barge_in.is_set() or self._response_started:
            return
        if self.tts is None:
            return
        await self._tts_queue.put((self._active_response_id, THINKING_FILLER_TEXT, True, 0.0))

    def _normalize_tts_chunk(self, chunk: np.ndarray) -> np.ndarray:
        if chunk.size == 0:
            return chunk
        if not np.isfinite(chunk).all():
            chunk = np.nan_to_num(chunk, nan=0.0, posinf=1.0, neginf=-1.0)
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        if not np.isfinite(rms) or rms <= 1e-6:
            return chunk
        desired_gain = max(0.5, min(2.0, TTS_TARGET_RMS / rms))
        if not np.isfinite(desired_gain):
            desired_gain = 1.0
        self._tts_gain += (desired_gain - self._tts_gain) * TTS_GAIN_SMOOTH
        normalized = chunk * self._tts_gain
        return np.clip(normalized, -1.0, 1.0)

    def _confidence_pause(self, sentence: str) -> float:
        lowered = sentence.lower()
        if any(token in lowered for token in TTS_LOW_CONFIDENCE_WORDS):
            return TTS_CONFIDENCE_PAUSE_SEC
        return TTS_SENTENCE_PAUSE_SEC


def main():
    args = parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(name)-25s %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    )

    jarvis = Jarvis(args)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    task = loop.create_task(jarvis.run())

    def shutdown(sig, frame):
        task.cancel()

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(task)
    finally:
        with suppress(Exception):
            loop.run_until_complete(loop.shutdown_asyncgens())
        with suppress(Exception):
            loop.run_until_complete(loop.shutdown_default_executor())
        loop.close()


if __name__ == "__main__":
    main()
