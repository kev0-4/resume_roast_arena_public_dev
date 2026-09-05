from sqlalchemy.ext.asyncio import AsyncSession
from backend.src.db.sessions import JobStatusEnum, Sessions
from backend.src.utils.telemetry import emit_event
from backend.src.db.sessions import JobStatusEnum
from backend.src.services.blob import read_blob, upload_extracted, upload_normalized
from asyncio import sleep
from backend.src.services.session_service import get_session
from backend.src.services.service_bus import enqueue_anonymization
from .state import mark_normalized,mark_normalizing,mark_failed
import enum
import datetime
from .schemas import NormalizationJobMessage
from .pipeline.loader import load_extracted
from .pipeline.segmenter import segment_text
from .pipeline.entities import extract_entities
from .pipeline.signals import compute_signals
from .pipeline.metrics import compute_metrics
from .pipeline.assembler import assemble_normalized
from .errors import PermanentNormalizationError, TransientNormalizationError

async def process_normalization_job(db: AsyncSession, message: NormalizationJobMessage) -> None:
    emit_event("normalization.job.started", {"session_id": str(message.session_id), "status": "INFO"})
    session_id = message.session_id
    session: Sessions | None = await get_session(db=db,session_id=message.session_id)
    if session is None:
        emit_event("normalization.session.not_found", {"session_id": str(session_id), "status": "WARNING"})
        return
    if session.status == JobStatusEnum.FAILED:
        emit_event("normalization.guard.session_failed", {"session_id": str(session.id), "status": "INFO"})
        return
    if session.status == JobStatusEnum.NORMALIZED:
        emit_event("normalization.guard.already_normalized", {"session_id": str(session.id), "status": "INFO"})
        return
    if session.status == JobStatusEnum.QUEUED:
        emit_event(
            "normalization.guard.still_queued",
            {"session_id": str(session.id), "current_status": session.status, "status": "WARNING"},
        )
        return
    if session.status != JobStatusEnum.EXTRACTED:
        emit_event(
            "normalization.guard.not_extracted",
            {"session_id": str(session.id), "current_status": session.status, "status": "WARNING"},
        )
        return#as invalid/unexpected state for this function, only queued jobs will be moved further

    session = await mark_normalizing(db=db, session=session)
    normalization_started_at = datetime.datetime.utcnow()
    emit_event("normalization.marked_normalizing", {"session_id": str(session_id), "status": "INFO"})


    try:
        emit_event(
            "normalization.loading_extracted",
            {"session_id": str(session_id), "blob_path": message.extracted_blob_path, "status": "INFO"},
        )

        extracted =  load_extracted(blob_path=message.extracted_blob_path)
        emit_event(
            "normalization.extracted_loaded",
            {"session_id": str(session_id), "keys": list(extracted.keys()), "status": "INFO"},
        )

        raw_text = extracted.get("raw_text")
        emit_event(
            "normalization.raw_text_retrieved",
            {"session_id": str(session_id), "char_count": len(raw_text) if raw_text else 0, "status": "INFO"},
        )

        if not raw_text:
            emit_event("normalization.raw_text_missing", {"session_id": str(session_id), "status": "ERROR"})
            raise PermanentNormalizationError("Extracted payload missing raw_text")

        blocks: dict = segment_text(raw_text=raw_text)
        emit_event(
            "normalization.segmentation_complete",
            {"session_id": str(session_id), "block_count": len(blocks), "status": "INFO"},
        )

        entities: dict = extract_entities(raw_text=raw_text)
        emit_event(
            "normalization.entities_extracted",
            {"session_id": str(session_id), "entity_count": len(entities), "status": "INFO"},
        )

        signals: dict = compute_signals(blocks=blocks, raw_text=raw_text,entities=entities)
        emit_event(
            "normalization.signals_computed",
            {"session_id": str(session_id), "signal_count": len(signals), "status": "INFO"},
        )

        metrics: dict = compute_metrics(blocks=blocks, raw_text=raw_text,entities=entities)
        emit_event(
            "normalization.metrics_computed",
            {"session_id": str(session_id), "metric_count": len(metrics), "status": "INFO"},
        )

        normalized_payload: dict = assemble_normalized(
            session_id=session_id,
            extracted=extracted,
            blocks=blocks,
            entities=entities,
            signals=signals,
            metrics=metrics,
            normalized_at=normalization_started_at,
        )
        emit_event("normalization.payload_assembled", {"session_id": str(session_id), "status": "INFO"})

        upload_normalized(session_id=str(session_id), data=normalized_payload)
        emit_event("normalization.payload_uploaded", {"session_id": str(session_id), "status": "INFO"})

        await mark_normalized(db=db, session=session)
        emit_event("normalization.marked_normalized", {"session_id": str(session_id), "status": "INFO"})
        await db.commit()
        enqueue_anonymization(
            session_id=str(session_id),
            normalized_blob_path=f"normalized/{session_id}/normalized.json"
        )


    except TransientNormalizationError as e:
        emit_event(
            "normalization.error.transient",
            {"session_id": str(session_id), "reason": str(e), "status": "ERROR"},
        )
        raise
    except PermanentNormalizationError as e:
        await mark_failed(db=db, session=session, error_code="NORMALIZATION_FAILED",error_reason=str(e))
    except Exception as e:
        raise TransientNormalizationError(str(e))


