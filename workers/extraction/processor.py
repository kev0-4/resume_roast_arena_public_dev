'''
this function orchestractes whole extraction data from file pipeline , also handels state transition while doing so 
and classify failures if can be retried or dead letter queue
'''
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from uuid import UUID
from .extractor.tika import extract_with_tika, compute_confidence, extract_with_ocr
from tika import parser
from backend.src.db.sessions import Sessions, JobStatusEnum
from backend.src.services.blob import read_blob, upload_extracted
from backend.src.services.service_bus import enqueue_normalization
from asyncio import sleep
from backend.src.services.session_service import get_session
from .schemas import ExtractionJobMessage
from .state import mark_processing, mark_extracted, mark_failed
from .errors import (TransientExtractionError,PermanentExtractionError,)
class LowConfidenceError(Exception):
    """Tika succeeded but confidence too low; trigger OCR."""

TIKA_CONFIDENCE_THRESHOLD = 0.50
MIN_EXTRACTED_CHARS = 200
OCR_CONFIDENCE = 0.80

async def process_extraction_job(db: AsyncSession, message:ExtractionJobMessage) ->None:
    print("--entered process_extraction_job")
    session_id = message.session_id
    session: Sessions | None = await get_session(db=db,session_id=message.session_id)
    if session is None:
        print("Returning: session is None")
        return 
    if session.status == JobStatusEnum.FAILED:
        print(f"Returning: session status is FAILED, session_id: {session.id}")
        return 
    if session.status == JobStatusEnum.EXTRACTED:
        print(f"Returning: session status is EXTRACTED, session_id: {session.id}")
        return 
    if session.status != JobStatusEnum.QUEUED:
        print(f"Returning: session status is {session.status}, session_id: {session.id} not queued")
        return#as invalid/unexpected state for this function, only queued jobs will be moved further
        
    session = await mark_processing(db=db, session=session)
    extraction_started_at = datetime.utcnow()
    print("--entered process_extraction_job -> marked processing")
    

    try:
        try:
            raw_bytes: bytes = read_blob(session.raw_blob_path)
        except Exception as e:
            raise TransientExtractionError(f"Failed to read raw blob {e}")
        
        used_ocr = False
        confidence = 0.0

        try:
            print("entered try")
            result = extract_with_tika(raw_bytes)    
            print("response came back from tika")        
            raw_text =  result.get('text')
            confidence = compute_confidence(raw_text)

            if confidence < TIKA_CONFIDENCE_THRESHOLD:
                raise LowConfidenceError("Low confidence – fallback to OCR")

           
        except LowConfidenceError:
            result = extract_with_ocr(raw_bytes)    
            used_ocr = True
            raw_text =  result.get('text')
            confidence = OCR_CONFIDENCE

        except PermanentExtractionError as e:
                print(f"OCR extraction failed: {e}")
                raise 

        except TransientExtractionError as e:
            raise TransientExtractionError(f"failed transistent erorr: {e}")            
            
        if not raw_text or len(raw_text.strip()) <100:
            raise PermanentExtractionError (f"Extraction Produced insufficient text")
        
        extracted_payload:dict = {
            "session_id": str(session_id),
            "extraction_version": "1.0",
            "source": {
                "used_ocr": used_ocr,
                "confidence": confidence,
                "file_type": session.raw_blob_path.split(".")[-1].upper(),
            },
            "raw_text": raw_text,
            "metrics": {
                "character_count": len(raw_text),
            },
            "timestamps": {
                "started_at": extraction_started_at.isoformat(),
                "completed_at": datetime.utcnow().isoformat(),
            },
        }

        try:
            upload_extracted(session_id=str(session_id),data=extracted_payload)
        except Exception as e:
            raise TransientExtractionError(f"failed to upload extarcted artifact {e}")
        

        await mark_extracted(db=db,session=session)
        db.commit()
        enqueue_normalization(
        session_id=str(session_id),
        extracted_blob_path=f"extracted/{session_id}/extracted.json"
        )

    except TransientExtractionError:
        raise
    except PermanentExtractionError as e:
        await mark_failed(db=db,session=session,error_code="EXTRACTION_FAILED", error_reason=str(e))

    except Exception as e:
        raise TransientExtractionError(str(e))      
