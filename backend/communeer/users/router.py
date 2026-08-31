import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from communeer.deps import get_current_user, get_db, require_role
from communeer.models import User, UserRole
from communeer.users.schemas import (
    CreateUserIn,
    ManagedUserOut,
    ResetPasswordIn,
    UpdateUserIn,
)
from communeer.users.service import (
    create_user,
    list_users,
    reset_user_password,
    update_user,
)

# Owner-only, no exceptions — managing who else can access the dashboard
# (including granting/revoking owner/admin access) is the one area where even
# `admin` shouldn't have write access, unlike moderation/renewals/sync.
router = APIRouter(tags=["users"], dependencies=[Depends(require_role(UserRole.owner))])


@router.get("/users", response_model=list[ManagedUserOut])
def list_users_route(db: Session = Depends(get_db)) -> list[User]:
    return list_users(db)


@router.post("/users", response_model=ManagedUserOut, status_code=status.HTTP_201_CREATED)
def create_user_route(
    body: CreateUserIn,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> User:
    return create_user(db, username=body.username, password=body.password, role=body.role, actor_user_id=actor.id)


@router.patch("/users/{user_id}", response_model=ManagedUserOut)
def update_user_route(
    user_id: uuid.UUID,
    body: UpdateUserIn,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> User:
    return update_user(db, user_id, role=body.role, is_active=body.is_active, actor_user_id=actor.id)


@router.post("/users/{user_id}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_user_password_route(
    user_id: uuid.UUID,
    body: ResetPasswordIn,
    db: Session = Depends(get_db),
    actor: User = Depends(get_current_user),
) -> None:
    reset_user_password(db, user_id, new_password=body.password, actor_user_id=actor.id)
