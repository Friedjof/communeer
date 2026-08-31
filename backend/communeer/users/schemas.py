import uuid
from datetime import datetime

from pydantic import Field

from communeer.models import UserRole
from communeer.schemas import CamelModel


class ManagedUserOut(CamelModel):
    id: uuid.UUID
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime


class CreateUserIn(CamelModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8)
    role: UserRole


class UpdateUserIn(CamelModel):
    role: UserRole | None = None
    is_active: bool | None = None


class ResetPasswordIn(CamelModel):
    password: str = Field(min_length=8)
