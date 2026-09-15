"""
scripts/interview_smoke_test/wav_utils.py

Chrome's --use-file-for-fake-audio-capture flag (the standard way to feed
a headless/automated Chrome a synthetic microphone) wants a real WAV
file, not raw PCM -- unlike sendRealtimeInput, which wants headerless
PCM. Small enough to use stdlib `wave` directly rather than pull in a
dependency for it.
"""

from __future__ import annotations

import wave
from pathlib import Path


def write_wav(path: Path, pcm16_mono: bytes, sample_rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)  # 16-bit
        f.setframerate(sample_rate)
        f.writeframes(pcm16_mono)
