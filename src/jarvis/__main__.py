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
        bind_robot_tools(self.robot, self.presence)

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

        self._tts_queue: asyncio.Queue[str] = asyncio.Queue()
        self._tts_task: asyncio.Task[None] | None = None

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
                if not text.strip():
                    self.presence.signals.state = State.IDLE
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
            if assistant_busy and doa_speech is not None:
                is_speech = doa_speech
            elif doa_speech is not None:
                is_speech = silero_speech or doa_speech
            else:
                is_speech = silero_speech

            if is_speech:
                if not recording:
                    recording = True
                    self.presence.signals.state = State.LISTENING
                    log.debug("Speech detected")
                silence_start = None
                chunks.append(chunk_16k)

                if assistant_busy and not self._barge_in.is_set():
                    self._barge_in.set()
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

                if self.tts:
                    await self._tts_queue.put(sentence)
                else:
                    print(f"  JARVIS: {sentence}")

        finally:
            with suppress(Exception):
                await response_iter.aclose()
            with self._lock:
                self._speaking = False
            if not self._barge_in.is_set():
                self.presence.signals.state = State.IDLE

    async def _tts_loop(self) -> None:
        """Consume sentences and play TTS in order, with barge-in support."""
        assert self.tts is not None
        while True:
            sentence = await self._tts_queue.get()
            if self._barge_in.is_set():
                self._flush_output()
                self.presence.signals.speech_energy = 0.0
                continue

            async for audio_chunk in self.tts.stream_chunks_async(sentence):
                if self._barge_in.is_set():
                    self._flush_output()
                    self.presence.signals.speech_energy = 0.0
                    break
                self.presence.signals.speech_energy = float(
                    max(0.0, min(1.0, float(np.sqrt(np.mean(audio_chunk ** 2)) * 5.0)))
                )
                self._play_audio_chunk(audio_chunk)
                await asyncio.sleep(0)
            self.presence.signals.speech_energy = 0.0

    def _clear_tts_queue(self) -> None:
        while not self._tts_queue.empty():
            try:
                self._tts_queue.get_nowait()
            except asyncio.QueueEmpty:
                break


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
