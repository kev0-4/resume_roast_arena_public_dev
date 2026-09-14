"""
backend/src/routes/interview.py

Routes for the real-time AI mock-interview feature.

The defining property of this module is what is NOT here: the conversation.
The candidate's browser holds its own WebSocket to Gemini's Live API and
talks to it directly. This server only:

  1. decides whether someone is allowed to interview at all, and mints a
     short-lived single-use credential for one session (/interview/start),
  2. accepts the transcript the browser streams up while it happens
     (/interview/{id}/transcript),
  3. scores the finished conversation (/interview/{id}/complete).

Putting a relay in the audio path would add a round trip to every syllable.
The previous, turn-based build did exactly that -- record, upload, LLM,
TTS, play -- and took ~92 seconds to produce its first question.

Two routers, matching this codebase's existing prefix split:
- interview_router: prefix /api/v1 (matches injest_router's own routes)
- interview_leaderboard_router: no prefix (matches leaderboard_router,
  which serves plain /leaderboard, not /api/v1/leaderboard)

Privacy invariant (same as workers/llm/pipeline/client.py's roast call):
only the ANONYMIZED resume artifact is ever sent to Gemini, read fresh
from anonymized/{resume_session_id}/anonymized.json -- never the raw
upload. That applies to the Live session's system instruction too: it is
built here, server-side, and handed to the browser already assembled.
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_db_sqlalchemy
from ..db.users import Users
from ..db.sessions import JobStatusEnum
from ..db.interview_sessions import InterviewSessions, InterviewStatusEnum
from ..dependencies.auth import get_current_user
from ..dependencies.rate_limit import check_interview_start_rate_limit
from ..services.session_service import get_session as get_resume_session
from ..services.blob import read_blob, upload_interview_transcript
from ..config import GEMINI_LIVE_MODEL
from ..interview import service as interview_service
from ..interview import prompt_builder as interview_prompts
from ..interview import llm_client as interview_llm
from ..interview import validator as interview_validator
from ..interview import planner as interview_planner
from ..interview import catalogue
from ..interview.tools import INTERVIEW_TOOLS
from ..utils.telemetry import emit_event
from ..schemas.interview_schemas import (
    InterviewStartResponse,
    InterviewTranscriptAck,
    InterviewCompleteRequest,
    InterviewRoundResponse,
    InterviewRoundResult,
    InterviewScoreResult,
    InterviewDetailResponse,
    TranscriptEntry,
    InterviewLeaderboardEntry,
    InterviewLeaderboardResponse,
    MyInterviewLeaderboardPosition,
    InterviewEligibilityResponse,
)

interview_router = APIRouter()
interview_leaderboard_router = APIRouter()

# Bounds on one /transcript POST. The browser flushes every ~5 seconds, so
# a legitimate batch is a handful of chunks; these exist to stop a client
# from posting a novel into blob storage, not to constrain normal use.
_MAX_CHUNKS_PER_POST = 500
_MAX_CHUNK_TEXT = 5000
_MAX_TOTAL_CHUNKS = 5000


async def _load_resume_context(resume_session_id) -> tuple[dict, dict]:
    """Reads anonymized.json + roast.json for a resume session concurrently."""
    anonymized_path = f"anonymized/{resume_session_id}/anonymized.json"
    roast_path = f"roast/{resume_session_id}/roast.json"

    async def _read_json(blob_path: str) -> dict:
        raw = await asyncio.to_thread(read_blob, blob_path)
        return json.loads(raw)

    anonymized, roast = await asyncio.gather(_read_json(anonymized_path), _read_json(roast_path))
    return anonymized, roast


@asynccontextmanager
async def _gemini_call_guard():
    """
    Wraps a single Gemini call, not a whole route body -- these routes
    interleave real Gemini calls with real DB/blob writes, and a broad
    try/except would mislabel an actual bug in that surrounding code as
    "the interviewer is temporarily unavailable."

    Turns any google.genai APIError (quota, rate limit, transient server
    error) into a clean 503 so the user gets a real "try again" message
    rather than a stack trace.
    """
    try:
        yield
    except genai_errors.APIError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The interviewer is temporarily unavailable. Please try again in a moment.",
        ) from e


async def _get_owned_interview(interview_id: str, curr_user: Users, db: AsyncSession) -> InterviewSessions:
    """
    404 (not 403) on a non-owner -- avoid leaking whether an interview_id
    exists at all to someone who isn't its owner, same posture as
    /r/{slug}'s 404/410 split for expired-vs-missing.
    """
    try:
        interview_uuid = uuid.UUID(str(interview_id))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")

    interview = await interview_service.get_interview_session(db, interview_uuid)
    if interview is None or interview.user_id != curr_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return interview


async def _read_transcript(interview: InterviewSessions) -> list[dict]:
    if not interview.transcript_blob_path:
        return []
    raw = await asyncio.to_thread(read_blob, interview.transcript_blob_path)
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Start: mint a credential, not a conversation
# ---------------------------------------------------------------------------


class InterviewStartRequest(BaseModel):
    resume_session_id: str
    job_description: str = Field(..., min_length=20, max_length=6000)


@interview_router.post("/interview/start", response_model=InterviewStartResponse, status_code=status.HTTP_201_CREATED)
async def start_interview(
    body: InterviewStartRequest,
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
    _rate_limit=Depends(check_interview_start_rate_limit),
):
    """
    Authorizes an interview and hands back everything the browser needs to
    run it itself: a single-use Live API token, the model to use, and the
    fully-built system instruction.

    The system instruction is assembled HERE rather than in the browser
    precisely because it contains the anonymized resume and the roast --
    the client is told how to conduct the interview, but never gets to
    choose what the interviewer knows.
    """
    resume_session = await get_resume_session(session_id=body.resume_session_id, db=db)
    if resume_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume session not found")
    if resume_session.user_id != curr_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your resume")
    if resume_session.status != JobStatusEnum.DONE.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Resume roast isn't finished yet")

    anonymized, roast = await _load_resume_context(resume_session.id)
    system_context = interview_prompts.build_interview_system_context(anonymized, roast, body.job_description)
    system_instruction = interview_prompts.build_live_system_instruction(system_context)
    resume_text = interview_prompts.build_resume_display_text(anonymized)

    # Plan the round structure before anything expensive happens. A failure
    # here degrades to the conversation-only interview that shipped in #19
    # rather than blocking a candidate who has already waited for a roast.
    try:
        raw_plan, _usage, _model = await interview_llm.generate_plan(
            interview_planner.build_planning_prompt(resume_text, body.job_description)
        )
        plan = interview_planner.validate_plan(raw_plan)
    except Exception as e:  # noqa: BLE001 -- any planner failure is non-fatal by design
        emit_event(
            "interview.plan_failed",
            {"reason": str(e)[:200], "status": "WARNING", "route": "POST /v1/interview/start"},
        )
        plan = interview_planner.conversation_only_plan()

    # The id is generated here rather than by the DB so the voice -- which
    # is derived from it -- is known before the token is minted, while the
    # mint still happens before any row is written. A mint failure then
    # leaves nothing to clean up and the user gets a 503 rather than an
    # orphaned interview they can never connect to.
    interview_id = uuid.uuid4()

    async with _gemini_call_guard():
        token, expires_at = await interview_llm.create_ephemeral_token(
            system_instruction, interview_llm.voice_for_interview(interview_id)
        )

    interview = await interview_service.create_interview_session(
        db=db,
        user_id=curr_user.id,
        resume_session_id=resume_session.id,
        job_description=body.job_description,
        interview_id=interview_id,
    )
    interview = await interview_service.set_plan(db, interview, plan.model_dump())

    return InterviewStartResponse(
        interview_id=str(interview.id),
        token=token,
        model=GEMINI_LIVE_MODEL,
        system_instruction=system_instruction,
        tools=INTERVIEW_TOOLS,
        resume_text=resume_text,
        agenda=interview_planner.plan_summary(plan),
        expires_at=expires_at,
    )


# ---------------------------------------------------------------------------
# Transcript: the browser streams up what was said, as it is said
# ---------------------------------------------------------------------------


class TranscriptChunkIn(BaseModel):
    seq: int = Field(..., ge=0)
    speaker: Literal["interviewer", "candidate"]
    text: str = Field(..., max_length=_MAX_CHUNK_TEXT)
    is_final: bool = True
    at: str


class TranscriptPostRequest(BaseModel):
    chunks: List[TranscriptChunkIn] = Field(..., max_length=_MAX_CHUNKS_PER_POST)
    # Client-side telemetry for the live session, piggybacked on the flush
    # that already happens every 5s. It rides here rather than on a route of
    # its own because browser console output does NOT reach the dev server
    # log reliably -- verified: the SDK's own warnings appear, ours never
    # did -- so this is the only channel that gets session telemetry to
    # somewhere readable. Free-form on purpose; it is only ever logged.
    client_diag: dict | None = None


@interview_router.post("/interview/{interview_id}/transcript", response_model=InterviewTranscriptAck)
async def post_interview_transcript(
    interview_id: str,
    body: TranscriptPostRequest,
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
):
    """
    Appends streamed transcript chunks to the server's copy.

    TRUST BOUNDARY -- stated plainly, because it is not obvious from the
    code: this is not tamper-proof. The conversation happens between the
    browser and Gemini, so the transcript necessarily originates
    client-side. The server can prove a session was *authorized* (it minted
    the token) but not what was actually said, and a determined user could
    stream invented text and farm a leaderboard score.

    This is not a new weakness. The resume leaderboard already scores a
    document the user fully controls, so the app's trust model is unchanged.
    Scoring stays server-side, so a score can never be submitted directly --
    only transcript text. The genuinely server-authoritative fix is a
    backend WebSocket relay, at the cost of the latency this design exists
    to win.

    Streaming during the call rather than posting at the end means a closed
    tab loses at most the last few seconds instead of the whole interview.
    """
    interview = await _get_owned_interview(interview_id, curr_user, db)

    if body.client_diag is not None:
        print(f"[interview-diag] {interview.id} {json.dumps(body.client_diag, default=str)[:600]}", flush=True)

    if interview.status != InterviewStatusEnum.IN_PROGRESS.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Interview is {interview.status}, not in progress",
        )

    existing = await _read_transcript(interview)

    # Read-modify-write on a single blob. Safe enough here because one
    # browser tab posts these sequentially, and a lost update costs a few
    # seconds of transcript rather than corrupting anything. Worth
    # revisiting if the client ever flushes concurrently.
    incoming = [chunk.model_dump() for chunk in body.chunks]
    merged = interview_service.merge_transcript_chunks(existing, incoming)

    if len(merged) > _MAX_TOTAL_CHUNKS:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Transcript is too long for a single interview",
        )

    blob_path = await asyncio.to_thread(upload_interview_transcript, str(interview.id), merged)
    if interview.transcript_blob_path != blob_path:
        await interview_service.set_transcript_blob_path(db, interview, blob_path)

    return InterviewTranscriptAck(accepted=len(merged) - len(existing), total_chunks=len(merged))


# ---------------------------------------------------------------------------
# Rounds: the exercise the interviewer switched the screen to
# ---------------------------------------------------------------------------


def _plan_of(interview: InterviewSessions) -> interview_planner.InterviewPlan:
    """
    An interview with no stored plan predates rounds entirely. Treating it
    as conversation-only means every interview created before this feature
    still works, with no backfill.
    """
    if not interview.plan:
        return interview_planner.conversation_only_plan("interview predates round planning")
    try:
        return interview_planner.InterviewPlan(**interview.plan)
    except Exception:
        return interview_planner.conversation_only_plan("stored plan unreadable")


@interview_router.get("/interview/{interview_id}/round/{index}", response_model=InterviewRoundResponse)
async def get_interview_round(
    interview_id: str,
    index: int,
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
):
    """
    The question for one round, as the candidate may see it.

    The answer key and the grading rubric never appear in this response --
    `public_question` strips them. The client is untrusted, and an MCQ
    whose answers ship to the browser is not a test.
    """
    interview = await _get_owned_interview(interview_id, curr_user, db)
    plan = _plan_of(interview)

    # Server holds the pointer, so a client cannot jump to a round it likes
    # the look of or replay one it already answered.
    if index != (interview.current_round or 0):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You're on round {interview.current_round}, not {index}.",
        )

    planned = interview_planner.find_round(plan, index)
    if planned is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such round")
    if planned.kind != "EXERCISE":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That round is a conversation, not an exercise")

    entry = catalogue.get_question(planned.question_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That question is no longer available")

    return InterviewRoundResponse(
        index=index,
        minutes=planned.minutes,
        question=catalogue.public_question(entry),
    )


@interview_router.post("/interview/{interview_id}/advance", response_model=InterviewRoundResult)
async def advance_interview_round(
    interview_id: str,
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
):
    """
    Leaves a conversation round and moves to whatever the plan has next.

    Driven by the interviewer's own `begin_round` tool call: the plan fixes
    WHAT the rounds are, the interviewer decides WHEN to move. Conversation
    rounds have nothing to grade, so this only moves the pointer.
    """
    interview = await _get_owned_interview(interview_id, curr_user, db)
    if interview.status != InterviewStatusEnum.IN_PROGRESS.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Interview is {interview.status}")

    plan = _plan_of(interview)
    index = interview.current_round or 0
    planned = interview_planner.find_round(plan, index)

    if planned is None or planned.kind != "CONVERSATION":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a conversation round can be advanced -- an exercise is finished by submitting it.",
        )

    next_planned = interview_planner.find_round(plan, index + 1)
    if next_planned is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="There is no next round -- this interview ends here.",
        )

    interview = await interview_service.record_round_result(
        db, interview, {"index": index, "kind": "CONVERSATION"}
    )

    return InterviewRoundResult(
        index=index,
        score=0,
        strengths=[],
        problems=[],
        next_round_kind=next_planned.kind,
        next_round_index=index + 1,
    )


class RoundSubmitRequest(BaseModel):
    # CODE / SQL / WRITTEN answer text, or MCQ selected option indexes.
    answer: str = Field(default="", max_length=20000)
    mcq_answers: List[int] = Field(default_factory=list, max_length=50)
    language: Optional[str] = Field(default=None, max_length=20)
    seconds_taken: int = Field(default=0, ge=0, le=7200)
    # Recorded, never blocked. A read-only editor cannot stop someone
    # pasting from another tab, so this becomes a signal for the debrief
    # rather than a gate the product pretends to enforce.
    pasted: bool = False


@interview_router.post("/interview/{interview_id}/round/{index}/submit", response_model=InterviewRoundResult)
async def submit_interview_round(
    interview_id: str,
    index: int,
    body: RoundSubmitRequest,
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
):
    """
    Grades one exercise and advances to the next round.

    MCQ is scored here, deterministically, against the key that never left
    this process. Everything else goes to one cheap text call -- no
    sandbox, no execution. The review's real product is `interviewer_notes`,
    which arms the debrief.
    """
    interview = await _get_owned_interview(interview_id, curr_user, db)

    if interview.status != InterviewStatusEnum.IN_PROGRESS.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Interview is {interview.status}")
    if index != (interview.current_round or 0):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Round {index} is not the current round ({interview.current_round}).",
        )

    plan = _plan_of(interview)
    planned = interview_planner.find_round(plan, index)
    if planned is None or planned.kind != "EXERCISE":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such exercise round")

    entry = catalogue.get_question(planned.question_id)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="That question is no longer available")

    if entry["format"] == "MCQ":
        review = interview_service.score_mcq(entry, body.mcq_answers)
        submission = json.dumps(body.mcq_answers)
    else:
        async with _gemini_call_guard():
            raw_review, _usage, _model = await interview_llm.review_submission(
                interview_prompts.build_review_prompt(entry, body.answer, body.language)
            )
        review = raw_review.model_dump()
        submission = body.answer

    interview = await interview_service.record_round_result(
        db,
        interview,
        {
            "index": index,
            "question_id": entry["id"],
            "format": entry["format"],
            "language": body.language,
            "submission": submission,
            "seconds_taken": body.seconds_taken,
            "pasted": body.pasted,
            "review": review,
        },
    )

    next_planned = interview_planner.find_round(plan, index + 1)
    return InterviewRoundResult(
        index=index,
        # Deliberately partial: the candidate sees how they did, not the
        # notes the interviewer is about to use on them.
        score=review["score"],
        strengths=review.get("strengths", []),
        problems=review.get("problems", []),
        mcq_detail=review.get("detail"),
        next_round_kind=next_planned.kind if next_planned else None,
        next_round_index=index + 1 if next_planned else None,
    )


@interview_router.post("/interview/{interview_id}/voice-token", response_model=InterviewStartResponse)
async def mint_voice_token(
    interview_id: str,
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
):
    """
    Re-opens voice after an exercise round.

    Not a rate-limited route: it does not start a new interview, it resumes
    one already paid for. Capping it would strand a candidate mid-session.

    Why a whole new token rather than resuming the old socket: ephemeral
    tokens silently ignore session resumption handles. Verified twice --
    with a fresh uses=1 token and with a single uses=2 token used for both
    connections, the model reconnected with no memory and replayed its
    opening question. The same test passes on a raw API key. So the
    conversation is carried by re-seeding the instruction from the
    transcript we already store, which also costs no measurable latency:
    a 6,237-char instruction reached first audio in 2.09s against a 2.0s
    baseline.
    """
    interview = await _get_owned_interview(interview_id, curr_user, db)
    if interview.status != InterviewStatusEnum.IN_PROGRESS.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Interview is {interview.status}")

    anonymized, roast = await _load_resume_context(interview.resume_session_id)
    system_context = interview_prompts.build_interview_system_context(
        anonymized, roast, interview.job_description
    )
    instruction = interview_prompts.build_live_system_instruction(system_context)

    chunks = await _read_transcript(interview)
    utterances = interview_service.merge_into_utterances(chunks)

    last = (interview.round_results or [])[-1] if interview.round_results else None
    if last:
        entry = catalogue.get_question(last["question_id"])
        if entry:
            instruction += interview_prompts.build_debrief_addendum(
                utterances, entry, last.get("submission", ""), last.get("review")
            )

    # Same voice as every other segment of this interview -- it is derived
    # from the id, so the debrief cannot come back as a different person.
    async with _gemini_call_guard():
        token, expires_at = await interview_llm.create_ephemeral_token(
            instruction, interview_llm.voice_for_interview(interview.id)
        )

    return InterviewStartResponse(
        interview_id=str(interview.id),
        token=token,
        model=GEMINI_LIVE_MODEL,
        system_instruction=instruction,
        tools=INTERVIEW_TOOLS,
        resume_text=interview_prompts.build_resume_display_text(anonymized),
        agenda=interview_planner.plan_summary(_plan_of(interview)),
        expires_at=expires_at,
    )


# ---------------------------------------------------------------------------
# Complete: score the finished conversation
# ---------------------------------------------------------------------------


@interview_router.post("/interview/{interview_id}/complete", response_model=InterviewScoreResult)
async def complete_interview(
    interview_id: str,
    body: InterviewCompleteRequest = InterviewCompleteRequest(),
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
):
    """
    Ends the interview and scores it.

    Idempotent by design: the browser calls this from several paths that
    can race (the end button, the 10-minute expiry, the socket closing, and
    now the interviewer's own end_interview tool call), so a completed
    interview returns its existing score rather than paying for a second
    scoring call.

    An interview the INTERVIEWER ended still gets scored normally, and
    still reaches the leaderboard. Wasting the interviewer's time produces
    a genuinely bad score rather than a free escape from one.
    """
    interview = await _get_owned_interview(interview_id, curr_user, db)

    if interview.status == InterviewStatusEnum.COMPLETED.value:
        return InterviewScoreResult(
            interview_id=str(interview.id),
            status=interview.status,
            score=interview.score,
            strengths=interview.strengths or [],
            weaknesses=interview.weaknesses or [],
            next_steps=interview.next_steps or [],
        )

    if interview.status != InterviewStatusEnum.IN_PROGRESS.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Interview is {interview.status} and can't be scored",
        )

    chunks = await _read_transcript(interview)
    utterances = interview_service.merge_into_utterances(chunks)

    # Nothing the candidate said means nothing to grade. Ending here avoids
    # spending a Gemini call on silence and keeps an empty session off the
    # leaderboard entirely.
    if not any(u["speaker"] == "candidate" for u in utterances):
        await interview_service.mark_interview_abandoned(db, interview)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You didn't say anything, so there's nothing to score. Start another interview when you're ready.",
        )

    anonymized, roast = await _load_resume_context(interview.resume_session_id)
    system_context = interview_prompts.build_interview_system_context(anonymized, roast, interview.job_description)
    scoring_prompt = interview_prompts.build_scoring_prompt(
        system_context,
        utterances,
        skipped_questions=body.skipped_questions,
        ended_early=body.ended_early.model_dump() if body.ended_early else None,
    )

    async with _gemini_call_guard():
        raw_score, _usage, _model = await interview_llm.generate_score(scoring_prompt)

    validated = interview_validator.validate_score_response(raw_score)
    interview = await interview_service.finalize_interview(db, interview, validated)

    return InterviewScoreResult(
        interview_id=str(interview.id),
        status=interview.status,
        score=interview.score,
        strengths=interview.strengths or [],
        weaknesses=interview.weaknesses or [],
        next_steps=interview.next_steps or [],
    )


# ---------------------------------------------------------------------------
# Reads -- unchanged in behaviour from the turn-based build
# ---------------------------------------------------------------------------


@interview_router.get("/interview/eligibility", response_model=InterviewEligibilityResponse)
async def check_interview_eligibility(
    slug: str = Query(...),
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
):
    """
    Backs the "start an interview" CTA on the public /r/[slug] result page.
    That page is intentionally public with zero ownership awareness, so
    the eligibility check is a SEPARATE authenticated route rather than
    adding user_id to the public /r/{slug}/data response -- a link
    designed to be shared shouldn't start leaking who owns it.
    """
    from ..services.session_service import get_session_by_slug

    session = await get_session_by_slug(db=db, slug=slug)
    if session is None or session.user_id != curr_user.id or session.status != JobStatusEnum.DONE.value:
        return InterviewEligibilityResponse(eligible=False)
    return InterviewEligibilityResponse(eligible=True, resume_session_id=str(session.id))


@interview_router.get("/interview/{interview_id}", response_model=InterviewDetailResponse)
async def get_interview(
    interview_id: str,
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
):
    """
    Not public like /r/{slug} -- a transcript is real personal data, so
    this is auth+ownership gated, not a shareable link.
    """
    interview = await _get_owned_interview(interview_id, curr_user, db)

    chunks = await _read_transcript(interview)
    transcript = [
        TranscriptEntry(seq=i, speaker=u["speaker"], text=u["text"], at=u.get("at"))
        for i, u in enumerate(interview_service.merge_into_utterances(chunks))
    ]

    resume_session = await get_resume_session(session_id=interview.resume_session_id, db=db)

    return InterviewDetailResponse(
        interview_id=str(interview.id),
        status=interview.status,
        resume_session_id=str(interview.resume_session_id),
        roast_slug=resume_session.slug if resume_session else None,
        job_description=interview.job_description,
        transcript=transcript,
        score=interview.score,
        strengths=interview.strengths,
        weaknesses=interview.weaknesses,
        next_steps=interview.next_steps,
        started_at=interview.started_at,
        completed_at=interview.completed_at,
    )


@interview_leaderboard_router.get("/interview-leaderboard", response_model=InterviewLeaderboardResponse)
async def get_interview_leaderboard_route(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db_sqlalchemy),
):
    rows, total = await interview_service.get_interview_leaderboard(db=db, limit=limit, offset=offset)
    entries = [
        InterviewLeaderboardEntry(
            rank=offset + i + 1,
            display_name=row["display_name"] or "Anonymous Applicant",
            score=row["score"],
            completed_at=row["completed_at"],
        )
        for i, row in enumerate(rows)
    ]
    return InterviewLeaderboardResponse(total=total, limit=limit, offset=offset, entries=entries)


@interview_leaderboard_router.get("/interview-leaderboard/me", response_model=MyInterviewLeaderboardPosition | None)
async def get_my_interview_leaderboard_position_route(
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
):
    position = await interview_service.get_user_interview_leaderboard_position(db=db, user_id=curr_user.id)
    if position is None:
        return None
    return MyInterviewLeaderboardPosition(
        rank=position["rank"], total=position["total"], score=position["score"], completed_at=position["completed_at"]
    )
