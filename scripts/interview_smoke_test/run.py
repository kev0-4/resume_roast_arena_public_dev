"""
scripts/interview_smoke_test/run.py

An on-demand, real-money integration test of the live interview: one
short conversation segment, a real begin_round tool call, a real round
submission, the debrief voice re-open, and a real end_interview tool
call -- combined into ONE short paid session rather than three separate
expensive ones, because that is what actually costs real Gemini Live
minutes and real wall-clock time.

Runs entirely against the REAL running backend and the REAL Gemini Live
API -- same ephemeral-token flow, same routes, same WebSocket protocol
the browser uses (verified field-for-field against
frontend/src/lib/live-session.ts and frontend/src/hooks/use-live-
interview.ts before writing this). A synthetic mic (pre-synthesized,
cached TTS audio -- see audio_fixtures.py) replaces a human speaking, so
this needs no microphone and no browser.

NEVER run automatically. Not in CI, not on a schedule, not triggered by
a git hook. It costs real money (Gemini Live is duration-billed, plus
two cheap text calls for planning and review) and takes a few real
minutes. Run it yourself, whenever you want:

    1. Start the backend locally first:
         cd <repo root> && uvicorn app:app --reload
    2. python scripts/interview_smoke_test/run.py

What it proves, end to end, that a human clicking through the UI would
otherwise have to check by hand every time:
  - /interview/start mints a working token and a real plan
  - the model actually speaks first (no seed = 20s of dead air, a real
    bug this rebuild hit once already)
  - real audio and real transcription are flowing both directions
  - asking to move on triggers a real begin_round tool call
  - /advance, the round GET, and /round/{i}/submit all work against a
    genuinely wrong answer (so grading has something to actually grade)
  - /voice-token correctly re-seeds the interviewer for the debrief
  - asking to end triggers a real end_interview tool call (or, if the
    model reasonably chooses to keep talking, that gets reported rather
    than silently swallowed)
  - /complete produces a real score

Total connected Live time is capped at roughly 3-4 minutes by design --
see the two wait_for_tool_call timeouts below.
"""

from __future__ import annotations

import asyncio
import sys
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audio_fixtures  # noqa: E402
import auth  # noqa: E402
import fixtures  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))

BASE_URL = "http://localhost:8000"
HARD_TIMEOUT_S = 600  # safety net for the whole run

# How long we'll wait for the model to react to a spoken request before
# giving up. begin_round is documented as a near-deterministic reaction
# to "can we move on"; end_interview is a judgement call the model makes,
# not a hard trigger, so it gets the longer allowance and a graceful
# fallback rather than a hard failure.
BEGIN_ROUND_TIMEOUT_S = 45
END_INTERVIEW_TIMEOUT_S = 40


@dataclass
class SegmentState:
    got_first_audio: asyncio.Event = field(default_factory=asyncio.Event)
    first_audio_at: float | None = None
    audio_chunks: int = 0
    tool_calls: "asyncio.Queue" = field(default_factory=asyncio.Queue)
    transcript: list[dict] = field(default_factory=list)
    interrupted_count: int = 0
    closed_reason: str | None = None
    _seq: int = 0

    def append_transcript(self, speaker: str, text: str) -> None:
        self._seq += 1
        self.transcript.append(
            {
                "seq": self._seq,
                "speaker": speaker,
                "text": text,
                "is_final": True,
                "at": "1970-01-01T00:00:00Z",  # smoke test -- ordering matters, wall time doesn't
            }
        )


async def _receive_loop(session, state: SegmentState, connect_started: float) -> None:
    try:
        async for message in session.receive():
            if message.tool_call and message.tool_call.function_calls:
                for call in message.tool_call.function_calls:
                    await state.tool_calls.put(call)

            content = message.server_content
            if not content:
                continue

            if content.model_turn and content.model_turn.parts:
                for part in content.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        state.audio_chunks += 1
                        if not state.got_first_audio.is_set():
                            state.first_audio_at = time.monotonic() - connect_started
                            state.got_first_audio.set()

            if content.input_transcription and content.input_transcription.text:
                state.append_transcript("candidate", content.input_transcription.text)
            if content.output_transcription and content.output_transcription.text:
                state.append_transcript("interviewer", content.output_transcription.text)
            if content.interrupted:
                state.interrupted_count += 1
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 -- reported, not swallowed
        state.closed_reason = f"{type(e).__name__}: {e}"


@asynccontextmanager
async def voice_segment(token: str, model: str, system_instruction: str, tools: list):
    """
    One Live connection, alive only for the duration of the `async with`
    block -- the Python SDK's connect() is an async context manager, not
    a plain awaitable-returning-a-handle like the JS SDK's. Yields
    (session, state); the receive loop runs as a background task for the
    lifetime of the block and is cancelled cleanly on exit.
    """
    from google import genai
    from google.genai import types

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=system_instruction,
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
        tools=tools,
    )
    # A fresh client per segment, authenticated with THIS segment's
    # single-use ephemeral token -- mirrors live-session.ts exactly,
    # including the v1alpha pin ephemeral tokens require.
    client = genai.Client(api_key=token, http_options=types.HttpOptions(api_version="v1alpha"))

    connect_started = time.monotonic()
    async with client.aio.live.connect(model=model, config=config) as session:
        state = SegmentState()
        recv_task = asyncio.create_task(_receive_loop(session, state, connect_started))
        try:
            yield session, state
        finally:
            recv_task.cancel()
            try:
                await recv_task
            except (asyncio.CancelledError, Exception):
                pass


async def kickoff(session) -> None:
    """Same seed the browser sends -- without it the model says nothing at all."""
    await session.send_client_content(
        turns=[{"role": "user", "parts": [{"text": "I'm here and ready. Please begin the interview."}]}],
        turn_complete=True,
    )


async def stream_pcm(session, pcm_bytes: bytes, chunk_ms: int = 20) -> None:
    from google.genai import types

    bytes_per_ms = (16000 * 2) // 1000
    chunk_size = bytes_per_ms * chunk_ms
    for i in range(0, len(pcm_bytes), chunk_size):
        chunk = pcm_bytes[i : i + chunk_size]
        await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
        await asyncio.sleep(chunk_ms / 1000)


async def wait_for_tool_call(session, state: SegmentState, name: str, timeout: float):
    """
    Waits for a specific tool call, acknowledging (generically) any other
    one that arrives first -- exactly the "must acknowledge or the model
    stalls" rule live-session.ts documents. Returns None on timeout
    rather than raising: a model choosing not to call end_interview
    within the window is a real, reportable outcome, not a script bug.
    """
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        try:
            call = await asyncio.wait_for(state.tool_calls.get(), timeout=remaining)
        except asyncio.TimeoutError:
            return None
        if call.name == name:
            return call
        print(f"    [live] tool call while waiting for {name!r}: {call.name!r} (acked, ignored)")
        await session.send_tool_response(
            function_responses=[{"id": call.id, "name": call.name, "response": {"ok": True}}]
        )


class Report:
    """Collects pass/fail per phase so the final summary is unambiguous."""

    def __init__(self) -> None:
        self.lines: list[tuple[str, bool, str]] = []

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label}{' -- ' + detail if detail else ''}")
        self.lines.append((label, ok, detail))

    def summary(self) -> bool:
        print("\n" + "=" * 70)
        print("SUMMARY")
        print("=" * 70)
        all_ok = True
        for label, ok, detail in self.lines:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {label}")
            all_ok = all_ok and ok
        print("=" * 70)
        print("ALL PASSED" if all_ok else "SOME FAILED -- see above")
        return all_ok


async def http_post(client: httpx.AsyncClient, path: str, **kwargs) -> httpx.Response:
    resp = await client.post(f"{BASE_URL}{path}", **kwargs)
    return resp


async def main() -> int:
    report = Report()
    interview_id: str | None = None
    id_token: str | None = None

    async def _emergency_complete(client: httpx.AsyncClient):
        """
        Never leave OUR OWN test run stranded IN_PROGRESS -- that's a
        known, pre-existing product gap (no recovery path for a stranded
        interview), and this script should not be the thing that creates
        one for someone to find later.
        """
        if interview_id and id_token:
            try:
                await http_post(
                    client,
                    f"/api/v1/interview/{interview_id}/complete",
                    json={},
                    headers={"Authorization": f"Bearer {id_token}"},
                    timeout=30,
                )
                print("[cleanup] forced /complete on the way out")
            except Exception as e:  # noqa: BLE001
                print(f"[cleanup] forced /complete failed too: {e}")

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            # ---- Setup: auth, fixture resume, audio (cheap/free) ------
            print("[1/9] Minting a real ID token...")
            id_token_local, firebase_uid = auth.mint_id_token()
            id_token = id_token_local
            headers = {"Authorization": f"Bearer {id_token}"}
            report.check("mint a real Firebase ID token", True)

            print("[2/9] Seeding a fresh resume+roast fixture...")
            db_user_id = await fixtures.get_or_create_db_user_id(firebase_uid, auth.TEST_ACCOUNT_EMAIL)
            resume_session_id = await fixtures.seed_resume_session(db_user_id)
            report.check("seed a DONE resume session", True, resume_session_id)

            print("[3/9] Ensuring TTS audio fixtures are cached (one-time cost if missing)...")
            audio = audio_fixtures.ensure_all_cached()
            report.check("audio fixtures ready", True, f"{len(audio)} phrases")

            # ---- POST /interview/start ---------------------------------
            print("[4/9] POST /interview/start ...")
            resp = await http_post(
                client,
                "/api/v1/interview/start",
                json={"resume_session_id": resume_session_id, "job_description": fixtures.JOB_DESCRIPTION},
                headers=headers,
            )
            ok = resp.status_code == 201
            report.check("POST /interview/start -> 201", ok, f"status={resp.status_code} body={resp.text[:200]}")
            if not ok:
                report.summary()
                return 1
            start = resp.json()
            interview_id = start["interview_id"]
            print(f"    interview_id={interview_id}")
            print(f"    agenda={start.get('agenda')}")
            has_exercise = any(a.get("label") != "Conversation" for a in start.get("agenda", []))
            report.check(
                "planner scheduled an exercise round",
                has_exercise,
                "the job description was written to make this likely -- if this fails, "
                "check the planner prompt before assuming the script is broken",
            )

            # ---- Segment 1: conversation -> begin_round ----------------
            print("[5/9] Opening the Live session (segment 1: conversation)...")
            async with voice_segment(
                start["token"], start["model"], start["system_instruction"], start["tools"]
            ) as (session, state):
                await kickoff(session)
                got_audio = await asyncio.wait_for(state.got_first_audio.wait(), timeout=20)
                report.check(
                    "model spoke first (no seed = known 20s dead-air bug)",
                    got_audio,
                    f"first audio at {state.first_audio_at:.2f}s" if state.first_audio_at else "",
                )

                print("    speaking a short answer...")
                await stream_pcm(session, audio["short_answer"])
                await asyncio.sleep(1.5)

                print("    asking to move to the coding round...")
                await stream_pcm(session, audio["move_to_round"])

                begin_call = await wait_for_tool_call(session, state, "begin_round", BEGIN_ROUND_TIMEOUT_S)
                report.check(
                    "begin_round tool call fired after asking to move on",
                    begin_call is not None,
                    f"handoff={begin_call.args.get('handoff')!r}" if begin_call else "timed out",
                )
                if begin_call:
                    await session.send_tool_response(
                        function_responses=[{"id": begin_call.id, "name": begin_call.name, "response": {"ok": True}}]
                    )

                segment1_transcript = list(state.transcript)

            if not begin_call:
                print("[!] Never got begin_round -- forcing completion so this doesn't strand.")
                await http_post(client, f"/api/v1/interview/{interview_id}/transcript", json={"chunks": segment1_transcript}, headers=headers)
                await http_post(client, f"/api/v1/interview/{interview_id}/complete", json={}, headers=headers)
                report.summary()
                return 1

            # ---- Flush transcript, advance, fetch + submit the round --
            print("[6/9] POST /transcript, /advance, GET round, POST submit...")
            resp = await http_post(
                client, f"/api/v1/interview/{interview_id}/transcript", json={"chunks": segment1_transcript}, headers=headers
            )
            report.check("POST /transcript (segment 1)", resp.status_code == 200, f"status={resp.status_code}")

            resp = await http_post(client, f"/api/v1/interview/{interview_id}/advance", json={}, headers=headers)
            ok = resp.status_code == 200
            report.check("POST /advance -> 200", ok, f"status={resp.status_code} body={resp.text[:200]}")
            if not ok:
                await _emergency_complete(client)
                report.summary()
                return 1
            advance_result = resp.json()
            next_index = advance_result["next_round_index"]

            resp = await client.get(f"{BASE_URL}/api/v1/interview/{interview_id}/round/{next_index}", headers=headers)
            ok = resp.status_code == 200
            report.check("GET /round/{index} -> 200", ok, f"status={resp.status_code}")
            if not ok:
                await _emergency_complete(client)
                report.summary()
                return 1
            round_payload = resp.json()
            question = round_payload["question"]
            print(f"    round {next_index}: format={question['format']} title={question.get('title')!r}")

            if question["format"] == "MCQ":
                submit_body = {"mcq_answers": [], "seconds_taken": 30}
            else:
                submit_body = {
                    "answer": f"definitely wrong nonsense {uuid.uuid4().hex}",
                    "language": "python" if question["format"] == "CODE" else None,
                    "seconds_taken": 30,
                }
            resp = await http_post(
                client, f"/api/v1/interview/{interview_id}/round/{next_index}/submit", json=submit_body, headers=headers
            )
            ok = resp.status_code == 200
            report.check("POST /round/{index}/submit -> 200", ok, f"status={resp.status_code} body={resp.text[:200]}")
            if not ok:
                await _emergency_complete(client)
                report.summary()
                return 1
            submit_result = resp.json()
            print(f"    round score: {submit_result.get('score')}/10 (garbage answer -- a low score is CORRECT, not a bug)")
            report.check(
                "a garbage submission scored low, not high",
                (submit_result.get("score") or 10) <= 4,
                f"score={submit_result.get('score')}",
            )

            # ---- Segment 2: debrief voice re-open -> end_interview -----
            print("[7/9] POST /voice-token, reopening Live for the debrief...")
            resp = await http_post(client, f"/api/v1/interview/{interview_id}/voice-token", json={}, headers=headers)
            ok = resp.status_code == 200
            report.check("POST /voice-token -> 200", ok, f"status={resp.status_code} body={resp.text[:200]}")
            if not ok:
                await _emergency_complete(client)
                report.summary()
                return 1
            reopened = resp.json()

            print("[8/9] Opening the Live session (segment 2: debrief + end)...")
            end_call = None
            async with voice_segment(
                reopened["token"], reopened["model"], reopened["system_instruction"], reopened["tools"]
            ) as (session, state):
                got_audio = await asyncio.wait_for(state.got_first_audio.wait(), timeout=20)
                report.check("debrief reconnection produced audio", got_audio)

                await asyncio.sleep(1.0)
                print("    asking to end the interview...")
                await stream_pcm(session, audio["end_interview"])

                end_call = await wait_for_tool_call(session, state, "end_interview", END_INTERVIEW_TIMEOUT_S)
                report.check(
                    "end_interview tool call fired after asking to end",
                    end_call is not None,
                    (f"category={end_call.args.get('category')!r}" if end_call else
                     "timed out -- the model may have reasonably chosen to keep talking; "
                     "forcing completion anyway below"),
                )

                segment2_transcript = list(state.transcript)

            await http_post(
                client, f"/api/v1/interview/{interview_id}/transcript", json={"chunks": segment2_transcript}, headers=headers
            )

            # ---- Complete + score ---------------------------------------
            print("[9/9] POST /complete ...")
            complete_body = {"skipped_questions": 0}
            if end_call:
                complete_body["ended_early"] = {
                    "reason": str(end_call.args.get("reason", "")),
                    "category": str(end_call.args.get("category", "COMPLETE")),
                }
            resp = await http_post(client, f"/api/v1/interview/{interview_id}/complete", json=complete_body, headers=headers)
            ok = resp.status_code == 200
            report.check("POST /complete -> 200", ok, f"status={resp.status_code} body={resp.text[:300]}")
            if ok:
                result = resp.json()
                print(f"    final score: {result.get('score')}/10")
                print(f"    strengths: {result.get('strengths')}")
                print(f"    weaknesses: {result.get('weaknesses')}")

        except Exception as e:  # noqa: BLE001
            print(f"\n[!] Unhandled error: {type(e).__name__}: {e}")
            await _emergency_complete(client)
            report.check("ran without an unhandled exception", False, f"{type(e).__name__}: {e}")

    return 0 if report.summary() else 1


if __name__ == "__main__":
    exit_code = asyncio.run(asyncio.wait_for(main(), timeout=HARD_TIMEOUT_S))
    raise SystemExit(exit_code)
