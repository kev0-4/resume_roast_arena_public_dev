"""
workers/scoring/processor.py
Scoring processor.

Orchestrates:
anonymized.json → scored.json
"""

from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from backend.src.db.sessions import Sessions, JobStatusEnum
from backend.src.services.session_service import get_session
from backend.src.services.blob import upload_scored, upload_prompt
from backend.src.services.service_bus import enqueue_llm
from backend.src.utils.telemetry import emit_event

from .schemas import ScoringJobMessage
from .state import mark_scoring, mark_scored, mark_failed
from .errors import (
    TransientScoringError,
    PermanentScoringError,
)

from .pipeline.loader import load_anonymized
from .pipeline.scorer import score_resume
from .pipeline.assembler import assemble_scored
from .pipeline.prompt_builder import build_roast_prompt


async def process_scoring_job(
    *,
    db: AsyncSession,
    message: ScoringJobMessage,
) -> None:
    """
    Main orchestrator for scoring stage.
    """

    emit_event("scoring.job.started", {"session_id": str(message.session_id), "status": "INFO"})
    session_id = message.session_id

    # ------------------------------------------------------------
    # 1. Fetch session
    # ------------------------------------------------------------
    session: Sessions | None = await get_session(
        db=db,
        session_id=session_id,
    )

    if session is None:
        emit_event("scoring.session.not_found", {"session_id": str(session_id), "status": "WARNING"})
        return

    # ------------------------------------------------------------
    # 2. Idempotency guards
    # ------------------------------------------------------------
    if session.status == JobStatusEnum.FAILED:
        emit_event("scoring.guard.session_failed", {"session_id": str(session_id), "status": "INFO"})
        return

    if session.status == JobStatusEnum.SCORED:
        emit_event("scoring.guard.already_scored", {"session_id": str(session_id), "status": "INFO"})
        return

    if session.status != JobStatusEnum.ANONYMIZED:
        emit_event(
            "scoring.guard.not_anonymized",
            {"session_id": str(session_id), "current_status": session.status, "status": "WARNING"},
        )
        return

    # ------------------------------------------------------------
    # 3. Mark SCORING
    # ------------------------------------------------------------
    session = await mark_scoring(db=db, session=session)
    scoring_started_at = datetime.utcnow()
    emit_event("scoring.marked_scoring", {"session_id": str(session_id), "status": "INFO"})

    try:
        # --------------------------------------------------------
        # 4. Load anonymized artifact
        # --------------------------------------------------------
        emit_event(
            "scoring.loading_anonymized",
            {"session_id": str(session_id), "blob_path": message.anonymized_blob_path, "status": "INFO"},
        )
        try:
            anonymized = load_anonymized(
                blob_path=message.anonymized_blob_path
            )
        except Exception as e:
            raise TransientScoringError(
                f"Failed to load anonymized artifact: {e}"
            )
        emit_event(
            "scoring.anonymized_loaded",
            {"session_id": str(session_id), "keys": list(anonymized.keys()), "status": "INFO"},
        )

        # --------------------------------------------------------
        # 5. Extract inputs
        # --------------------------------------------------------
        try:
            signals = anonymized["signals"]
            metrics = anonymized["metrics"]
            blocks = anonymized["content"]["blocks"]
        except Exception as e:
            raise PermanentScoringError(
                f"Malformed anonymized payload: {e}"
            )
        emit_event(
            "scoring.inputs_extracted",
            {
                "session_id": str(session_id),
                "signal_count": len(signals),
                "metric_count": len(metrics),
                "block_count": len(blocks),
                "status": "INFO",
            },
        )

        # --------------------------------------------------------
        # 6. Run scoring
        # --------------------------------------------------------
        scoring_result = score_resume(
            signals=signals,
            metrics=metrics,
            blocks=blocks,
        )
        emit_event(
            "scoring.complete",
            {
                "session_id": str(session_id),
                "issue_count": len(scoring_result.issues),
                "strength_count": len(scoring_result.strengths),
                "status": "INFO",
            },
        )

        # --------------------------------------------------------
        # 7. Assemble final artifact
        # --------------------------------------------------------
        scored_payload = assemble_scored(
            session_id=session_id,
            anonymized=anonymized,
            scoring_result=scoring_result,
            scored_at=scoring_started_at,
        )
        emit_event("scoring.payload_assembled", {"session_id": str(session_id), "status": "INFO"})

        # --------------------------------------------------------
        # 8. Upload scored artifact
        # --------------------------------------------------------
        try:
            upload_scored(
                session_id=str(session_id),
                data=scored_payload,
            )
        except Exception as e:
            raise TransientScoringError(
                f"Failed to upload scored artifact: {e}"
            )
        emit_event("scoring.payload_uploaded", {"session_id": str(session_id), "status": "INFO"})

        # --------------------------------------------------------
        # 8b. Build LLM prompt (uses anonymized already in memory)
        # --------------------------------------------------------
        try:
            prompt = build_roast_prompt(
                anonymized=anonymized,
                scoring_result=scoring_result,
            )
        except Exception as e:
            raise PermanentScoringError(
                f"Failed to build roast prompt: {e}"
            )
        emit_event("scoring.prompt_built", {"session_id": str(session_id), "status": "INFO"})

        # --------------------------------------------------------
        # 8c. Upload prompt artifact
        # --------------------------------------------------------
        try:
            prompt_blob_path = upload_prompt(
                session_id=str(session_id),
                prompt=prompt,
            )
        except Exception as e:
            raise TransientScoringError(
                f"Failed to upload prompt artifact: {e}"
            )
        emit_event("scoring.prompt_uploaded", {"session_id": str(session_id), "status": "INFO"})

        # --------------------------------------------------------
        # 8d. Mark success -- BEFORE enqueueing, not after. The LLM worker
        # is a separate process with its own DB connection; it re-reads
        # this session's status as an idempotency guard the moment it
        # receives the message. If the message went out first and this
        # commit landed after, a fast consumer (routine on a local
        # Service Bus emulator) can read the still-SCORING status,
        # silently guard-return, and the message gets marked complete
        # anyway -- the job is dropped with no error anywhere. Real bug,
        # found via a live end-to-end upload sticking at SCORED forever.
        # --------------------------------------------------------
        await mark_scored(db=db, session=session)
        await db.commit()
        emit_event("scoring.marked_scored", {"session_id": str(session_id), "status": "INFO"})

        # --------------------------------------------------------
        # 9. Enqueue LLM roast job
        # --------------------------------------------------------
        try:
            enqueue_llm(
                session_id=str(session_id),
                prompt_blob_path=prompt_blob_path,
            )
        except Exception as e:
            raise TransientScoringError(
                f"Failed to enqueue LLM roast job: {e}"
            )
        emit_event("scoring.llm_job_enqueued", {"session_id": str(session_id), "status": "INFO"})

    # ------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------
    except TransientScoringError:
        raise

    except PermanentScoringError as e:
        emit_event(
            "scoring.error.permanent",
            {"session_id": str(session_id), "reason": str(e), "status": "ERROR"},
        )
        await mark_failed(
            db=db,
            session=session,
            error_code="SCORING_FAILED",
            error_reason=str(e),
        )
        await db.commit()

    except Exception as e:
        emit_event(
            "scoring.error.unexpected",
            {"session_id": str(session_id), "reason": str(e), "status": "ERROR"},
        )
        raise TransientScoringError(str(e))