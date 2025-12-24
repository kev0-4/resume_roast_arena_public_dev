from fastapi import UploadFile
from fastapi.exceptions import HTTPException
from starlette import status

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def validate_upload(file: UploadFile) -> None:
    """
    Validates uploaded resume file.
    Raises HTTPException on failure.
    """

    if not file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No file provided",
        )

    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file has no filename",
        )

    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type}",
        )

    file.file.seek(0, 2) 
    size = file.file.tell()
    file.file.seek(0)     
    if size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Max allowed is {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB",
        )
