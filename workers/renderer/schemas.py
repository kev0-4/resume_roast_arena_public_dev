"""
workers/renderer/schemas.py

Contract layer for the renderer worker.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID


class RenderJobMessage(BaseModel):
    version: str = Field(default="1.0")
    job_type: str = Field(default="Render")

    session_id: UUID
    scored_blob_path: str
    roast_blob_path: str

    attempt: int = 1
    created_at: datetime
