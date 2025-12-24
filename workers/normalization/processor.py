from sqlalchemy.ext.asyncio import AsyncSession
from backend.src.db.sessions import JobStatusEnum, Sessions
from backend.src.utils.telemetry import emit_event
from backend.src.db.sessions import JobStatusEnum
from backend.src.services.blob import read_blob, upload_extracted
from asyncio import sleep
from backend.src.services.session_service import get_session
from .state import mark_normalized,mark_normalizing,mark_failed
import enum
import datetime
from .schemas import NormalizationJobMessage
from pipeline.loader import load_extracted
from pipeline.segmenter import segment_text
from pipeline.entities import extract_entities
from pipeline.signals import compute_signals
from pipeline.metrics import compute_metrics
from pipeline.assembler import assemble_normalized
from .errors import PermanentNormalizationError, TransientNormalizationError

async def process_normalization_job(db: AsyncSession, message: NormalizationJobMessage) -> None:
    print("--entered process_normalization_job")
    session_id = message.session_id
    session: Sessions | None = await get_session(db=db,session_id=message.session_id)
    if session is None:
        print("Returning: session is None")
        return 
    if session.status == JobStatusEnum.FAILED:
        print(f"Returning: session status is FAILED, session_id: {session.id}")
        return 
    if session.status == JobStatusEnum.NORMALIZED:
        print(f"Returning: session status is NORMALIZED, session_id: {session.id}")
        return 
    if session.status != JobStatusEnum.QUEUED:
        print(f"Returning: session status is {session.status}, session_id: {session.id} not queued")
        return#as invalid/unexpected state for this function, only queued jobs will be moved further
        
    session = await mark_normalizing(db=db, session=session)
    normalization_started_at = datetime.datetime.utcnow()
    print("--entered process_normalization_job -> marked normalizing")
    try:
        extracted = load_extracted(blob_path=message.extracted_blob_path)
        raw_text = extracted.get("raw_text")
        if not raw_text:
            raise PermanentNormalizationError("Extracted payload missing raw_text")

        blocks: dict = segment_text(raw_text=raw_text)
        entities: dict = extract_entities(raw_text=raw_text)
        signals : dict = compute_signals(blocks=blocks,raw_text=raw_text)
        metrics : dict = compute_metrics(blocks=blocks,raw_text=raw_text)
        normalized_payload: dict = assemble_normalized(
            session_id=session_id,
            extracted=extracted,
            blocks=blocks,
            entities=entities,
            signals=signals,
            metrics=metrics,
            normalized_at=normalization_started_at,
        )
        upload_normalized(session_id=str(session_id),data=normalized_payload,)
        await mark_normalized(db=db,session=session)
    except TransientNormalizationError:
        raise
    except PermanentNormalizationError as e:
        await mark_failed(db=db, session=session, error_code="NORMALIZATION_FAILED",error_reason=str(e))
    except Exception as e:
        raise TransientNormalizationError(str(e))


def upload_normalized(session_id, data):
    pass # implement this in backend blob service