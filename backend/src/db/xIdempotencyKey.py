from sqlalchemy import Column, Integer, String, DateTime, func, Boolean, UniqueConstraint, ForeignKey, Enum, Text, URL
from .users import Base
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import uuid

class xIdempotencyKey(Base):
    __tablename__ = "IdempotencyKeys"

    id = Column(UUID(as_uuid= True), primary_key=True,default = uuid.uuid4)
    key = Column(Text, nullable = False, index = True)
    user_id = Column(UUID(as_uuid=True),ForeignKey("Users.id"), nullable=True, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey('Sessions.id'), nullable=False, index=True)
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime, nullable=True)

    user = relationship("Users", backref="idempotency_keys")
    session = relationship("Sessions", backref="idempotency_keys")
    
    __table_args__ = (
        UniqueConstraint('key', 'user_id', name='uq_key_user'),
    )

    def __repr__(self):
        return f"<IdempotencyKey(id='{self.id}', key='{self.key}', user_id='{self.user_id}', session_id='{self.session_id}')>"