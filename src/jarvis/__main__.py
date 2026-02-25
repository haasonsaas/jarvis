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

    def start(self) -> None:
        """Initialize all subsystems."""
        self.robot.connect()
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

    def stop(self) -> None:
        """Shut down all subsystems."""
        if self._output_stream:
            self._output_stream.stop()
            self._output_stream.close()
            self._output_stream = None

        if self._use_robot_audio:
            self.robot.stop_audio(recording=True, playing=True)

        if self.face_tracker:
            self.face_tracker.stop()
        if self.hand_tracker:
            self.hand_tracker.stop()
        self.presence.stop()
        self.robot.disconnect()
        log.info("Jarvis offline.")

    async def run(self) -> None:
        """Main conversation loop."""
        self.start()
        if self.tts is not None:
            self._tts_task = asyncio.create_task(self._tts_loop(), name="tts")
        self._listen_task = asyncio.create_task(self._listen_loop(), name="listen")
        print("\n  JARVIS is online. Speak to begin.\n")
        print("  Press Ctrl+C to exit.\n")

        try:
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
                    if self.tts:
                        await self._tts_queue.put((self._active_response_id, CONFIRMATION_PHRASE, True, 0.0))
                    else:
                        print(f"  JARVIS: {CONFIRMATION_PHRASE}")
                    self.presence.signals.state = State.LISTENING
                    continue

                # Get response from Claude and play it
                await self._respond_and_speak(text)

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

            silero_speech = conf > self.vad.threshold
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
                    data, overflowed = stream.read(CHUNK_SAMPLES)
                    if overflowed:
                        log.warning("Audio input buffer overflowed")
                    await process_chunk(data[:, 0])
                    await asyncio.sleep(0)

        else:
            pending = np.array([], dtype=np.float32)
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

                pending = np.concatenate([pending, mono_16k])
                while pending.size >= CHUNK_SAMPLES:
                    chunk = pending[:CHUNK_SAMPLES]
                    pending = pending[CHUNK_SAMPLES:]
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
            self._output_stream.write(audio_16k.reshape(-1, 1))

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
                    break

                if not self._response_started:
                    self._response_started = True
                    self._first_sentence_at = time.monotonic()
                    if self._response_start_at is not None:
                        log.info(
                            "LLM first sentence latency: %.0fms",
                            (self._first_sentence_at - self._response_start_at) * 1000.0,
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

            async for audio_chunk in self.tts.stream_chunks_async(sentence):
                if self._barge_in.is_set():
                    self._flush_output()
                    self.presence.signals.speech_energy = 0.0
                    break
                if not is_filler and response_id == self._active_response_id and self._first_audio_at is None:
                    self._first_audio_at = time.monotonic()
                    if self._response_start_at is not None:
                        log.info(
                            "TTS first audio latency: %.0fms",
                            (self._first_audio_at - self._response_start_at) * 1000.0,
                        )
                self.presence.signals.speech_energy = float(
                    max(0.0, min(1.0, float(np.sqrt(np.mean(audio_chunk ** 2)) * 5.0)))
                )
                normalized = self._normalize_tts_chunk(audio_chunk)
                self._play_audio_chunk(normalized)
                await asyncio.sleep(0)
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
        score = (0.6 * conf) + (0.3 * doa_score) + (0.1 * attention)
        threshold = TURN_TAKING_BARGE_IN_THRESHOLD if assistant_busy else TURN_TAKING_THRESHOLD
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
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        if rms <= 1e-6:
            return chunk
        desired_gain = max(0.5, min(2.0, TTS_TARGET_RMS / rms))
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

    try:
        loop.run_until_complete(task)
    finally:
        loop.close()


if __name__ == "__main__":
    main()
