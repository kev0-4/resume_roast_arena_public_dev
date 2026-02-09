

from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID
from typing import Dict, List, Any, Optional


class AnonymizationJobMessage(BaseModel):
    """
    Message consumed by anonymization worker.
    """

    version: str = Field(..., example="1.0")
    job_type: str = Field(..., example="Anonymization")

    session_id: UUID

    normalized_blob_path: str = Field(
        ...,
        example="normalized/<session_id>/normalized.json"
    )

    attempt: int = Field(default=1, ge=1)
    created_at: datetime


class Span(BaseModel):
    start: int
    end: int


class RedactionEntry(BaseModel):
    """
    Records one redaction event.
    """
    placeholder: str
    original_span: Span


class AnonymizedContent(BaseModel):
    """
    Redacted resume content.
    """
    blocks: Dict[str, List[dict]]


class Redactions(BaseModel):
    """
    All redactions performed in this session.
    """
    emails: List[RedactionEntry] = []
    phones: List[RedactionEntry] = []
    urls: List[RedactionEntry] = []
    # v2:
    names: Optional[list[RedactionEntry] | str] = None
    organizations: Optional[list[RedactionEntry] | str] = None


class AnonymizedArtifact(BaseModel):
    """
    Final anonymized resume artifact.
    """

    session_id: UUID
    anonymization_version: str = "1.0"

    content: AnonymizedContent
    redactions: Redactions

    signals: Dict[str, bool]
    metrics: Dict[str, Any]

    timestamps: Dict[str, datetime]


'''
example structure of anonymized json
{}
  "session_id": "b984f720-40bc-4ff5-a2bd-fc8738460061",
  "anonymization_version": "1.0",
  "content": {
    "blocks": {
      "experience": [
        {
          "text": "Worked at {{ORG_1}} from {{YEAR_1}} to {{YEAR_2}}",
          "source_span": { "start": 196, "end": 1066 }
        }
      ]
    }
  },
  "redactions": {
    "phones": [
      {
        "placeholder": "{{PHONE_1}}",
        "original_span": { "start": 14, "end": 28 }
      }
    ]
  },
  "signals": { "...": true },
  "metrics": { "...": 123 },
  "timestamps": {
    "normalized_at": "2026-02-07T21:11:09Z",
    "anonymized_at": "2026-02-07T21:12:01Z"
  }
}
'''
