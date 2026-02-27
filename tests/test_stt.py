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

    @patch("jarvis.audio.stt.WhisperModel")
    def test_transcribe_with_diagnostics_returns_confidence_fields(self, mock_whisper_cls):
        mock_model = MagicMock()
        mock_whisper_cls.return_value = mock_model

        seg1 = MagicMock()
        seg1.text = "Hello"
        seg1.avg_logprob = -0.4
        seg1.no_speech_prob = 0.1
        seg2 = MagicMock()
        seg2.text = "world"
        seg2.avg_logprob = -0.3
        seg2.no_speech_prob = 0.05
        info = MagicMock(language="en", language_probability=0.98)
        mock_model.transcribe.return_value = (iter([seg1, seg2]), info)

        from jarvis.audio.stt import SpeechToText
        stt = SpeechToText()
        text, diagnostics = stt.transcribe_with_diagnostics(np.ones(16000, dtype=np.float32))

        assert text == "Hello world"
        assert diagnostics["confidence_band"] in {"medium", "high"}
        assert diagnostics["confidence_score"] > 0.5
        assert diagnostics["word_count"] == 2
        assert diagnostics["language"] == "en"
        assert diagnostics["language_probability"] == 0.98
        assert diagnostics["segment_count"] == 2

    @patch("jarvis.audio.stt.WhisperModel")
    def test_transcribe_with_diagnostics_handles_model_failure(self, mock_whisper_cls):
        mock_model = MagicMock()
        mock_whisper_cls.return_value = mock_model
        mock_model.transcribe.side_effect = RuntimeError("boom")

        from jarvis.audio.stt import SpeechToText
        stt = SpeechToText()
        text, diagnostics = stt.transcribe_with_diagnostics(np.ones(16000, dtype=np.float32))

        assert text == ""
        assert diagnostics["confidence_score"] == 0.0
        assert diagnostics["confidence_band"] == "unknown"
        assert diagnostics["error"] == "transcription_failed"
