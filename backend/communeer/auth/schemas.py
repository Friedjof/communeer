import uuid

from pydantic import BaseModel

from communeer.models import UserRole
from communeer.schemas import CamelModel


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(CamelModel):
    id: uuid.UUID
    username: str
    role: UserRole
