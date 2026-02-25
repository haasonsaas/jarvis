"""Tests for jarvis.audio.stt."""

import numpy as np
from unittest.mock import MagicMock, patch


class TestSpeechToText:
    @patch("jarvis.audio.stt.WhisperModel")
    def test_init(self, mock_whisper_cls):
        from jarvis.audio.stt import SpeechToText
        SpeechToText(model_size="tiny.en")
        mock_whisper_cls.assert_called_once_with("tiny.en", compute_type="int8")

    @patch("jarvis.audio.stt.WhisperModel")
    def test_transcribe_joins_segments(self, mock_whisper_cls):
        mock_model = MagicMock()
        mock_whisper_cls.return_value = mock_model

        seg1 = MagicMock()
        seg1.text = " Hello "
        seg2 = MagicMock()
        seg2.text = " world "
        mock_model.transcribe.return_value = (iter([seg1, seg2]), MagicMock())

        from jarvis.audio.stt import SpeechToText
        stt = SpeechToText()

        audio = np.zeros(16000, dtype=np.float32)
        result = stt.transcribe(audio)
        assert result == "Hello world"

    @patch("jarvis.audio.stt.WhisperModel")
    def test_transcribe_empty_audio(self, mock_whisper_cls):
        mock_model = MagicMock()
        mock_whisper_cls.return_value = mock_model
        mock_model.transcribe.return_value = (iter([]), MagicMock())

        from jarvis.audio.stt import SpeechToText
        stt = SpeechToText()

        result = stt.transcribe(np.zeros(100, dtype=np.float32))
        assert result == ""

    @patch("jarvis.audio.stt.WhisperModel")
    def test_stereo_to_mono(self, mock_whisper_cls):
        mock_model = MagicMock()
        mock_whisper_cls.return_value = mock_model
        mock_model.transcribe.return_value = (iter([]), MagicMock())

        from jarvis.audio.stt import SpeechToText
        stt = SpeechToText()

        stereo = np.zeros((16000, 2), dtype=np.float32)
        stt.transcribe(stereo)

        # Should have been called with 1D mono audio
        call_audio = mock_model.transcribe.call_args[0][0]
        assert call_audio.ndim == 1

    @patch("jarvis.audio.stt.WhisperModel")
    def test_transcribe_resamples_non_16k(self, mock_whisper_cls):
        mock_model = MagicMock()
        mock_whisper_cls.return_value = mock_model
        mock_model.transcribe.return_value = (iter([]), MagicMock())

        from jarvis.audio.stt import SpeechToText
        stt = SpeechToText()

        audio = np.zeros(8000, dtype=np.float32)  # 1s at 8kHz
        stt.transcribe(audio, sample_rate=8000)

        call_audio = mock_model.transcribe.call_args[0][0]
        assert len(call_audio) == 16000

    @patch("jarvis.audio.stt.WhisperModel")
    def test_transcribe_rejects_invalid_sample_rate(self, mock_whisper_cls):
        mock_model = MagicMock()
        mock_whisper_cls.return_value = mock_model

        from jarvis.audio.stt import SpeechToText
        stt = SpeechToText()

        result = stt.transcribe(np.zeros(100, dtype=np.float32), sample_rate=0)
        assert result == ""
        mock_model.transcribe.assert_not_called()
