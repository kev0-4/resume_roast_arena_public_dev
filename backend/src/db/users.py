'''
Base user table schema
- based use this form by importing in other tables
- albemenic env update needed by importing new table 
'''
from sqlalchemy import Column, Integer,String,DateTime,func, Boolean,UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID, JSONB
import uuid

Base = declarative_base()
class Users(Base):
    __tablename__ = "Users"
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
    __table_args__ = (
        UniqueConstraint('firebase_uid'),
    )
