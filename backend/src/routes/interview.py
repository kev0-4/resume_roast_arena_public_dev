"""
backend/src/routes/interview.py

Thin routes for the AI mock-interview feature -- plain synchronous FastAPI
routes (not a Service-Bus-queued worker like the rest of the pipeline):
an interview is live back-and-forth, the user is waiting on each response,
so it has to be request/response, not fire-and-forget.

Two routers, matching this codebase's existing prefix split:
- interview_router: prefix /api/v1 (matches injest_router's own routes)
- interview_leaderboard_router: no prefix (matches leaderboard_router,
  which serves plain /leaderboard, not /api/v1/leaderboard)

Privacy invariant (same as workers/llm/pipeline/client.py's roast call):
only the ANONYMIZED resume artifact is ever sent to Gemini, read fresh
from anonymized/{resume_session_id}/anonymized.json -- never the raw
upload.

Each turn is genuinely stateless server-side: no in-memory chat session,
no persistent connection. Every call rebuilds its prompt from the
transcript blob + a fresh read of the anonymized resume + roast, matching
the turn-based (not real-time-streaming) architecture decision.
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File, Form, status
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_db_sqlalchemy
from ..db.users import Users
from ..db.sessions import JobStatusEnum
from ..db.interview_sessions import InterviewSessions, InterviewStatusEnum
from ..dependencies.auth import get_current_user
from ..dependencies.rate_limit import check_interview_start_rate_limit, check_interview_turn_rate_limit
from ..services.session_service import get_session as get_resume_session
from ..services.blob import (
    read_blob,
    upload_interview_transcript,
    upload_interview_audio,
)
from ..config import INTERVIEW_MAX_TURNS
from ..interview import service as interview_service
from ..interview import prompt_builder as interview_prompts
from ..interview import llm_client as interview_llm
from ..interview import tts_client
from ..interview import validator as interview_validator
from ..interview.audio_validation import validate_answer_audio
from ..schemas.interview_schemas import (
    InterviewStartResponse,
    InterviewTurnApiResponse,
    InterviewDetailResponse,
    TranscriptTurnEntry,
    InterviewLeaderboardEntry,
    InterviewLeaderboardResponse,
    MyInterviewLeaderboardPosition,
    InterviewEligibilityResponse,
)

interview_router = APIRouter()
interview_leaderboard_router = APIRouter()


def _audio_url(interview_id, turn: int, kind: str) -> str:
    return f"api/v1/interview/{interview_id}/audio/{turn}/{kind}"


async def _load_resume_context(resume_session_id) -> tuple[dict, dict]:
    """Reads anonymized.json + roast.json for a resume session concurrently."""
    anonymized_path = f"anonymized/{resume_session_id}/anonymized.json"
    roast_path = f"roast/{resume_session_id}/roast.json"

    async def _read_json(blob_path: str) -> dict:
        raw = await asyncio.to_thread(read_blob, blob_path)
        return json.loads(raw)

    anonymized, roast = await asyncio.gather(_read_json(anonymized_path), _read_json(roast_path))
    return anonymized, roast


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
    resume_session = await get_resume_session(session_id=body.resume_session_id, db=db)
    if resume_session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume session not found")
    if resume_session.user_id != curr_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your resume")
    if resume_session.status != JobStatusEnum.DONE.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Resume roast isn't finished yet")

    anonymized, roast = await _load_resume_context(resume_session.id)

    system_context = interview_prompts.build_interview_system_context(anonymized, roast, body.job_description)
    opening_prompt = interview_prompts.build_opening_prompt(system_context)

    async with _gemini_call_guard():
        opening_response, _usage, _model = await interview_llm.generate_opening_question(opening_prompt)
        question_text = interview_validator.validate_opening_question(opening_response)
        audio_bytes, content_type = await tts_client.synthesize_speech(question_text)

    interview = await interview_service.create_interview_session(
        db=db,
        user_id=curr_user.id,
        resume_session_id=resume_session.id,
        job_description=body.job_description,
        max_turns=INTERVIEW_MAX_TURNS,
    )

    question_audio_path = upload_interview_audio(str(interview.id), 0, "prompt", audio_bytes, content_type)
    transcript = [interview_service.new_transcript_entry(0, question_text, question_audio_path)]
    transcript_blob_path = upload_interview_transcript(str(interview.id), transcript)
    await interview_service.set_transcript_blob_path(db, interview, transcript_blob_path)

    return InterviewStartResponse(
        interview_id=str(interview.id),
        status=interview.status,
        turn_number=0,
        max_turns=interview.max_turns,
        question_text=question_text,
        question_audio_url=_audio_url(interview.id, 0, "prompt"),
    )


@asynccontextmanager
async def _gemini_call_guard():
    """
    Wraps a single Gemini or TTS call, not a whole route body -- these
    routes interleave real Gemini calls with real DB/blob writes, and a
    broad try/except would mislabel an actual bug in that surrounding
    code as "the interviewer is temporarily unavailable."

    Confirmed live during this feature's own end-to-end verification:
    Gemini's TTS model free tier caps at just 10 requests/day (far
    tighter than the interview LLM's own quota) -- exhausting it mid-
    interview previously surfaced as a raw, unhandled 500. This turns any
    google.genai APIError (quota, rate limit, transient server error)
    into a clean 503 instead, so a user mid-interview gets a real
    "try again" message, not a stack trace.

    This makes the immediate HTTP response graceful -- it does NOT by
    itself fix every state-consistency edge case. In particular: the
    end-of-interview scoring call (generate_score) runs AFTER
    advance_turn_count has already moved turn_count to max_turns, so a
    failure there still leaves the interview stuck IN_PROGRESS with no
    score and no way to submit another turn (turn_number will never match
    turn_count again). That gap is real and still open -- see this
    feature's own plan doc's "Stuck-IN_PROGRESS failure mode" risk. Every
    OTHER Gemini call in these routes does run before its turn's DB
    writes, so a caught failure anywhere else leaves the interview
    exactly where it was before the call -- safely retriable.
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


@interview_router.post("/interview/{interview_id}/turn", response_model=InterviewTurnApiResponse)
async def submit_interview_turn(
    interview_id: str,
    turn_number: int = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
    _rate_limit=Depends(check_interview_turn_rate_limit),
):
    interview = await _get_owned_interview(interview_id, curr_user, db)

    if interview.status != InterviewStatusEnum.IN_PROGRESS.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Interview is {interview.status}, not in progress")

    # Optimistic-concurrency guard: a duplicate/retried submit of the same
    # turn_number must not double-spend a Gemini call. Deliberately not
    # reusing IdempotencyKeys (its session_id FK is hard-tied to Sessions,
    # not InterviewSessions) -- turn_count itself is the natural, already-
    # persisted counter to check against.
    if turn_number != interview.turn_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Expected turn_number {interview.turn_count}, got {turn_number}. Re-fetch the interview to reconcile.",
        )

    validate_answer_audio(file)
    answer_audio_bytes = await file.read()
    answer_mime_type = file.content_type

    transcript_raw = await asyncio.to_thread(read_blob, interview.transcript_blob_path)
    transcript = json.loads(transcript_raw)

    answer_audio_path = upload_interview_audio(
        str(interview.id), turn_number, "user", answer_audio_bytes, answer_mime_type
    )

    anonymized, roast = await _load_resume_context(interview.resume_session_id)
    system_context = interview_prompts.build_interview_system_context(anonymized, roast, interview.job_description)
    turn_prompt = interview_prompts.build_turn_prompt(system_context, transcript)

    async with _gemini_call_guard():
        raw_response, _usage, _model = await interview_llm.generate_turn_response(
            turn_prompt, answer_audio_bytes, answer_mime_type
        )
    validated = interview_validator.validate_turn_response(
        raw_response, turn_count=interview.turn_count, max_turns=interview.max_turns
    )

    transcript = interview_service.record_turn_answer(
        transcript,
        turn_number,
        answer_transcript=validated.answer_transcript,
        answer_audio_path=answer_audio_path,
        reaction_text=validated.reaction_text,
    )

    if validated.is_final_turn:
        response_text = validated.reaction_text
        async with _gemini_call_guard():
            response_audio_bytes, response_content_type = await tts_client.synthesize_speech(response_text)
        response_audio_path = upload_interview_audio(
            str(interview.id), turn_number, "closing", response_audio_bytes, response_content_type
        )
        response_audio_url = _audio_url(interview.id, turn_number, "closing")
    else:
        response_text = f"{validated.reaction_text} {validated.next_question}".strip()
        async with _gemini_call_guard():
            response_audio_bytes, response_content_type = await tts_client.synthesize_speech(response_text)
        next_turn_number = turn_number + 1
        response_audio_path = upload_interview_audio(
            str(interview.id), next_turn_number, "prompt", response_audio_bytes, response_content_type
        )
        response_audio_url = _audio_url(interview.id, next_turn_number, "prompt")
        transcript = interview_service.append_question_turn(
            transcript,
            turn=next_turn_number,
            question_text=validated.next_question,
            question_audio_path=response_audio_path,
        )

    transcript_blob_path = upload_interview_transcript(str(interview.id), transcript)
    await interview_service.set_transcript_blob_path(db, interview, transcript_blob_path)
    interview = await interview_service.advance_turn_count(db, interview)

    score_payload = {}
    if validated.is_final_turn:
        scoring_prompt = interview_prompts.build_scoring_prompt(system_context, transcript)
        async with _gemini_call_guard():
            raw_score, _usage2, _model2 = await interview_llm.generate_score(scoring_prompt)
        validated_score = interview_validator.validate_score_response(raw_score)
        interview = await interview_service.finalize_interview(db, interview, validated_score)
        score_payload = {
            "score": interview.score,
            "strengths": interview.strengths,
            "weaknesses": interview.weaknesses,
            "next_steps": interview.next_steps,
        }

    return InterviewTurnApiResponse(
        interview_id=str(interview.id),
        turn_number=turn_number,
        reaction_text=validated.reaction_text,
        next_question=validated.next_question,
        response_audio_url=response_audio_url,
        is_final=validated.is_final_turn,
        status=interview.status,
        **score_payload,
    )


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

    transcript = []
    if interview.transcript_blob_path:
        raw = await asyncio.to_thread(read_blob, interview.transcript_blob_path)
        transcript_raw = json.loads(raw)
        transcript = [
            TranscriptTurnEntry(
                turn=t["turn"],
                question_text=t["question_text"],
                question_audio_url=_audio_url(interview.id, t["turn"], "prompt"),
                answer_transcript=t.get("answer_transcript"),
                answer_audio_url=_audio_url(interview.id, t["turn"], "user") if t.get("answer_audio_path") else None,
                reaction_text=t.get("reaction_text"),
            )
            for t in transcript_raw
        ]

    resume_session = await get_resume_session(session_id=interview.resume_session_id, db=db)

    return InterviewDetailResponse(
        interview_id=str(interview.id),
        status=interview.status,
        resume_session_id=str(interview.resume_session_id),
        roast_slug=resume_session.slug if resume_session else None,
        job_description=interview.job_description,
        turn_count=interview.turn_count,
        max_turns=interview.max_turns,
        transcript=transcript,
        score=interview.score,
        strengths=interview.strengths,
        weaknesses=interview.weaknesses,
        next_steps=interview.next_steps,
        started_at=interview.started_at,
        completed_at=interview.completed_at,
    )


@interview_router.get("/interview/{interview_id}/audio/{turn}/{kind}")
async def get_interview_audio(
    interview_id: str,
    turn: int,
    kind: str,
    db: AsyncSession = Depends(get_db_sqlalchemy),
    curr_user: Users = Depends(get_current_user),
):
    """
    Streams the blob directly (same approach GET /r/{slug} uses for the
    PNG) rather than generating a SAS URL -- nothing in this codebase does
    that today, and this keeps the per-request auth/ownership check
    server-side rather than trusting a time-limited signed URL.
    """
    interview = await _get_owned_interview(interview_id, curr_user, db)

    if kind not in ("prompt", "user", "closing"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown audio kind")

    # Extension is unknown from the path alone (wav for our own TTS output,
    # whatever the browser recorded for "user") -- try the content types we
    # actually ever write, in order, rather than requiring the caller to
    # know the extension.
    from ..services.blob import blob_exists

    for ext, content_type in (("wav", "audio/wav"), ("webm", "audio/webm"), ("mp4", "audio/mp4"), ("mpeg", "audio/mpeg"), ("ogg", "audio/ogg")):
        blob_path = f"interview-audio/{interview.id}/turn_{turn}_{kind}.{ext}"
        if blob_exists(blob_path):
            audio_bytes = await asyncio.to_thread(read_blob, blob_path)
            return Response(content=audio_bytes, media_type=content_type)

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio not found")


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
