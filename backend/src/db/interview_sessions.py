from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey, Text
from .users import Base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
import enum
from typing import Optional
from datetime import datetime


class InterviewStatusEnum(str, enum.Enum):
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABANDONED = "ABANDONED"


class InterviewSessions(Base):
    __tablename__ = "InterviewSessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('Users.id'), nullable=False, index=True)
    resume_session_id = Column(UUID(as_uuid=True), ForeignKey('Sessions.id'), nullable=False, index=True)

    status = Column(String, default=InterviewStatusEnum.IN_PROGRESS.value, nullable=False, index=True)
    job_description = Column(Text, nullable=False)

    turn_count = Column(Integer, default=0, nullable=False)
    # Snapshotted from config at creation time (not re-read from config on
    # every turn) so a later env-var change never retroactively changes the
    # cap an in-flight interview is being held to.
    max_turns = Column(Integer, nullable=False)

    transcript_blob_path: Optional[str] = Column(Text, nullable=True)

    score: Optional[int] = Column(Integer, nullable=True)
    strengths: Optional[list] = Column(JSONB, nullable=True)
    weaknesses: Optional[list] = Column(JSONB, nullable=True)
    next_steps: Optional[list] = Column(JSONB, nullable=True)

    started_at = Column(DateTime, default=func.now())
    completed_at: Optional[datetime] = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    error_code: Optional[str] = Column(String(50), nullable=True)
    error_message: Optional[str] = Column(Text, nullable=True)

    user = relationship("Users", backref="InterviewSessions")
    resume_session = relationship("Sessions", backref="InterviewSessions")

    def __repr__(self):
        return f"<InterviewSessions(id='{self.id}', status='{self.status}', user_id='{self.user_id}')>"
