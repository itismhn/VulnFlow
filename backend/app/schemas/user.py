from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import Role
from app.schemas.common import ORM


class NetworkRef(ORM):
    id: int
    name: str


class UserOut(ORM):
    id: int
    username: str
    email: str
    full_name: str
    role: Role
    is_active: bool
    must_change_password: bool
    scope_restricted: bool
    networks: list[NetworkRef]
    last_login_at: datetime | None
    locked_until: datetime | None
    created_at: datetime


class MeOut(UserOut):
    permissions: list[str]


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    email: EmailStr
    full_name: str = Field(default="", max_length=128)
    role: Role = Role.VIEWER
    password: str
    scope_restricted: bool = False
    network_ids: list[int] = []


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    full_name: str | None = Field(default=None, max_length=128)
    role: Role | None = None
    is_active: bool | None = None
    scope_restricted: bool | None = None
    network_ids: list[int] | None = None


class PasswordReset(BaseModel):
    password: str


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str
