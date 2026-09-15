"""
scripts/interview_smoke_test/browser_check.py

Drives the REAL production frontend code (live-session.ts, the real
AudioWorklet mic pipeline, the real useLiveInterview hook) in a headless
Chromium, with a virtual microphone fed from a WAV file -- to answer one
specific question the Python-side investigation could not settle:

    Does audio streamed from a genuinely different client (the browser's
    own JS SDK, the code path already proven working in real spoken
    interviews) get transcribed, where a hand-rolled Python asyncio
    client (see run.py, and the diagnostics that led here) consistently
    got zero input_transcription -- across TTS audio, real recorded
    voice, raw API key, ephemeral tokens, forced VAD, and the SDK's own
    documented `media=` parameter (which turned out to be server-side
    DEPRECATED, not silently ignored -- confirmed via a real validation
    error, which is itself evidence the server was actively parsing
    those messages all along).

This does NOT replace run.py. It exists to answer one yes/no question so
that question stops being a mystery. If the browser succeeds here, the
Python audio path is a genuine, narrow SDK gap and run.py's audio
segments need a different implementation (or should drive a browser too).
If the browser ALSO gets nothing, the problem is upstream of both --
something about this project's specific token/config, not either client.

NEEDS:
  - the backend running locally (uvicorn app:app --reload)
  - the frontend dev server running locally (npm run dev, port 3000)
  - Chromium via `python -m playwright install chromium` (already done
    if this repo's venv has run it once)

Chrome's fake-microphone flags need a real WAV file, so the same real
recorded phrase used in the Python diagnostics is re-wrapped with a WAV
header here rather than re-decoded -- see wav_utils.py.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auth  # noqa: E402
import fixtures  # noqa: E402
from wav_utils import write_wav  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

BASE_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3000"
REAL_VOICE_PCM = Path(__file__).resolve().parent / ".cache" / "real_voice" / "phrase0.pcm16"
WAV_PATH = Path(__file__).resolve().parent / ".cache" / "real_voice" / "phrase0.wav"


async def _setup():
    id_token, uid = auth.mint_id_token()
    custom_token, _ = auth.mint_custom_token()
    db_user_id = await fixtures.get_or_create_db_user_id(uid, auth.TEST_ACCOUNT_EMAIL)
    resume_session_id = await fixtures.seed_resume_session(db_user_id)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/interview/start",
            json={"resume_session_id": resume_session_id, "job_description": fixtures.JOB_DESCRIPTION},
            headers={"Authorization": f"Bearer {id_token}"},
        )
        resp.raise_for_status()
        start = resp.json()
    return id_token, custom_token, start


def main() -> int:
    if not REAL_VOICE_PCM.exists():
        print(f"[!] {REAL_VOICE_PCM} not found -- run prep_real_voice.py first (see chat history).")
        return 1

    write_wav(WAV_PATH, REAL_VOICE_PCM.read_bytes(), sample_rate=16000)
    print(f"[setup] wrote {WAV_PATH} for Chrome's fake mic")

    id_token, custom_token, start = asyncio.run(_setup())
    interview_id = start["interview_id"]
    print(f"[setup] interview_id={interview_id}")

    console_lines: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=[
                "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-audio-capture={WAV_PATH}",
                "--use-fake-ui-for-media-stream",  # auto-accept the mic permission prompt
            ]
        )
        context = browser.new_context(permissions=["microphone"])
        page = context.new_page()
        page.on("console", lambda msg: console_lines.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda exc: console_lines.append(f"[pageerror] {exc}"))

        # Runs before ANY page script, so it's there when the room page's
        # own effect reads it -- matches interview-handoff.ts's exact key.
        page.add_init_script(
            f"window.sessionStorage.setItem({json.dumps('interview-start:' + interview_id)}, "
            f"{json.dumps(json.dumps(start))});"
        )

        print("[browser] navigating to the real interview room...")
        page.goto(f"{FRONTEND_URL}/interview/{interview_id}")

        print("[browser] signing in via the dev-only test hook...")
        page.wait_for_function("() => !!window.__TEST_AUTH__", timeout=15000)
        page.evaluate(
            "(token) => window.__TEST_AUTH__.signInWithCustomToken(token)", custom_token
        )
        page.wait_for_timeout(1500)  # let onAuthStateChanged settle

        print("[browser] clicking 'Join the interview'...")
        page.get_by_text("Join the interview").click(timeout=15000)

        print("[browser] connected -- letting the real mic pipeline run for 25s...")
        page.wait_for_timeout(25000)

        print("\n--- console lines captured ---")
        for line in console_lines[-40:]:
            print(" ", line)

        context.close()
        browser.close()

    print("\n[check] polling the backend for any candidate transcript...")
    time.sleep(1)
    resp = httpx.get(
        f"{BASE_URL}/api/v1/interview/{interview_id}",
        headers={"Authorization": f"Bearer {id_token}"},
        timeout=15,
    )
    data = resp.json()
    transcript = data.get("transcript", [])
    candidate_lines = [t for t in transcript if t["speaker"] == "candidate"]

    print(f"\nfull transcript ({len(transcript)} fragments):")
    for t in transcript:
        print(f"  {t['speaker']:<12} {t['text']}")

    # Never leave this stranded.
    httpx.post(
        f"{BASE_URL}/api/v1/interview/{interview_id}/complete",
        json={},
        headers={"Authorization": f"Bearer {id_token}"},
        timeout=30,
    )

    print("\n" + "=" * 70)
    if candidate_lines:
        print(f"RESULT: the REAL BROWSER got {len(candidate_lines)} candidate transcript "
              f"fragment(s). The audio pipeline works from the browser.")
    else:
        print("RESULT: even the real browser produced ZERO candidate transcript. "
              "This points upstream of both clients -- the token/config, not either SDK.")
    print("=" * 70)
    return 0 if candidate_lines else 1


if __name__ == "__main__":
    raise SystemExit(main())
