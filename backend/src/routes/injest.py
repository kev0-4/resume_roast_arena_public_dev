from fastapi import APIRouter, Response, status, Depends, Request, HTTPException, UploadFile, File, Header
from sqlalchemy.ext.asyncio import AsyncSession
from ..dependencies.auth import get_current_user
from ..utils.telemetry import emit_event, with_trace
from ..services.blob import upload_raw, delete_raw, read_blob, blob_exists, initialize_blob_storage
from ..services.service_bus import enqueue_extraction
from ..services.session_service import create_sessions, get_session, update_session_status, update_session_raw_blob_path
from ..services.idempotency_service import get_session_by_key, create_key_mapping
import logging
import uuid
from typing import Optional
from ..db.session import get_db_sqlalchemy
from ..db.sessions import JobStatusEnum
from ..dependencies.auth import get_current_user
from ..utils.file_validation import validate_upload

injest_router = APIRouter()


@injest_router.post("/ingest", status_code=status.HTTP_202_ACCEPTED)
async def injest_resume(file: UploadFile = File(...),
                        db: AsyncSession = Depends(get_db_sqlalchemy),
                        curr_user=Depends(get_current_user),
                        idempotency_key: str | None = Header(default=None, alias="X-Idempotency-Key")):
    user_id: Optional[uuid.UUID] = (
        curr_user.id if curr_user is not None else None
    )

    try:
        validate_upload(file)
        emit_event(
            "ingest.validation.success",
            {
                "filename": file.filename,
                "content_type": file.content_type,
                "user_id": str(user_id) if user_id else None,
                "status": "INFO",
                "route": "POST /v1/ingest"
            }
        )
    except ValueError as e:
        emit_event(
            "ingest.validation.failure",
            {
                "filename": file.filename,
                "content_type": file.content_type,
                "user_id": str(user_id) if user_id else None,
                "reason": str(e),
                "status": "WARNING",
                "route": "POST /v1/ingest"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(e)
        )

    if idempotency_key:
        existing_session = await get_session_by_key(db=db, key=idempotency_key, user_id=user_id)
        if existing_session:
            emit_event(
                "ingest.idempotency.duplicate",
                {
                    "session_id": str(existing_session.id),
                    "idempotency_key": idempotency_key,
                    "user_id": str(user_id) if user_id else None,
                    "existing_status": existing_session.status,
                    "status": "INFO",
                    "route": "POST /v1/ingest"
                }
            )
            return {
                "session_id": str(existing_session.id),
                "status": existing_session.status,
                "links": {
                    "session": f"api/v1/sessions/{existing_session.id}"
                },
            }

    session = await create_sessions(
        db=db, user_id=user_id
    )
    session_id = session.id

    emit_event(
        "ingest.session.created",
        {
            "session_id": str(session_id),
            "user_id": str(user_id) if user_id else None,
            "idempotency_key": idempotency_key,
            "status": "INFO",
            "route": "POST /v1/ingest"
        }
    )

    if idempotency_key:
        await create_key_mapping(
            db=db,
            key=idempotency_key,
            user_id=user_id,
            session_id=session.id,
        )

    try:
        file_bytes = await file.read()

        raw_blob_path = upload_raw(session_id=str(session.id),
                                   filename=file.filename,
                                   file_bytes=file_bytes)

        emit_event(
            "ingest.blob.uploaded",
            {
                "session_id": str(session_id),
                "filename": file.filename,
                "blob_path": raw_blob_path,
                "file_size": len(file_bytes),
                "user_id": str(user_id) if user_id else None,
                "status": "INFO",
                "route": "POST /v1/ingest"
            }
        )

        session = await update_session_raw_blob_path(
            db=db, session=session, raw_blob_path=raw_blob_path
        )
        session = await update_session_status(
            db=db, session=session, new_status=JobStatusEnum.QUEUED
        )
        await db.commit()

# Refresh to reload attributes from database
        await db.refresh(session)
        enqueue_extraction(
            session_id=str(session.id), raw_blob_path=raw_blob_path
        )

        emit_event(
            "ingest.extraction.enqueued",
            {
                "session_id": str(session_id),
                "blob_path": raw_blob_path,
                "user_id": str(user_id) if user_id else None,
                "status": "INFO",
                "route": "POST /v1/ingest"
            }
        )

        emit_event(
            "ingest.success",
            {
                "session_id": str(session_id),
                "final_status": session.status,
                "user_id": str(user_id) if user_id else None,
                "status": "INFO",
                "route": "POST /v1/ingest"
            }
        )
    except Exception as e:
        await update_session_status(db=db, session=session, new_status=JobStatusEnum.FAILED)
        emit_event(
            "ingest.failure",
            {
                "session_id": str(session_id),
                "user_id": str(user_id) if user_id else None,
                "reason": str(e),
                "error_type": type(e).__name__,
                "status": "ERROR",
                "route": "POST /v1/ingest"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed ot injest resume"
        ) from e

    return {
        "session_id": str(session.id),
        "status": session.status,
        "links": {
            "session": f"api/v1/sessions/{session.id}"
        },
    }


@injest_router.get("/sessions/{session_id}", status_code=status.HTTP_200_OK)
async def get_injest_resume(session_id: uuid.UUID | str, db=Depends(get_db_sqlalchemy)):
    session = await get_session(
        db=db, session_id=session_id
    )

    if session is None:
        emit_event(
            "sessions.get.not_found",
            {
                "session_id": str(session_id),
                "status": "WARNING",
                "route": "GET /v1/sessions/{session_id}"
            }
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )

    emit_event(
        "sessions.get.success",
        {
            "session_id": str(session.id),
            "session_status": session.status,
            "status": "INFO",
            "route": "GET /v1/sessions/{session_id}"
        }
    )

    return {
        "session_id": str(session.id),
        "status": session.status,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


