"""Tests for jarvis.audio.tts."""

import numpy as np
from unittest.mock import MagicMock, patch


class TestTextToSpeech:
    @patch("jarvis.audio.tts.ElevenLabs")
    def test_init(self, mock_eleven):
        from jarvis.audio.tts import TextToSpeech
        tts = TextToSpeech(api_key="test-key", voice_id="test-voice")

        mock_eleven.assert_called_once_with(api_key="test-key")
        assert tts._voice_id == "test-voice"

    @patch("jarvis.audio.tts.ElevenLabs")
    def test_stream_chunks_yields_float32(self, mock_eleven):
        mock_client = MagicMock()
        mock_eleven.return_value = mock_client

        # Simulate PCM int16 audio chunks from ElevenLabs
        pcm_data = np.array([0, 16384, -16384, 32767], dtype=np.int16).tobytes()
        mock_client.text_to_speech.stream.return_value = iter([pcm_data])

        from jarvis.audio.tts import TextToSpeech
        tts = TextToSpeech(api_key="test", voice_id="v1")

        chunks = list(tts.stream_chunks("hello"))
        assert len(chunks) == 1
        assert chunks[0].dtype == np.float32
        assert len(chunks[0]) == 4
        # Check normalization: 32767 -> ~1.0
        assert abs(chunks[0][3] - 1.0) < 0.001

    @patch("jarvis.audio.tts.ElevenLabs")
    def test_stream_chunks_skips_empty(self, mock_eleven):
        mock_client = MagicMock()
        mock_eleven.return_value = mock_client
        mock_client.text_to_speech.stream.return_value = iter([b"", b"", b"\x00\x00"])

        from jarvis.audio.tts import TextToSpeech
        tts = TextToSpeech(api_key="test", voice_id="v1")

        chunks = list(tts.stream_chunks("hello"))
        assert len(chunks) == 1  # only the non-empty one

    @patch("jarvis.audio.tts.ElevenLabs")
    def test_stream_chunks_handles_error(self, mock_eleven):
        mock_client = MagicMock()
        mock_eleven.return_value = mock_client
        mock_client.text_to_speech.stream.side_effect = RuntimeError("API error")

        from jarvis.audio.tts import TextToSpeech
        tts = TextToSpeech(api_key="test", voice_id="v1")

        chunks = list(tts.stream_chunks("hello"))
        assert chunks == []

    @patch("jarvis.audio.tts.ElevenLabs")
    def test_synthesize_concatenates(self, mock_eleven):
        mock_client = MagicMock()
        mock_eleven.return_value = mock_client

        chunk1 = np.array([100, 200], dtype=np.int16).tobytes()
        chunk2 = np.array([300, 400], dtype=np.int16).tobytes()
        mock_client.text_to_speech.stream.return_value = iter([chunk1, chunk2])

        from jarvis.audio.tts import TextToSpeech
        tts = TextToSpeech(api_key="test", voice_id="v1")

        audio = tts.synthesize("hello")
        assert audio.dtype == np.float32
        assert len(audio) == 4

    @patch("jarvis.audio.tts.ElevenLabs")
    def test_synthesize_empty_returns_empty(self, mock_eleven):
        mock_client = MagicMock()
        mock_eleven.return_value = mock_client
        mock_client.text_to_speech.stream.return_value = iter([])

        from jarvis.audio.tts import TextToSpeech
        tts = TextToSpeech(api_key="test", voice_id="v1")

        audio = tts.synthesize("hello")
        assert len(audio) == 0

    @patch("jarvis.audio.tts.ElevenLabs")
    def test_uses_flash_model(self, mock_eleven):
        mock_client = MagicMock()
        mock_eleven.return_value = mock_client
        mock_client.text_to_speech.stream.return_value = iter([])

        from jarvis.audio.tts import TextToSpeech
        tts = TextToSpeech(api_key="test", voice_id="v1")
        list(tts.stream_chunks("test"))

        call_kwargs = mock_client.text_to_speech.stream.call_args.kwargs
        assert call_kwargs["model_id"] == "eleven_flash_v2_5"
        assert call_kwargs["optimize_streaming_latency"] == 3
