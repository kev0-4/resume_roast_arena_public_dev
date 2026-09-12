"""
backend/src/interview/tts_client.py

Text-to-speech for the mock interviewer's voice -- isolated in its own
module, same provider-isolation rationale workers/llm/pipeline/client.py
states for the roast LLM call (the TTS provider may change independently
of the interview LLM's).

Gemini is the primary voice; OpenAI is a fallback used ONLY when Gemini
fails. That isn't hedging -- it's answering a measured problem. Gemini's
TTS model free tier is capped at 10 requests/day (confirmed live, and it
behaves more like a short rolling window than a clean daily reset), while
a single full interview needs 8 TTS calls. So on the free tier the
interviewer reliably loses its voice partway through the *first*
interview of the day. Paid tier raises that ceiling, but a fallback also
covers transient 5xx/rate-limit blips for free, so it stays either way.

Both providers are wrapped to return the same (wav_bytes, "audio/wav")
contract, because their raw outputs differ in ways callers should never
have to care about:
  - Gemini returns raw, HEADERLESS PCM (mime_type "audio/l16; rate=24000;
    channels=1") -- 16-bit linear, 24kHz, mono. Not playable by a browser
    <audio> element as-is, so it gets a WAV header here.
  - OpenAI returns a real WAV, but a STREAMING one: both the RIFF and data
    chunk size fields are the 0xFFFFFFFF "unknown length" placeholder
    rather than the true byte count (confirmed by inspecting real response
    bytes). Lenient players cope; strict parsers -- including Python's own
    `wave` module -- read that as a ~4.29GB file. Patched here to the real
    sizes so every consumer gets a standards-clean file.
"""

import io
import struct
import wave
from typing import Tuple

import httpx
from google import genai

from ..config import (
    GEMINI_API_KEY,
    GEMINI_TTS_MODEL,
    OPENAI_API_KEY,
    OPENAI_TTS_MODEL,
    OPENAI_TTS_VOICE,
)

# Matches the real mime_type Gemini's TTS model returns -- confirmed via a
# live call, not assumed from docs.
_PCM_SAMPLE_RATE_HZ = 24000
_PCM_SAMPLE_WIDTH_BYTES = 2  # 16-bit
_PCM_CHANNELS = 1

_OPENAI_SPEECH_URL = "https://api.openai.com/v1/audio/speech"

# The interviewer's persona, expressed to a model that accepts natural-
# language delivery direction (OpenAI's TTS models do; Gemini's voice is
# selected by name instead). Keeps the fallback voice in the same register
# as the primary rather than switching to a neutral narrator mid-interview.
_OPENAI_VOICE_INSTRUCTIONS = (
    "Speak as a brutally honest, impatient technical interviewer -- skeptical, "
    "sharp, no warmth. Speak slightly faster than a normal conversational pace."
)

_gemini_client: genai.Client | None = None


def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return _gemini_client


def _wrap_pcm_as_wav(pcm_bytes: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(_PCM_CHANNELS)
        wav_file.setsampwidth(_PCM_SAMPLE_WIDTH_BYTES)
        wav_file.setframerate(_PCM_SAMPLE_RATE_HZ)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


def _fix_streaming_wav_header(wav_bytes: bytes) -> bytes:
    """
    Replace a streaming WAV's 0xFFFFFFFF placeholder size fields with the
    real byte counts. No-op for a WAV that already declares real sizes.
    """
    data = bytearray(wav_bytes)
    data_idx = data.find(b"data")
    if data_idx == -1 or len(data) < data_idx + 8:
        return wav_bytes
    pcm_bytes = len(data) - (data_idx + 8)
    struct.pack_into("<I", data, data_idx + 4, pcm_bytes)
    struct.pack_into("<I", data, 4, len(data) - 8)
    return bytes(data)


async def _synthesize_gemini(text: str, voice_name: str) -> Tuple[bytes, str]:
    client = _get_gemini_client()
    response = await client.aio.models.generate_content(
        model=GEMINI_TTS_MODEL,
        contents=text,
        config=genai.types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=genai.types.SpeechConfig(
                voice_config=genai.types.VoiceConfig(
                    prebuilt_voice_config=genai.types.PrebuiltVoiceConfig(voice_name=voice_name)
                )
            ),
        ),
    )
    part = response.candidates[0].content.parts[0]
    inline = getattr(part, "inline_data", None)
    if inline is None or not inline.data:
        # Confirmed live: a non-TTS-capable model (e.g. the flash-lite roast
        # model) doesn't error here -- it silently returns text instead.
        raise ValueError(
            f"Gemini TTS response had no inline audio data (model={GEMINI_TTS_MODEL!r}, "
            f"text fallback={getattr(part, 'text', None)!r})"
        )
    return _wrap_pcm_as_wav(inline.data), "audio/wav"


async def _synthesize_openai(text: str) -> Tuple[bytes, str]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            _OPENAI_SPEECH_URL,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={
                "model": OPENAI_TTS_MODEL,
                "input": text,
                "voice": OPENAI_TTS_VOICE,
                "response_format": "wav",
                "instructions": _OPENAI_VOICE_INSTRUCTIONS,
            },
        )
        response.raise_for_status()
        return _fix_streaming_wav_header(response.content), "audio/wav"


async def synthesize_speech(text: str, *, voice_name: str = "Kore") -> Tuple[bytes, str]:
    """
    Returns (wav_bytes, "audio/wav") -- always a real, playable WAV file,
    whichever provider produced it.

    Tries Gemini first, falls back to OpenAI on ANY Gemini failure (quota,
    rate limit, transient 5xx, or a model that silently returned text).
    The fallback is skipped entirely when OPENAI_API_KEY is unset, in which
    case the original Gemini error propagates unchanged.

    Raises:
        The Gemini error, when no fallback is configured or the fallback
        also fails. Callers (routes/interview.py's _gemini_call_guard) turn
        that into a clean 503 rather than a raw 500.
    """
    try:
        return await _synthesize_gemini(text, voice_name)
    except Exception as gemini_error:
        if not OPENAI_API_KEY:
            raise
        try:
            return await _synthesize_openai(text)
        except Exception:
            # Surface the *Gemini* error, not the fallback's -- Gemini is the
            # primary provider, so its failure is the one worth debugging.
            # The fallback failing too is a secondary symptom.
            raise gemini_error
