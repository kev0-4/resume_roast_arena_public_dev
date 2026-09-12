"""
backend/src/interview/audio_validation.py

Validates a recorded-answer audio upload for the interview turn route --
mirrors backend/src/utils/file_validation.py's validate_upload exactly.

MIME whitelist covers what MediaRecorder actually produces in practice:
Chrome/Firefox default to audio/webm (opus codec), Safari to audio/mp4
(AAC). Neither this list nor real cross-browser MediaRecorder behavior has
been exercised against the live Gemini audio-input endpoint yet -- flagged
as an open risk in the implementation plan (browser format variance),
worth re-checking once the frontend half is built and tested for real.
"""

from fastapi import UploadFile
from fastapi.exceptions import HTTPException
from starlette import status

ALLOWED_AUDIO_MIME_TYPES = {
    "audio/webm",
    "audio/webm;codecs=opus",
    "audio/mp4",
    "audio/mpeg",
    "audio/wav",
    "audio/ogg",
}

MAX_ANSWER_AUDIO_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB -- generous for a ~60-90s answer clip


def validate_answer_audio(file: UploadFile) -> None:
    """Raises HTTPException on failure."""
    if not file:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No audio file provided")

    content_type = (file.content_type or "").split(";")[0].strip()
    full_type = (file.content_type or "").strip()
    if content_type not in {t.split(";")[0] for t in ALLOWED_AUDIO_MIME_TYPES} and full_type not in ALLOWED_AUDIO_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported audio type: {file.content_type}",
        )

    file.file.seek(0, 2)
    size = file.file.tell()
    file.file.seek(0)
    if size == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Audio file is empty")
    if size > MAX_ANSWER_AUDIO_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio too large. Max allowed is {MAX_ANSWER_AUDIO_SIZE_BYTES // (1024 * 1024)} MB",
        )
