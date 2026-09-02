from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from communeer.auth.claim_service import complete_claim, request_claim
from communeer.auth.phone import normalize_phone_to_wa_id
from communeer.auth.schemas import (
    ClaimCompleteIn,
    ClaimRequestIn,
    LoginRequest,
    LoginTotpRequiredOut,
    PasswordConfirmIn,
    RecoveryCodesOut,
    TotpEnableIn,
    TotpSetupOut,
    UserOut,
    VerifyTotpIn,
    VerifyWhatsappOtpIn,
    WhatsAppOtpEnableOut,
    WhatsAppOtpSetupIn,
    WhatsAppOtpSetupOut,
)
from communeer.auth.security import (
    PENDING_2FA_MAX_AGE_SECONDS,
    build_totp_uri,
    create_pending_2fa_token,
    create_session_token,
    decrypt_totp_secret,
    encrypt_totp_secret,
    generate_totp_secret,
    read_pending_2fa_token,
    verify_password,
    verify_totp_code,
)
from communeer.auth.service import (
    authenticate_password,
    clear_recovery_codes_if_no_factor_remains,
    disable_whatsapp_otp,
    enable_whatsapp_otp,
    record_auth_event,
    replace_recovery_codes,
    request_whatsapp_otp_login,
    request_whatsapp_otp_setup,
    verify_totp_step,
    verify_whatsapp_otp_login_step,
)
from communeer.config import Settings, get_settings
from communeer.deps import get_current_user, get_db, get_provider
from communeer.errors import bad_request, conflict, unauthorized
from communeer.models import User
from communeer.providers.whatsapp.base import WhatsAppProvider

router = APIRouter(tags=["auth"])

_PENDING_2FA_COOKIE_NAME = "communeer_2fa_pending"


def _set_session_cookie(response: Response, settings: Settings, user: User) -> None:
    token = create_session_token(user.id, user.token_version)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        path="/",
    )


def _set_pending_2fa_cookie(response: Response, settings: Settings, user: User) -> None:
    token = create_pending_2fa_token(user.id)
    response.set_cookie(
        key=_PENDING_2FA_COOKIE_NAME,
        value=token,
        max_age=PENDING_2FA_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=settings.session_cookie_secure,
        # Scoped narrowly to the login sub-flow (prefix-matched, so this
        # still reaches `/auth/login/verify-totp` and
        # `/auth/login/whatsapp-otp/*`) — never sent alongside ordinary
        # authenticated requests.
        path="/api/v1/auth/login",
    )


def _clear_pending_2fa_cookie(response: Response) -> None:
    response.delete_cookie(key=_PENDING_2FA_COOKIE_NAME, path="/api/v1/auth/login")


def _get_pending_2fa_user(request: Request, db: Session) -> User:
    token = request.cookies.get(_PENDING_2FA_COOKIE_NAME)
    if not token:
        raise unauthorized("Log in again to continue.")
    user_id = read_pending_2fa_token(token)
    if user_id is None:
        raise unauthorized("Log in again to continue.")
    user = db.get(User, user_id)
    if user is None or not user.is_active or not (user.totp_enabled or user.whatsapp_otp_enabled):
        raise unauthorized("Log in again to continue.")
    return user


@router.post("/auth/login", response_model=UserOut | LoginTotpRequiredOut)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User | LoginTotpRequiredOut:
    result = authenticate_password(db, payload.username, payload.password, settings)
    if result is None:
        record_auth_event(db, action="auth.login_failed", detail={"username": payload.username[:64]})
        raise unauthorized("Invalid username or password.")

    if result.requires_2fa:
        _set_pending_2fa_cookie(response, settings, result.user)
        return LoginTotpRequiredOut(
            totp_enabled=result.user.totp_enabled,
            whatsapp_otp_enabled=result.user.whatsapp_otp_enabled,
        )

    record_auth_event(db, action="auth.login", actor_user_id=result.user.id)
    _set_session_cookie(response, settings, result.user)
    return result.user


@router.post("/auth/login/verify-totp", response_model=UserOut)
def verify_login_totp(
    payload: VerifyTotpIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    user = _get_pending_2fa_user(request, db)

    if not verify_totp_step(db, user, payload.code, settings):
        record_auth_event(db, action="auth.login_failed", detail={"username": user.username, "step": "totp"})
        raise unauthorized("Invalid code.")

    record_auth_event(db, action="auth.login", actor_user_id=user.id)
    _clear_pending_2fa_cookie(response)
    _set_session_cookie(response, settings, user)
    return user


@router.post("/auth/login/whatsapp-otp/request", status_code=status.HTTP_204_NO_CONTENT)
def request_login_whatsapp_otp(
    request: Request,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
) -> None:
    user = _get_pending_2fa_user(request, db)
    request_whatsapp_otp_login(db, provider, user)


@router.post("/auth/login/whatsapp-otp/verify", response_model=UserOut)
def verify_login_whatsapp_otp(
    payload: VerifyWhatsappOtpIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    user = _get_pending_2fa_user(request, db)

    if not verify_whatsapp_otp_login_step(db, user, payload.code, settings):
        record_auth_event(db, action="auth.login_failed", detail={"username": user.username, "step": "whatsapp_otp"})
        raise unauthorized("Invalid code.")

    record_auth_event(db, action="auth.login", actor_user_id=user.id)
    _clear_pending_2fa_cookie(response)
    _set_session_cookie(response, settings, user)
    return user


@router.post("/auth/claim/request", status_code=status.HTTP_204_NO_CONTENT)
def request_claim_route(
    payload: ClaimRequestIn, db: Session = Depends(get_db), provider: WhatsAppProvider = Depends(get_provider)
) -> None:
    """Unauthenticated — no session/pending-2FA-cookie exists yet at this
    point. Always 204s regardless of outcome (see `request_claim`'s own
    docstring for the account-enumeration reasoning)."""
    request_claim(db, provider, payload.phone_number)


@router.post("/auth/claim/complete", response_model=UserOut)
def complete_claim_route(
    payload: ClaimCompleteIn,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Sets the account's real password (+ optional chosen username) and
    issues a normal session — exactly like a password-only login, since
    `totp_enabled`/`whatsapp_otp_enabled` are both still `False` right after
    claiming. The very next request then hits the same mandatory-2FA gate
    (`deps.get_current_user`) a fresh owner/admin account would, and the
    frontend's existing `/setup/2fa` redirect takes over from there — no new
    2FA-setup UI needed for this flow."""
    user = complete_claim(
        db,
        settings,
        phone_number=payload.phone_number,
        code=payload.code,
        username=payload.username,
        password=payload.password,
    )
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


# ---------------------------------------------------------------------------
# TOTP self-service enrollment/management (any logged-in user, own account)
# ---------------------------------------------------------------------------


@router.post("/auth/2fa/setup", response_model=TotpSetupOut)
def setup_totp(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TotpSetupOut:
    """Generates a new (not-yet-active) secret and stores it encrypted —
    `totp_enabled` only flips to `True` once `/auth/2fa/enable` confirms a
    real code from the authenticator app works. Calling this again before
    confirming just replaces the pending secret (e.g. the user re-scans)."""
    if user.totp_enabled:
        raise conflict("Two-factor authentication is already enabled. Disable it first to set up a new device.")

    secret = generate_totp_secret()
    user.totp_secret_encrypted = encrypt_totp_secret(secret)
    db.commit()

    return TotpSetupOut(secret=secret, otpauth_uri=build_totp_uri(secret, user.username))


@router.post("/auth/2fa/enable", response_model=RecoveryCodesOut)
def enable_totp(
    payload: TotpEnableIn,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> RecoveryCodesOut:
    if user.totp_enabled:
        raise conflict("Two-factor authentication is already enabled.")
    if not user.totp_secret_encrypted:
        raise bad_request("Call /auth/2fa/setup first.")

    secret = decrypt_totp_secret(user.totp_secret_encrypted)
    if secret is None or not verify_totp_code(secret, payload.code):
        raise bad_request("Invalid code. Please try again.")

    user.totp_enabled = True
    user.token_version += 1  # invalidate any other sessions for this account
    codes = replace_recovery_codes(db, user)

    record_auth_event(db, action="auth.totp_enabled", actor_user_id=user.id)
    db.commit()
    # Bumping token_version above would otherwise invalidate the very
    # session cookie this request just authenticated with — reissue it so
    # the user who just enabled 2FA isn't immediately logged out.
    _set_session_cookie(response, settings, user)
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/auth/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_totp(
    payload: PasswordConfirmIn,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> None:
    """Requires the current password (not a TOTP/recovery code) — this must
    still work for a user who has lost their authenticator device and has
    no recovery codes left, as long as they still know their password."""
    if not verify_password(payload.password, user.password_hash):
        raise bad_request("Incorrect password.")

    user.totp_enabled = False
    user.totp_secret_encrypted = None
    user.token_version += 1
    # Only wipes recovery codes if WhatsApp-OTP isn't also enabled — they're
    # a generic backup for "any 2FA factor," not TOTP-specific.
    clear_recovery_codes_if_no_factor_remains(db, user)

    record_auth_event(db, action="auth.totp_disabled", actor_user_id=user.id)
    db.commit()
    # Same reissue-after-bump reasoning as `enable_totp` above.
    _set_session_cookie(response, settings, user)


@router.post("/auth/2fa/recovery-codes/regenerate", response_model=RecoveryCodesOut)
def regenerate_recovery_codes(
    payload: PasswordConfirmIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecoveryCodesOut:
    if not user.totp_enabled:
        raise bad_request("Two-factor authentication is not enabled.")
    if not verify_password(payload.password, user.password_hash):
        raise bad_request("Incorrect password.")

    codes = replace_recovery_codes(db, user)
    record_auth_event(db, action="auth.totp_recovery_codes_regenerated", actor_user_id=user.id)
    db.commit()
    return RecoveryCodesOut(recovery_codes=codes)


# ---------------------------------------------------------------------------
# WhatsApp-OTP self-service enrollment/management (any logged-in user, own
# account) — mirrors the TOTP section above exactly in structure.
# ---------------------------------------------------------------------------


@router.post("/auth/2fa/whatsapp/setup", response_model=WhatsAppOtpSetupOut)
def setup_whatsapp_otp(
    payload: WhatsAppOtpSetupIn,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(get_current_user),
) -> WhatsAppOtpSetupOut:
    """Sends a verification code to the given number and stages it as
    `pending_phone_wa_id` — `whatsapp_otp_enabled` only flips to `True` once
    `/auth/2fa/whatsapp/enable` confirms the code. Calling this again before
    confirming replaces the pending number/code (e.g. the user mistyped it),
    subject to the resend cooldown."""
    phone_wa_id = normalize_phone_to_wa_id(payload.phone_number)
    request_whatsapp_otp_setup(db, provider, user, phone_wa_id)
    return WhatsAppOtpSetupOut(phone_wa_id=phone_wa_id)


@router.post("/auth/2fa/whatsapp/enable", response_model=WhatsAppOtpEnableOut)
def enable_whatsapp_otp_route(
    payload: VerifyWhatsappOtpIn,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> WhatsAppOtpEnableOut:
    codes = enable_whatsapp_otp(db, user, payload.code)

    record_auth_event(db, action="auth.whatsapp_otp_enabled", actor_user_id=user.id)
    # Same reissue-after-token_version-bump reasoning as `enable_totp` above.
    _set_session_cookie(response, settings, user)
    return WhatsAppOtpEnableOut(recovery_codes=codes)


@router.post("/auth/2fa/whatsapp/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_whatsapp_otp_route(
    payload: PasswordConfirmIn,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    user: User = Depends(get_current_user),
) -> None:
    """Password-gated only, same reasoning as `disable_totp`: must still work
    for a user who's lost their phone but knows their password."""
    if not verify_password(payload.password, user.password_hash):
        raise bad_request("Incorrect password.")

    disable_whatsapp_otp(db, user)

    record_auth_event(db, action="auth.whatsapp_otp_disabled", actor_user_id=user.id)
    # Same reissue-after-token_version-bump reasoning as `enable_totp` above.
    _set_session_cookie(response, settings, user)
