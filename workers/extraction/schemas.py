from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal
import uuid
class ExtractionJobMessage(BaseModel):
    version: str = Field(default="1.0")
    job_type: Literal["Extraction"] = Field(default="Extraction")
    session_id: str|uuid.UUID
    raw_blob_path: str
    attempt: int
    created_at: datetime | str

class ExtractionMetadata(BaseModel):
    MessageId : str|uuid.UUID
    correlationId : str|uuid.UUID 