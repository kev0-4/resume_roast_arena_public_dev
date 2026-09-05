'''
ALSO BEFORE THIS enqueue_anonymization() add to backend/src/services/service_bus.py
Fetch session

Validate status == NORMALIZED

Mark ANONYMIZING

Load normalized.json

Call redactor

Call assembler

Upload anonymized.json

Mark ANONYMIZED

No queue logic here.
No message handling here.

just orchestration.
'''


"""
Anonymization processor.

Orchestrates:
normalized.json → anonymized.json

Handles:
- state transitions
- pipeline execution
- error classification
"""

from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from backend.src.db.sessions import Sessions, JobStatusEnum
from backend.src.services.session_service import get_session
from backend.src.services.blob import read_blob, upload_normalized, upload_extracted  # keep consistent style
from backend.src.utils.telemetry import emit_event

from .schemas import AnonymizationJobMessage
from .state import mark_anonymizing, mark_anonymized, mark_failed
from .errors import (
    TransientAnonymizationError,
    PermanentAnonymizationError,
)

from .pipeline.loader import load_normalized
from .pipeline.redactor import redact_content
from .pipeline.assembler import assemble_anonymized

# You will create this if not already present
from backend.src.services.blob import upload_anonymized 
from backend.src.services.service_bus import enqueue_scoring



async def process_anonymization_job(
    *,
    db: AsyncSession,
    message: AnonymizationJobMessage,
) -> None:
    """
    Main orchestrator for anonymization stage.
    """

    session_id = message.session_id

    # ------------------------------------------------------------
    # 1. Fetch session
    # ------------------------------------------------------------
    session: Sessions | None = await get_session(
        db=db,
        session_id=session_id,
    )

    if session is None:
        return

    # ------------------------------------------------------------
    # 2. Idempotency guards
    # ------------------------------------------------------------
    if session.status == JobStatusEnum.FAILED:
        return

    if session.status == JobStatusEnum.ANONYMIZED:
        return

    if session.status != JobStatusEnum.NORMALIZED:
        return

    # ------------------------------------------------------------
    # 3. Mark ANONYMIZING
    # ------------------------------------------------------------
    session = await mark_anonymizing(db=db, session=session)
    anonymization_started_at = datetime.utcnow()

    try:
        # --------------------------------------------------------
        # 4. Load normalized artifact
        # --------------------------------------------------------
        try:
            normalized = load_normalized(
                blob_path=message.normalized_blob_path
            )
        except Exception as e:
            raise TransientAnonymizationError(
                f"Failed to load normalized artifact: {e}"
            )

        # --------------------------------------------------------
        # 5. Extract required inputs
        # --------------------------------------------------------
        try:
            blocks = normalized["content"]["blocks"]
            entities = normalized["content"]["entities"]
        except Exception as e:
            raise PermanentAnonymizationError(
                f"Malformed normalized content: {e}"
            )

        # --------------------------------------------------------
        # 6. Redaction
        # --------------------------------------------------------
        redacted_blocks, redactions = redact_content(
            blocks=blocks,
            entities=entities,
        )

        # --------------------------------------------------------
        # 7. Assemble artifact
        # --------------------------------------------------------
        anonymized_payload = assemble_anonymized(
            session_id=session_id,
            normalized=normalized,
            redacted_blocks=redacted_blocks,
            redactions=redactions,
            anonymized_at=anonymization_started_at,
        )

        # --------------------------------------------------------
        # 8. Upload artifact
        # --------------------------------------------------------
        try:
            upload_anonymized(
                session_id=str(session_id),
                data=anonymized_payload,
            )
        except Exception as e:
            raise TransientAnonymizationError(
                f"Failed to upload anonymized artifact: {e}"
            )

        # --------------------------------------------------------
        # 9. Mark success
        # --------------------------------------------------------
        await mark_anonymized(db=db, session=session)

        await db.commit()
        emit_event("anonymization.enqueuing_scoring", {"session_id": str(session_id), "status": "INFO"})
        enqueue_scoring(
        session_id=str(session_id),
        anonymized_blob_path=f"anonymized/{session_id}/anonymized.json"
        )


    # ------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------
    except TransientAnonymizationError:
        # Let consumer retry
        raise

    except PermanentAnonymizationError as e:
        await mark_failed(
            db=db,
            session=session,
            error_code="ANONYMIZATION_FAILED",
            error_reason=str(e),
        )
        await db.commit()
        
    except Exception as e:
        # Unknown → treat as transient
        raise TransientAnonymizationError(str(e))