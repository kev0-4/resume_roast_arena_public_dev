from sqlalchemy import Column, Integer,String,DateTime,func, Boolean,UniqueConstraint,ForeignKey,Enum, Text, URL
from .users import Base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid
import enum
from typing import Optional

JOB_STATUSES = (
    "UPLOADED",
    "QUEUED",
    "PROCESSING",
    "FAILED",
    "DONE"
)
#JobStatusEnum = Enum(*JOB_STATUSES, name='job_status')
class JobStatusEnum(str, enum.Enum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    FAILED = "FAILED"
    EXTRACTED = "EXTRACTED"
    DONE = "DONE"
    NORMALIZING = "NORMALIZING"
    NORMALIZED = "NORMALIZED"
class Sessions(Base):
    __tablename__ = "Sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey('Users.id'), nullable=False, index=True)
    status = Column(String, default="UPLOADED", nullable=False, index=True)
    raw_blob_path = Column(Text,nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    user = relationship("Users", backref="Sessions")
    # sanitized_blob_path = Column(Text, nullable=True)
    render_blob_path: Optional[str] = Column(Text, nullable=True)
    error_code: Optional[str] = Column(String(50), nullable=True)
    error_message: Optional[str] = Column(Text, nullable=True)
    # expires_at = Column(DateTime, nullable=True)


    def __repr__(self):
        return f"<Job(id='{self.id}', status='{self.status}', user_id='{self.user_id}')>"

