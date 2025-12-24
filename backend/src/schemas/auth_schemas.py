from pydantic import BaseModel
from typing import Optional
from .user_schema import UserPublicSchema

class FirebaseAuthRequest(BaseModel):
    id_token: Optional[str] = None

class FirebaseAuthResponse(BaseModel):
    user: UserPublicSchema
