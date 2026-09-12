"""
Tests for backend/src/interview/tts_client.py's WAV normalization and its
Gemini-primary / OpenAI-fallback selection logic.

No real Gemini or OpenAI calls here -- both providers' real call shapes
were verified live during this feature's own development (real audio came
back from both), so what's worth guarding in the checked-in suite is the
*decision* logic around them: when the fallback fires, when it's skipped,
and which error survives when both fail. Real network calls stay in
manual/throwaway verification, matching the rest of this package.

Note on monkeypatching: tts_client does `from ..config import OPENAI_API_KEY`,
so the name lives in the tts_client module namespace. Tests must patch
`tts_client.OPENAI_API_KEY`, not `config.OPENAI_API_KEY` -- patching the
latter would have no effect on the already-bound name.

Async tests use asyncio.run() per test rather than @pytest.mark.asyncio:
pytest-asyncio is not a dependency of this project (only anyio is), so
that marker would silently SKIP these tests rather than run them. This
matches the asyncio.run()-per-test pattern the rest of the suite uses.
"""

import asyncio
import struct
import wave
import io

import pytest

from . import tts_client


def _make_streaming_wav(pcm_bytes: bytes) -> bytes:
    """
    A WAV with the 0xFFFFFFFF 'unknown length' placeholders OpenAI's
    streaming speech endpoint really returns (confirmed by inspecting live
    response bytes), rather than true sizes.
    """
    header = bytearray()
    header += b"RIFF"
    header += struct.pack("<I", 0xFFFFFFFF)
    header += b"WAVEfmt "
    header += struct.pack("<I", 16)
    header += struct.pack("<HHIIHH", 1, 1, 24000, 24000 * 2, 2, 16)
    header += b"data"
    header += struct.pack("<I", 0xFFFFFFFF)
    return bytes(header) + pcm_bytes


class TestWavNormalization:
    def test_wraps_raw_pcm_into_parseable_wav(self):
        pcm = b"\x00\x01" * 24000  # 1 second of 16-bit mono @24kHz
        wav_bytes = tts_client._wrap_pcm_as_wav(pcm)

        with wave.open(io.BytesIO(wav_bytes), "rb") as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getframerate() == 24000
            assert w.getnframes() == 24000

    def test_fixes_streaming_placeholder_sizes(self):
        pcm = b"\x00\x01" * 12000
        broken = _make_streaming_wav(pcm)

        # Proof the placeholder really does break a strict parser: Python's
        # own wave module reads 0xFFFFFFFF as a ~4.29GB frame count.
        with wave.open(io.BytesIO(broken), "rb") as w:
            assert w.getnframes() > 10**9

        fixed = tts_client._fix_streaming_wav_header(broken)
        with wave.open(io.BytesIO(fixed), "rb") as w:
            assert w.getnframes() == 12000

    def test_is_a_no_op_on_an_already_clean_wav(self):
        clean = tts_client._wrap_pcm_as_wav(b"\x00\x01" * 100)
        assert tts_client._fix_streaming_wav_header(clean) == clean

    def test_tolerates_bytes_with_no_data_chunk(self):
        # Never raise on a malformed response -- the caller's error handling
        # should decide what to do, not a header patcher.
        assert tts_client._fix_streaming_wav_header(b"not a wav at all") == b"not a wav at all"


class TestProviderSelection:
    def test_uses_gemini_when_it_succeeds(self, monkeypatch):
        calls = []

        async def fake_gemini(text, voice_name):
            calls.append("gemini")
            return b"GEMINI_AUDIO", "audio/wav"

        async def fake_openai(text):
            calls.append("openai")
            return b"OPENAI_AUDIO", "audio/wav"

        monkeypatch.setattr(tts_client, "_synthesize_gemini", fake_gemini)
        monkeypatch.setattr(tts_client, "_synthesize_openai", fake_openai)
        monkeypatch.setattr(tts_client, "OPENAI_API_KEY", "sk-test")

        audio, content_type = asyncio.run(tts_client.synthesize_speech("hello"))

        assert audio == b"GEMINI_AUDIO"
        assert content_type == "audio/wav"
        assert calls == ["gemini"], "OpenAI must not be called when Gemini works"

    def test_falls_back_to_openai_when_gemini_fails(self, monkeypatch):
        async def fake_gemini(text, voice_name):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

        async def fake_openai(text):
            return b"OPENAI_AUDIO", "audio/wav"

        monkeypatch.setattr(tts_client, "_synthesize_gemini", fake_gemini)
        monkeypatch.setattr(tts_client, "_synthesize_openai", fake_openai)
        monkeypatch.setattr(tts_client, "OPENAI_API_KEY", "sk-test")

        audio, content_type = asyncio.run(tts_client.synthesize_speech("hello"))

        assert audio == b"OPENAI_AUDIO"
        assert content_type == "audio/wav"

    def test_skips_fallback_entirely_when_no_openai_key(self, monkeypatch):
        """Unset key must not silently change behaviour -- the real Gemini
        error has to propagate, not get masked by a fallback attempt."""
        openai_called = []

        async def fake_gemini(text, voice_name):
            raise RuntimeError("gemini exploded")

        async def fake_openai(text):
            openai_called.append(True)
            return b"OPENAI_AUDIO", "audio/wav"

        monkeypatch.setattr(tts_client, "_synthesize_gemini", fake_gemini)
        monkeypatch.setattr(tts_client, "_synthesize_openai", fake_openai)
        monkeypatch.setattr(tts_client, "OPENAI_API_KEY", None)

        with pytest.raises(RuntimeError, match="gemini exploded"):
            asyncio.run(tts_client.synthesize_speech("hello"))
        assert openai_called == []

    def test_raises_the_gemini_error_when_both_fail(self, monkeypatch):
        """Gemini is the primary provider, so its failure is the one worth
        debugging -- the fallback also failing is a secondary symptom."""

        async def fake_gemini(text, voice_name):
            raise RuntimeError("the real root cause")

        async def fake_openai(text):
            raise RuntimeError("fallback also down")

        monkeypatch.setattr(tts_client, "_synthesize_gemini", fake_gemini)
        monkeypatch.setattr(tts_client, "_synthesize_openai", fake_openai)
        monkeypatch.setattr(tts_client, "OPENAI_API_KEY", "sk-test")

        with pytest.raises(RuntimeError, match="the real root cause"):
            asyncio.run(tts_client.synthesize_speech("hello"))

    def test_falls_back_when_gemini_returns_text_instead_of_audio(self, monkeypatch):
        """The silent-failure mode confirmed live: a non-TTS-capable model
        returns text with no inline audio rather than erroring. _synthesize_gemini
        turns that into a ValueError, which must also trigger the fallback."""

        async def fake_openai(text):
            return b"OPENAI_AUDIO", "audio/wav"

        async def fake_gemini(text, voice_name):
            raise ValueError("Gemini TTS response had no inline audio data")

        monkeypatch.setattr(tts_client, "_synthesize_gemini", fake_gemini)
        monkeypatch.setattr(tts_client, "_synthesize_openai", fake_openai)
        monkeypatch.setattr(tts_client, "OPENAI_API_KEY", "sk-test")

        audio, _ = asyncio.run(tts_client.synthesize_speech("hello"))
        assert audio == b"OPENAI_AUDIO"
