from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
from uuid import UUID

class UserPublicSchema(BaseModel):
    id: UUID | str
    firebase_uid: str
    display_name: Optional[str]
    email: Optional[str]
    photo_url: Optional[str]
    role: str
    is_anonymous: bool
    user_metadata: Optional[Any]
    created_at: Optional[datetime]
    last_login_at: Optional[datetime]

    class Config:
        orm_mode = True      # allows to return ORM objects

'''
User
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    firebase_uid = Column(String, index = True,nullable=False)
    email = Column(String,index=True )
    display_name = Column(String)
    photo_url = Column(String)
    is_anonymous = Column(Boolean, default=False)
    role = Column(String, default='user')
    user_metadata=Column(JSONB)
    created_at = Column(DateTime, default=func.now())
    last_login_at=Column(DateTime, default=func.now(), onupdate=func.now())

'''