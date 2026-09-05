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

    print("--entered process_llm_job")
    session_id = message.session_id

    # ----------------------------------------------------------------
    # 1. Fetch session
    # ----------------------------------------------------------------
    session: Sessions | None = await get_session(db=db, session_id=session_id)
    if session is None:
        print(f"Returning: session not found, session_id: {session_id}")
        return

    # ----------------------------------------------------------------
    # 2. Idempotency guards
    # ----------------------------------------------------------------
    if session.status == JobStatusEnum.FAILED:
        print(f"Returning: session is FAILED, session_id: {session_id}")
        return

    if session.status == JobStatusEnum.ROASTED:
        print(f"Returning: session already ROASTED, session_id: {session_id}")
        return

    if session.status != JobStatusEnum.SCORED:
        print(
            f"Returning: session status is {session.status}, "
            f"expected SCORED, session_id: {session_id}"
        )
        return

    # ----------------------------------------------------------------
    # 3. Mark ROASTING
    # ----------------------------------------------------------------
    session = await mark_roasting(db=db, session=session)
    roasting_started_at = datetime.utcnow()
    print("--marked ROASTING")

    try:
        # ------------------------------------------------------------
        # 4. Load prompt artifact
        # ------------------------------------------------------------
        try:
            prompt = load_prompt(message.prompt_blob_path)
        except Exception as e:
            raise TransientLLMError(f"Failed to load prompt artifact: {e}")
        print(f"DEBUG: Prompt loaded ({len(prompt)} chars) for session_id: {session_id}")

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
        print(
            f"DEBUG: LLM responded. Model: {model_used}, "
            f"tokens in/out: {usage.get('input_tokens')}/{usage.get('output_tokens')}"
        )

        # ------------------------------------------------------------
        # 6. Parse + validate output
        # ------------------------------------------------------------
        try:
            roast_result = parse_roast_output(raw_text)
        except ValueError as e:
            raise PermanentLLMError(f"Failed to parse LLM output: {e}")
        print("DEBUG: LLM output parsed successfully")

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
        print("DEBUG: Roast payload assembled")

        # ------------------------------------------------------------
        # 8. Upload roast.json
        # ------------------------------------------------------------
        try:
            roast_blob_path = upload_roast(session_id=str(session_id), data=roast_payload)
        except Exception as e:
            raise TransientLLMError(f"Failed to upload roast artifact: {e}")
        print(f"DEBUG: roast.json uploaded for session_id: {session_id}")

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
        print(f"DEBUG: render job enqueued for session_id: {session_id}")

        # ------------------------------------------------------------
        # 9. Mark ROASTED
        # ------------------------------------------------------------
        await mark_roasted(db=db, session=session)
        await db.commit()
        print(f"DEBUG: Session marked ROASTED, session_id: {session_id}")

    # ----------------------------------------------------------------
    # Error handling
    # ----------------------------------------------------------------
    except TransientLLMError:
        raise

    except PermanentLLMError as e:
        print(f"DEBUG: Permanent LLM error: {e}, session_id: {session_id}")
        await mark_failed(
            db=db,
            session=session,
            error_code="LLM_ROAST_FAILED",
            error_reason=str(e),
        )
        await db.commit()

    except Exception as e:
        print(f"DEBUG: Unexpected error in LLM processor: {e}, session_id: {session_id}")
        raise TransientLLMError(str(e))
