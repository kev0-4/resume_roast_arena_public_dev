from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
class NormalizationJobMessage(BaseModel):
    version: str
    job_type: str
    session_id: UUID | str
    extracted_blob_path: str
    created_at: datetime


class NormalizedOutput(BaseModel):
    session_id: UUID |str
    normalization_version: str
    source: dict
    blocks: dict
    entities: dict
    signals: dict
    metrics: dict
    timestamps: dict
