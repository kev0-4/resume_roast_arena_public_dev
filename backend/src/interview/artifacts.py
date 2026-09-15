"""
backend/src/interview/artifacts.py

Blob reads for the interview feature: the resume artifacts an interview is
built from, and the transcript it accumulates while it runs.

These lived in routes/interview.py until the cleanup worker needed them
too. service.py deliberately owns only the database (see its docstring), so
blob I/O gets its own module rather than being folded in there.

Privacy invariant, same as everywhere else in this feature: only the
ANONYMIZED resume artifact is ever read, never the raw upload.
"""

import asyncio
import json

from ..db.interview_sessions import InterviewSessions
from ..services.blob import read_blob


async def load_resume_context(resume_session_id) -> tuple[dict, dict]:
    """Reads anonymized.json + roast.json for a resume session concurrently."""
    anonymized_path = f"anonymized/{resume_session_id}/anonymized.json"
    roast_path = f"roast/{resume_session_id}/roast.json"

    async def _read_json(blob_path: str) -> dict:
        raw = await asyncio.to_thread(read_blob, blob_path)
        return json.loads(raw)

    anonymized, roast = await asyncio.gather(_read_json(anonymized_path), _read_json(roast_path))
    return anonymized, roast


async def read_transcript(interview: InterviewSessions) -> list[dict]:
    if not interview.transcript_blob_path:
        return []
    raw = await asyncio.to_thread(read_blob, interview.transcript_blob_path)
    return json.loads(raw)
