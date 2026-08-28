from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from communeer.auth.schemas import LoginRequest, UserOut
from communeer.auth.security import create_session_token
from communeer.auth.service import authenticate, record_auth_event
from communeer.config import Settings, get_settings
from communeer.deps import get_current_user, get_db
from communeer.errors import unauthorized
from communeer.models import User

router = APIRouter(tags=["auth"])


def _set_session_cookie(response: Response, settings: Settings, user: User) -> None:
    token = create_session_token(user.id)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


@router.post("/auth/login", response_model=UserOut)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    user = authenticate(db, payload.username, payload.password)
    if user is None:
        record_auth_event(db, action="auth.login_failed", detail={"username": payload.username})
        raise unauthorized("Invalid username or password.")

    record_auth_event(db, action="auth.login", actor_user_id=user.id)
    _set_session_cookie(response, settings, user)
    return user


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> None:
    record_auth_event(db, action="auth.logout", actor_user_id=user.id)
    response.delete_cookie(key=settings.session_cookie_name, path="/")


@router.get("/session", response_model=UserOut)
def session(user: User = Depends(get_current_user)) -> User:
    return user
