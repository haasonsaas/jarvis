"""Tests for jarvis.audio.vad."""

import pytest
import numpy as np
import warnings
from unittest.mock import MagicMock, patch


class TestVoiceActivityDetector:
    @patch("jarvis.audio.vad.load_silero_vad")
    @patch("jarvis.audio.vad.VADIterator")
    def test_init(self, mock_vad_iter, mock_load):
        mock_model = MagicMock()
        mock_load.return_value = mock_model

        from jarvis.audio.vad import VoiceActivityDetector
        vad = VoiceActivityDetector(threshold=0.6)

        mock_load.assert_called_once()
        mock_vad_iter.assert_called_once()
        assert vad._threshold == 0.6

    @patch("jarvis.audio.vad.load_silero_vad")
    @patch("jarvis.audio.vad.VADIterator")
    def test_init_suppresses_known_torch_jit_deprecation(self, mock_vad_iter, mock_load):
        mock_model = MagicMock()

        def _load_with_warning():
            warnings.warn(
                "`torch.jit.load` is deprecated. Please switch to `torch.export`.",
                DeprecationWarning,
                stacklevel=1,
            )
            return mock_model

        mock_load.side_effect = _load_with_warning

        from jarvis.audio.vad import VoiceActivityDetector

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            VoiceActivityDetector(threshold=0.5)

        assert caught == []

    @patch("jarvis.audio.vad.load_silero_vad")
    @patch("jarvis.audio.vad.VADIterator")
    def test_invalid_sample_rate_raises(self, mock_vad_iter, mock_load):
        mock_load.return_value = MagicMock()

        from jarvis.audio.vad import VoiceActivityDetector
        with pytest.raises(ValueError, match="16kHz"):
            VoiceActivityDetector(sample_rate=44100)

    @patch("jarvis.audio.vad.load_silero_vad")
    @patch("jarvis.audio.vad.VADIterator")
    def test_wrong_chunk_size_raises(self, mock_vad_iter, mock_load):
        import torch
        mock_model = MagicMock()
        mock_model.return_value = torch.tensor(0.3)
        mock_load.return_value = mock_model

        from jarvis.audio.vad import VoiceActivityDetector
        vad = VoiceActivityDetector()

        wrong_size = np.zeros(480, dtype=np.float32)  # 30ms, not 32ms
        with pytest.raises(ValueError, match="512"):
            vad.is_speech(wrong_size)

    @patch("jarvis.audio.vad.load_silero_vad")
    @patch("jarvis.audio.vad.VADIterator")
    def test_is_speech_true(self, mock_vad_iter, mock_load):
        import torch
        mock_model = MagicMock()
        mock_model.return_value = torch.tensor(0.8)
        mock_load.return_value = mock_model

        from jarvis.audio.vad import VoiceActivityDetector
        vad = VoiceActivityDetector(threshold=0.5)

        chunk = np.zeros(512, dtype=np.float32)
        assert vad.is_speech(chunk) is True

    @patch("jarvis.audio.vad.load_silero_vad")
    @patch("jarvis.audio.vad.VADIterator")
    def test_is_speech_false(self, mock_vad_iter, mock_load):
        import torch
        mock_model = MagicMock()
        mock_model.return_value = torch.tensor(0.2)
        mock_load.return_value = mock_model

        from jarvis.audio.vad import VoiceActivityDetector
        vad = VoiceActivityDetector(threshold=0.5)

        chunk = np.zeros(512, dtype=np.float32)
        assert vad.is_speech(chunk) is False

    @patch("jarvis.audio.vad.load_silero_vad")
    @patch("jarvis.audio.vad.VADIterator")
    def test_stereo_converted_to_mono(self, mock_vad_iter, mock_load):
        import torch
        mock_model = MagicMock()
        mock_model.return_value = torch.tensor(0.8)
        mock_load.return_value = mock_model

        from jarvis.audio.vad import VoiceActivityDetector
        vad = VoiceActivityDetector()

        stereo = np.zeros((512, 2), dtype=np.float32)
        # Should not raise — stereo is averaged to mono
        assert vad.is_speech(stereo) is True

    @patch("jarvis.audio.vad.load_silero_vad")
    @patch("jarvis.audio.vad.VADIterator")
    def test_reset(self, mock_vad_iter, mock_load):
        mock_model = MagicMock()
        mock_load.return_value = mock_model
        mock_iter = MagicMock()
        mock_vad_iter.return_value = mock_iter

        from jarvis.audio.vad import VoiceActivityDetector
        vad = VoiceActivityDetector()
        vad.reset()

        mock_iter.reset_states.assert_called_once()
        mock_model.reset_states.assert_called_once()

    @patch("jarvis.audio.vad.load_silero_vad")
    @patch("jarvis.audio.vad.VADIterator")
    def test_detect_boundaries(self, mock_vad_iter, mock_load):
        mock_model = MagicMock()
        mock_load.return_value = mock_model
        mock_iter = MagicMock()
        mock_iter.return_value = {"start": 1024}
        mock_vad_iter.return_value = mock_iter

        from jarvis.audio.vad import VoiceActivityDetector
        vad = VoiceActivityDetector()

        chunk = np.zeros(512, dtype=np.float32)
        result = vad.detect_boundaries(chunk)
        assert result == {"start": 1024}
