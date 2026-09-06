"""
workers/llm/processor.py

LLM roast processor.

Orchestrates:
prompt.txt → roast.json

Pipeline:
1. Fetch session
2. Idempotency guards
3. Mark ROASTING
4. Load prompt artifact
5. Call LLM
6. Parse + validate output
7. Assemble roast artifact
8. Upload roast.json
8b. Enqueue render job
9. Mark ROASTED
"""

from google.genai import errors as genai_errors
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from backend.src.db.sessions import Sessions, JobStatusEnum
from backend.src.services.session_service import get_session
from backend.src.services.blob import upload_roast
from backend.src.services.service_bus import enqueue_render
from backend.src.utils.telemetry import emit_event

from .schemas import LLMJobMessage
from .state import mark_roasting, mark_roasted, mark_failed
from .errors import TransientLLMError, PermanentLLMError

from .pipeline.loader import load_prompt
from .pipeline.client import call_roast_llm
from .pipeline.validator import parse_roast_output
from .pipeline.assembler import assemble_roast


async def process_llm_job(
    *,
    db: AsyncSession,
    message: LLMJobMessage,
) -> None:
    """Main orchestrator for the LLM roast stage."""

    emit_event("llm.job.started", {"session_id": str(message.session_id), "status": "INFO"})
    session_id = message.session_id

    # ----------------------------------------------------------------
    # 1. Fetch session
    # ----------------------------------------------------------------
    session: Sessions | None = await get_session(db=db, session_id=session_id)
    if session is None:
        emit_event("llm.session.not_found", {"session_id": str(session_id), "status": "WARNING"})
        return

    # ----------------------------------------------------------------
    # 2. Idempotency guards
    # ----------------------------------------------------------------
    if session.status == JobStatusEnum.FAILED:
        emit_event("llm.guard.session_failed", {"session_id": str(session_id), "status": "INFO"})
        return

    if session.status == JobStatusEnum.ROASTED:
        emit_event("llm.guard.already_roasted", {"session_id": str(session_id), "status": "INFO"})
        return

    if session.status != JobStatusEnum.SCORED:
        emit_event(
            "llm.guard.not_scored",
            {"session_id": str(session_id), "current_status": session.status, "status": "WARNING"},
        )
        return

    # ----------------------------------------------------------------
    # 3. Mark ROASTING
    # ----------------------------------------------------------------
    session = await mark_roasting(db=db, session=session)
    roasting_started_at = datetime.utcnow()
    emit_event("llm.marked_roasting", {"session_id": str(session_id), "status": "INFO"})

    try:
        # ------------------------------------------------------------
        # 4. Load prompt artifact
        # ------------------------------------------------------------
        try:
            prompt = load_prompt(message.prompt_blob_path)
        except Exception as e:
            raise TransientLLMError(f"Failed to load prompt artifact: {e}")
        emit_event(
            "llm.prompt_loaded",
            {"session_id": str(session_id), "char_count": len(prompt), "status": "INFO"},
        )

        # ------------------------------------------------------------
        # 5. Call LLM
        # ------------------------------------------------------------
        try:
            raw_text, usage, model_used = await call_roast_llm(prompt)
        except genai_errors.ServerError as e:
            raise TransientLLMError(f"Gemini server error ({e.code}): {e}")
        except genai_errors.ClientError as e:
            if e.code == 429:
                raise TransientLLMError(f"Gemini rate limit: {e}")
            raise PermanentLLMError(f"Gemini client error ({e.code}): {e}")
        emit_event(
            "llm.response_received",
            {
                "session_id": str(session_id),
                "model": model_used,
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "status": "INFO",
            },
        )

        # ------------------------------------------------------------
        # 6. Parse + validate output
        # ------------------------------------------------------------
        try:
            roast_result = parse_roast_output(raw_text, source_text=prompt)
        except ValueError as e:
            raise PermanentLLMError(f"Failed to parse LLM output: {e}")
        emit_event("llm.output_parsed", {"session_id": str(session_id), "status": "INFO"})

        # ------------------------------------------------------------
        # 7. Assemble roast artifact
        # ------------------------------------------------------------
        roast_payload = assemble_roast(
            session_id=str(session_id),
            roast_result=roast_result,
            model=model_used,
            usage=usage,
            roasted_at=roasting_started_at,
        )
        emit_event("llm.payload_assembled", {"session_id": str(session_id), "status": "INFO"})

        # ------------------------------------------------------------
        # 8. Upload roast.json
        # ------------------------------------------------------------
        try:
            roast_blob_path = upload_roast(session_id=str(session_id), data=roast_payload)
        except Exception as e:
            raise TransientLLMError(f"Failed to upload roast artifact: {e}")
        emit_event("llm.roast_uploaded", {"session_id": str(session_id), "status": "INFO"})

        # ------------------------------------------------------------
        # 8b. Enqueue render job
        # ------------------------------------------------------------
        try:
            enqueue_render(
                session_id=str(session_id),
                scored_blob_path=f"scored/{session_id}/scored.json",
                roast_blob_path=roast_blob_path,
            )
        except Exception as e:
            raise TransientLLMError(f"Failed to enqueue render job: {e}")
        emit_event("llm.render_job_enqueued", {"session_id": str(session_id), "status": "INFO"})

        # ------------------------------------------------------------
        # 9. Mark ROASTED
        # ------------------------------------------------------------
        await mark_roasted(db=db, session=session)
        await db.commit()
        emit_event("llm.marked_roasted", {"session_id": str(session_id), "status": "INFO"})

    # ----------------------------------------------------------------
    # Error handling
    # ----------------------------------------------------------------
    except TransientLLMError:
        raise

    except PermanentLLMError as e:
        emit_event(
            "llm.error.permanent",
            {"session_id": str(session_id), "reason": str(e), "status": "ERROR"},
        )
        await mark_failed(
            db=db,
            session=session,
            error_code="LLM_ROAST_FAILED",
            error_reason=str(e),
        )
        await db.commit()

    except Exception as e:
        emit_event(
            "llm.error.unexpected",
            {"session_id": str(session_id), "reason": str(e), "status": "ERROR"},
        )
        raise TransientLLMError(str(e))
