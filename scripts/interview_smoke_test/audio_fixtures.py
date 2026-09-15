"""
scripts/interview_smoke_test/audio_fixtures.py

Synthesizes the handful of fixed spoken phrases this smoke test needs, so
the actual interview run never needs a microphone -- sendRealtimeInput
takes raw PCM chunks, and nothing about the Live API requires them to
come from a live mic.

Uses gemini-3.1-flash-tts-preview (verified against the real API: returns
audio/l16;rate=24000;channels=1, i.e. raw 16-bit signed PCM, no header)
rather than a third-party TTS package -- this sandbox has no system audio
tooling (no espeak, no ffmpeg) and no passwordless sudo to install one,
whereas google-genai is already a project dependency and the cost of a
few short phrases is a fraction of a cent.

Downsampled 24kHz -> 16kHz with a plain numpy linear interpolation --
adequate for Gemini's own transcription to understand, which is all this
needs; audio quality for a human listener is not the point.

Cached to disk (gitignored) so this is a ONE-TIME cost: every later run
of the smoke test reads cached PCM bytes and makes zero TTS calls.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = Path(__file__).resolve().parent / ".cache"

TTS_MODEL = "gemini-3.1-flash-tts-preview"
TTS_VOICE = "Kore"
SOURCE_RATE = 24000
TARGET_RATE = 16000

PHRASES = {
    "short_answer": (
        "I built a caching layer in front of our checkout service using Redis, "
        "with a read-through pattern, and it cut our p99 latency by about half."
    ),
    "move_to_round": (
        "Actually, can we move on to the coding round now? I would like to get "
        "started on it."
    ),
    "end_interview": (
        "I have to go now -- please end the interview and give me my score. Thank you."
    ),
}


def _lowpass_fir(cutoff_hz: float, sample_rate: int, num_taps: int = 127) -> np.ndarray:
    """Windowed-sinc FIR lowpass. numpy-only -- this sandbox has no scipy."""
    n = np.arange(num_taps) - (num_taps - 1) / 2
    normalized_cutoff = cutoff_hz / (sample_rate / 2)
    sinc = np.sinc(normalized_cutoff * n) * normalized_cutoff
    window = np.hamming(num_taps)
    kernel = sinc * window
    return (kernel / kernel.sum()).astype(np.float32)


def _downsample_24k_to_16k(pcm_24k: bytes) -> bytes:
    """
    24kHz -> 16kHz, with an anti-aliasing lowpass BEFORE resampling.

    Verified this filter is necessary, not decorative: a 10kHz tone
    (real content in speech sibilants, well within 24kHz's own Nyquist)
    survives a NAIVE linear-interp resample as ~6kHz garbage, because
    16kHz's Nyquist is only 8kHz and nothing was removing the energy
    above it first. That aliasing was corrupting every synthesized
    fixture enough to trip the API's VAD (there was still real energy)
    while defeating its transcription (the formants were garbled) -- a
    live smoke-test run showed exactly this: a real begin_round
    interruption fired, but no input_transcription ever arrived for
    what was "said". A single-tone or RMS check does not catch this;
    only a broadband signal does, because a pure low tone has nothing
    to alias.
    """
    samples = np.frombuffer(pcm_24k, dtype="<i2").astype(np.float32)
    n_in = len(samples)
    if n_in <= 1:
        return b""

    # Cut at 7.5kHz, safely under 16kHz's 8kHz Nyquist.
    filtered = np.convolve(samples, _lowpass_fir(7500, SOURCE_RATE), mode="same")

    n_out = int(round(n_in * TARGET_RATE / SOURCE_RATE))
    if n_out <= 1:
        return b""
    x_in = np.linspace(0.0, 1.0, num=n_in, endpoint=True)
    x_out = np.linspace(0.0, 1.0, num=n_out, endpoint=True)
    resampled = np.interp(x_out, x_in, filtered)
    return np.clip(resampled, -32768, 32767).astype("<i2").tobytes()


def _synthesize(text: str) -> bytes:
    from google import genai
    from google.genai import types

    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / "workers" / ".env")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    resp = client.models.generate_content(
        model=TTS_MODEL,
        contents=text,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE)
                )
            ),
        ),
    )
    part = resp.candidates[0].content.parts[0]
    inline = part.inline_data
    if not inline or not inline.data:
        raise RuntimeError(f"TTS returned no audio for: {text!r}")
    assert "l16" in (inline.mime_type or "") and "24000" in (inline.mime_type or ""), (
        f"unexpected TTS mime type {inline.mime_type!r} -- resample assumptions no longer hold"
    )
    return _downsample_24k_to_16k(inline.data)


def get_phrase_pcm(key: str) -> bytes:
    """16kHz mono 16-bit signed PCM, raw bytes -- ready for sendRealtimeInput."""
    text = PHRASES[key]
    cache_path = CACHE_DIR / f"{key}.{hashlib.sha1(text.encode()).hexdigest()[:8]}.pcm16"
    if cache_path.exists():
        return cache_path.read_bytes()

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pcm = _synthesize(text)
    cache_path.write_bytes(pcm)
    print(f"[audio] synthesized and cached {key} ({len(pcm)} bytes)")
    return pcm


def ensure_all_cached() -> dict[str, bytes]:
    return {key: get_phrase_pcm(key) for key in PHRASES}


if __name__ == "__main__":
    fixtures = ensure_all_cached()
    for key, pcm in fixtures.items():
        seconds = len(pcm) / 2 / TARGET_RATE
        print(f"[audio] {key}: {len(pcm)} bytes, ~{seconds:.1f}s at {TARGET_RATE}Hz mono")
