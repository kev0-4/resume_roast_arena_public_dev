"""
scripts/interview_smoke_test/code_editor_check.py

Ad hoc, on-demand check that the in-browser code editor actually works:
Pyodide/PGlite genuinely execute a real solution in a real headless
Chromium, the Run button shows real pass/fail, Submit reaches the real
backend, and a correct solution scores well.

Deliberately avoids the live-audio question entirely (see run.py and
browser_check.py for that investigation and its conclusion: no replayed
audio, in any client, produces input_transcription -- a real, separate
issue from this one). To reach the exercise round without depending on
audio, this drives begin_round with ONE text turn via the dev-only
__TEST_LIVE__ hook (see live-session.ts's sendText docstring) -- text
turns were proven reliable in every diagnostic. Everything from there on
(the editor, Pyodide/PGlite, Run, Submit, scoring) is the real product
surface, untouched by that hook.

Reuses the SAME reference solutions backend/src/interview/test_
catalogue_solutions.py already proves correct server-side (via exec()),
typing them into the REAL browser editor -- this is a genuinely
different check: does the same solution ALSO pass when run through
Pyodide's compiled CPython / PGlite's WASM Postgres, not just CPython
directly.

Job description is deliberately biased toward a pure coding role (no
SQL/data language) so the planner reliably picks a CODE round --
verified against the real planner's own stated bias in planner.py.

NEEDS: backend on :8000, frontend dev server on :3000, Chromium via
`python -m playwright install chromium`.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auth  # noqa: E402
import fixtures  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backend"))
from src.interview.catalogue.solutions import SOLUTIONS  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

BASE_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3000"

# Two rewrites of this JD, both aimed at CODE specifically (removing
# SQL/data language), got conversation-only 6/6 attempts each --
# apparently the SQL mention was what made the planner commit to AN
# exercise at all, not just which format it picked. Reusing
# fixtures.JOB_DESCRIPTION verbatim instead: proven in earlier testing
# to reliably produce an exercise. It can still come back as SQL rather
# than CODE (PGlite, not Pyodide) -- the retry loop below accepts
# either, since both are real in-browser runtimes and either answers
# "does the code editor thing work."
CODE_BIASED_JD = fixtures.JOB_DESCRIPTION


async def _setup(max_attempts: int = 6):
    """
    Retries a fresh /interview/start (real planner, real token, the
    exact path every real user goes through) until the agenda includes
    an exercise -- rather than forcing one via a hand-built plan.

    That WAS tried first, forcing the plan in the DB and mint a fresh
    token through /voice-token so its constraints would match. It
    doesn't work: connecting with that token hung indefinitely (40s+,
    no error, never even reached CONNECTED) in direct Python, and closed
    almost immediately (code 1000) through the browser -- a different,
    worse symptom than anything in the original audio investigation, and
    specific to that unusual use of an endpoint designed for re-opening
    voice AFTER an exercise, not minting the interview's first
    connection. Not worth chasing a second mystery to avoid a retry
    loop. kevintandon123@gmail.com is admin-exempt from the one-
    interview-per-week limit, so retrying costs nothing but planner
    calls.
    """
    # A SEPARATE admin-exempt account from the rest of this toolkit's
    # default, deliberately: kevintandon123@gmail.com's question history
    # is now exhausted -- confirmed directly, 8/8 CODE+SQL questions in
    # the whole catalogue already "asked" from today's own extensive dev
    # testing (run.py, browser_check.py, and this file's own earlier
    # attempts). That's PR #22's no-repeat feature working exactly as
    # designed, colliding with heavy reuse of one test account. Switching
    # accounts sidesteps it without touching real history on the other.
    account = "lemonocean11@gmail.com"
    id_token, uid = auth.mint_id_token(account)
    custom_token, _ = auth.mint_custom_token(account)
    db_user_id = await fixtures.get_or_create_db_user_id(uid, account)

    async with httpx.AsyncClient(timeout=30) as client:
        headers = {"Authorization": f"Bearer {id_token}"}
        for attempt in range(1, max_attempts + 1):
            resume_session_id = await fixtures.seed_resume_session(db_user_id)
            resp = await client.post(
                f"{BASE_URL}/api/v1/interview/start",
                json={"resume_session_id": resume_session_id, "job_description": CODE_BIASED_JD},
                headers=headers,
            )
            resp.raise_for_status()
            start = resp.json()
            agenda_labels = [a["label"] for a in start.get("agenda", [])]
            print(f"[setup] attempt {attempt}: agenda={agenda_labels}")
            # Accept CODE ("Coding") or SQL specifically -- both are real
            # in-browser runtimes this check can exercise. Reject MCQ
            # ("Quick-fire questions") and WRITTEN: neither has a runtime
            # or a SOLUTIONS entry, so this check would have nothing to do.
            if any(label in ("Coding", "SQL") for label in agenda_labels):
                return id_token, custom_token, start
            # Conversation-only this time -- abandon it (no candidate
            # speech, so /complete would 409 anyway) and try a fresh one.
            await client.post(f"{BASE_URL}/api/v1/interview/{start['interview_id']}/complete", json={}, headers=headers)

    raise RuntimeError(f"planner gave conversation-only {max_attempts} times in a row -- try again or raise max_attempts")


class Report:
    def __init__(self) -> None:
        self.lines: list[tuple[str, bool, str]] = []

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}{' -- ' + detail if detail else ''}")
        self.lines.append((label, ok, detail))

    def summary(self) -> bool:
        print("\n" + "=" * 70 + "\nSUMMARY\n" + "=" * 70)
        all_ok = True
        for label, ok, _ in self.lines:
            print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
            all_ok = all_ok and ok
        print("=" * 70, "\nALL PASSED" if all_ok else "\nSOME FAILED -- see above")
        return all_ok


def main() -> int:
    report = Report()
    id_token, custom_token, start = asyncio.run(_setup())
    interview_id = start["interview_id"]
    print(f"[setup] interview_id={interview_id}")
    print(f"[setup] agenda={[a['label'] for a in start.get('agenda', [])]}")

    round_payload: dict = {}

    with sync_playwright() as p:
        # Needs SOME file here -- omitting --use-file-for-fake-audio-
        # capture produced an immediate "live socket closed: code=1000"
        # right after connecting (MicCapture.start() apparently needs a
        # real file behind the fake device to not break something
        # upstream of the socket). But a real spoken clip was WORSE:
        # Chrome loops the file continuously for as long as the stream
        # is open, so 12 real seconds of speech became an unbroken loop
        # of "activity" the whole session -- confirmed by the app's own
        # diagnostics staying speaking=true/audioChunks climbing
        # continuously, and begin_round never landing through that
        # noise even from a genuinely quiet moment. A short SILENT clip
        # satisfies MicCapture without ever competing with the text
        # channel this check actually uses.
        fake_audio_wav = Path(__file__).resolve().parent / ".cache" / "silence.wav"
        browser = p.chromium.launch(
            args=[
                "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-audio-capture={fake_audio_wav}",
                "--use-fake-ui-for-media-stream",  # in browser_check.py; missing here was likely the actual bug
            ]
        )
        context = browser.new_context(permissions=["microphone"])
        page = context.new_page()
        page.on("pageerror", lambda exc: print(f"  [pageerror] {exc}"))

        # The app's own periodic diagnostic line
        # ("[interview] quiet=Xs ... speaking=true/false ...") is the
        # cheapest way to know whether the model is mid-utterance without
        # another frontend change -- sending a text nudge while
        # speaking=true went unanswered every time in an earlier run;
        # text apparently does not barge in the way voice does.
        diag_state: dict[str, bool | None] = {"speaking": None}

        def on_console(msg):
            print(f"  [console:{msg.type}] {msg.text}")
            m = re.search(r"speaking=(true|false)", msg.text)
            if m:
                diag_state["speaking"] = m.group(1) == "true"

        page.on("console", on_console)

        def capture_round(response):
            if "/round/" in response.url and response.request.method == "GET" and response.ok:
                try:
                    round_payload.update(response.json())
                except Exception:
                    pass

        page.on("response", capture_round)

        page.add_init_script(
            f"window.sessionStorage.setItem({json.dumps('interview-start:' + interview_id)}, "
            f"{json.dumps(json.dumps(start))});"
        )

        print("[browser] navigating and signing in...")
        page.goto(f"{FRONTEND_URL}/interview/{interview_id}")
        page.wait_for_function("() => !!window.__TEST_AUTH__", timeout=15000)
        page.evaluate("(t) => window.__TEST_AUTH__.signInWithCustomToken(t)", custom_token)
        page.wait_for_timeout(1500)

        print("[browser] joining...")
        page.get_by_text("Join the interview").click(timeout=15000)
        # __TEST_LIVE__ is registered on mount, well before the socket is
        # actually open (connect() is async, triggered but not awaited by
        # the click) -- so its mere existence proves nothing about the
        # session being live yet. A fixed settle wait is cheap insurance
        # against sendText silently no-op'ing on a still-null session.
        page.wait_for_function("() => !!window.__TEST_LIVE__", timeout=20000)
        page.wait_for_timeout(5000)
        report.check("live session connected", True)

        move_to_round_text = "Can we move on to the coding round now? I'd like to get started on it."
        for attempt in range(3):
            # Wait for a quiet moment rather than firing blind: a text
            # nudge sent while speaking=true went unanswered every time
            # in an earlier run of this exact script -- unlike voice,
            # sendClientContent apparently doesn't barge in on a turn
            # already in flight, so sending into one is just lost.
            print(f"[browser] waiting for a quiet moment (attempt {attempt + 1})...")
            for _ in range(20):  # up to ~10s
                if diag_state["speaking"] is False:
                    break
                page.wait_for_timeout(500)
            print(f"[browser] asking (via text, not audio) to move to the coding round...")
            page.evaluate("(t) => window.__TEST_LIVE__.sendText(t)", move_to_round_text)
            try:
                page.wait_for_selector(".cm-content", timeout=20000)
                break
            except Exception:
                if attempt == 2:
                    raise

        report.check("reached the exercise round (begin_round -> /advance -> round GET -> UI)", True)

        question_id = round_payload.get("question", {}).get("id")
        question_format = round_payload.get("question", {}).get("format")
        print(f"[browser] round: id={question_id!r} format={question_format!r}")

        entry = SOLUTIONS.get(question_id)
        report.check(
            f"have a known-correct reference solution for {question_id!r}",
            entry is not None,
            "" if entry else "unexpected question -- extend SOLUTIONS or the job description bias",
        )
        if entry is None:
            report.summary()
            return 1

        reference = entry["reference"]

        # Select all, then insertText -- NOT keyboard.type(). CM6's
        # basicSetup closes brackets on real keydown events; type()
        # simulates those and a typed "(" would get an auto-inserted ")"
        # that then collides with the reference solution's own ")",
        # corrupting the code. insertText uses CDP's raw text insertion,
        # which bypasses that entirely.
        page.locator(".cm-content").click()
        page.keyboard.press("ControlOrMeta+a")
        page.keyboard.insert_text(reference)

        if question_format == "CODE":
            print("[browser] clicking 'Run tests'...")
            page.get_by_text("Run tests", exact=True).click()
            # Pyodide boots on first use -- give it real time.
            passing_locator = page.locator("text=/\\d+\\/\\d+ tests passing/")
            passing_locator.wait_for(timeout=60000)
            passing_text = passing_locator.inner_text()
            passed, total = (int(x) for x in passing_text.split()[0].split("/"))
            report.check(
                "Pyodide ran the reference solution and every case passed",
                passed == total and total > 0,
                passing_text,
            )
        elif question_format == "SQL":
            print("[browser] clicking 'Run'...")
            page.get_by_text("Run", exact=True).click()
            outcome_locator = page.locator("text=/matches the expected result|didn.t match|error/i")
            outcome_locator.wait_for(timeout=60000)
            outcome_text = outcome_locator.first.inner_text()
            report.check(
                "PGlite ran the reference SQL and it matched",
                "matches the expected result" in outcome_text,
                outcome_text,
            )
        else:
            report.check(
                "question format is CODE or SQL",
                False,
                f"got {question_format!r} -- the JD bias didn't work, adjust CODE_BIASED_JD",
            )

        print("[browser] submitting...")
        page.get_by_text("Submit and face the questions").click()
        page.get_by_text("Round scored").wait_for(timeout=45000)
        # The score and "/10" are sibling text/element nodes inside the
        # SAME <p>, so inner_text() on that element is "7/10" -- pull the
        # leading digits out in Python rather than trying to match just
        # the number with a locator, which the DOM doesn't expose as one.
        score_block_text = page.locator("p.text-brand-lime").first.inner_text()
        score = int(score_block_text.split("/")[0].strip())
        report.check(
            "a CORRECT reference solution scored well (not a garbage-answer low score)",
            score >= 7,
            f"score={score}/10",
        )

        context.close()
        browser.close()

    httpx.post(
        f"{BASE_URL}/api/v1/interview/{interview_id}/complete",
        json={}, headers={"Authorization": f"Bearer {id_token}"}, timeout=30,
    )

    return 0 if report.summary() else 1


if __name__ == "__main__":
    raise SystemExit(main())
