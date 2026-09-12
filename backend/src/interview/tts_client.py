"""
backend/src/interview/tts_client.py

Text-to-speech for the mock interviewer's voice -- isolated in its own
module, same provider-isolation rationale workers/llm/pipeline/client.py
states for the roast LLM call (the TTS provider may change independently
of the interview LLM's).

Confirmed against the real API this session: GEMINI_TTS_MODEL
("gemini-3.1-flash-tts-preview" by default) returns raw, HEADERLESS PCM
audio (mime_type "audio/l16; rate=24000; channels=1") -- 16-bit linear,
24kHz, mono. That's not something a browser <audio> element or
MediaRecorder-adjacent playback code can play directly, so this module
wraps it in a minimal WAV header before returning. Every caller gets a
real, playable (audio_bytes, content_type) pair -- the raw-PCM detail
never leaks past this module.
"""

import io
import wave
from typing import Tuple

from google import genai

from ..config import GEMINI_API_KEY, GEMINI_TTS_MODEL

# Matches the real mime_type Gemini's TTS model returns -- confirmed via a
# live call this session, not assumed from docs.
_PCM_SAMPLE_RATE_HZ = 24000
_PCM_SAMPLE_WIDTH_BYTES = 2  # 16-bit
_PCM_CHANNELS = 1

_async_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _async_client
    if _async_client is None:
        _async_client = genai.Client(api_key=GEMINI_API_KEY)
    return _async_client


def _wrap_pcm_as_wav(pcm_bytes: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(_PCM_CHANNELS)
        wav_file.setsampwidth(_PCM_SAMPLE_WIDTH_BYTES)
        wav_file.setframerate(_PCM_SAMPLE_RATE_HZ)
        wav_file.writeframes(pcm_bytes)
    return buffer.getvalue()


async def synthesize_speech(text: str, *, voice_name: str = "Kore") -> Tuple[bytes, str]:
    """
    Returns (wav_bytes, "audio/wav") -- always a real, playable WAV file,
    never the raw PCM the API actually returns.

    Raises:
        google.genai.errors.ServerError / ClientError.
        ValueError -- no inline audio data in the response (the model
                      silently fell back to a text-only reply -- confirmed
                      this session that this is exactly what happens if the
                      wrong, non-TTS-capable model is configured).
    """
    client = _get_client()
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
        raise ValueError(
            f"Gemini TTS response had no inline audio data (model={GEMINI_TTS_MODEL!r}, "
            f"text fallback={getattr(part, 'text', None)!r})"
        )
    return _wrap_pcm_as_wav(inline.data), "audio/wav"
