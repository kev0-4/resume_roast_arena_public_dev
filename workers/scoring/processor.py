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
from backend.src.services.blob import upload_scored

from .schemas import ScoringJobMessage
from .state import mark_scoring, mark_scored, mark_failed
from .errors import (
    TransientScoringError,
    PermanentScoringError,
)

from .pipeline.loader import load_anonymized
from .pipeline.scorer import score_resume
from .pipeline.assembler import assemble_scored


async def process_scoring_job(
    *,
    db: AsyncSession,
    message: ScoringJobMessage,
) -> None:
    """
    Main orchestrator for scoring stage.
    """

    print("--entered process_scoring_job")
    session_id = message.session_id

    # ------------------------------------------------------------
    # 1. Fetch session
    # ------------------------------------------------------------
    session: Sessions | None = await get_session(
        db=db,
        session_id=session_id,
    )

    if session is None:
        print(f"Returning: session is None, session_id: {session_id}")
        return

    # ------------------------------------------------------------
    # 2. Idempotency guards
    # ------------------------------------------------------------
    if session.status == JobStatusEnum.FAILED:
        print(f"Returning: session status is FAILED, session_id: {session_id}")
        return

    if session.status == JobStatusEnum.SCORED:
        print(f"Returning: session status is SCORED, session_id: {session_id}")
        return

    if session.status != JobStatusEnum.ANONYMIZED:
        print(f"Returning: session status is {session.status}, session_id: {session_id} not ANONYMIZED")
        return

    # ------------------------------------------------------------
    # 3. Mark SCORING
    # ------------------------------------------------------------
    session = await mark_scoring(db=db, session=session)
    scoring_started_at = datetime.utcnow()
    print("--entered process_scoring_job -> marked scoring")

    try:
        # --------------------------------------------------------
        # 4. Load anonymized artifact
        # --------------------------------------------------------
        print(f"DEBUG: Loading anonymized artifact: {message.anonymized_blob_path}")
        try:
            anonymized = load_anonymized(
                blob_path=message.anonymized_blob_path
            )
        except Exception as e:
            raise TransientScoringError(
                f"Failed to load anonymized artifact: {e}"
            )
        print(f"DEBUG: Successfully loaded anonymized data. Keys: {list(anonymized.keys())}")

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
        print(f"DEBUG: Inputs extracted. Signals: {len(signals)}, Metrics: {len(metrics)}, Blocks: {len(blocks)}")

        # --------------------------------------------------------
        # 6. Run scoring
        # --------------------------------------------------------
        scoring_result = score_resume(
            signals=signals,
            metrics=metrics,
            blocks=blocks,
        )
        print(f"DEBUG: Scoring complete. Issues: {len(scoring_result.issues)}, Strengths: {len(scoring_result.strengths)}")

        # --------------------------------------------------------
        # 7. Assemble final artifact
        # --------------------------------------------------------
        scored_payload = assemble_scored(
            session_id=session_id,
            anonymized=anonymized,
            scoring_result=scoring_result,
            scored_at=scoring_started_at,
        )
        print("DEBUG: Scored payload assembled successfully")

        # --------------------------------------------------------
        # 8. Upload artifact
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
        print(f"DEBUG: Scored payload uploaded for session_id: {session_id}")

        # --------------------------------------------------------
        # 9. Mark success
        # --------------------------------------------------------
        await mark_scored(db=db, session=session)
        await db.commit()
        print(f"DEBUG: Session marked as SCORED in database, session_id: {session_id}")

    # ------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------
    except TransientScoringError:
        raise

    except PermanentScoringError as e:
        print(f"DEBUG: Permanent scoring error: {e}, session_id: {session_id}")
        await mark_failed(
            db=db,
            session=session,
            error_code="SCORING_FAILED",
            error_reason=str(e),
        )
        await db.commit()

    except Exception as e:
        print(f"DEBUG: Unexpected error in scoring: {e}, session_id: {session_id}")
        raise TransientScoringError(str(e))