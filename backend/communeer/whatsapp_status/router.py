"""Session-lifecycle endpoints (not per-community data sync — that's
`sync/router.py`). The frontend polls `/whatsapp/status` alone; it never
needs to know which provider is active behind it.
"""

import logging
import threading

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from communeer.communities.router import _summary
from communeer.deps import get_current_user, get_db, get_provider, require_role
from communeer.errors import bad_request, conflict, service_unavailable
from communeer.models import Community, User, UserRole
from communeer.providers.whatsapp.base import (
    WhatsAppNotConnectedError,
    WhatsAppProvider,
    WhatsAppProviderUnavailableError,
)
from communeer.providers.whatsapp.wppconnect import WppconnectProvider
from communeer.sync.service import SyncInProgressError, sync_community
from communeer.whatsapp_status.schemas import (
    DiscoverAndSyncFailureOut,
    DiscoverAndSyncResultOut,
    WhatsAppStatusOut,
)

logger = logging.getLogger("communeer.whatsapp_status")

router = APIRouter(tags=["whatsapp"], dependencies=[Depends(get_current_user)])

# `discover_and_sync` below is a single, long-running (per its own frontend
# copy, "a few minutes") synchronous request with no other persisted
# progress signal — a page reload mid-discovery aborts the HTTP request
# client-side, but the plain `def` handler keeps running to completion in
# uvicorn's threadpool regardless (Starlette doesn't cancel sync handlers on
# client disconnect). This module-level flag lets `GET /whatsapp/status`
# (already polled every few seconds) tell a freshly (re)loaded page "a
# discovery is still running" instead of silently losing that state, and
# lets a second concurrent discovery attempt be rejected outright rather
# than racing the first. A plain global + lock is enough: this app runs as
# one single-process `uvicorn` worker (see `backend/Dockerfile`'s CMD), so
# there's no cross-process state to reconcile.
_discovery_lock = threading.Lock()
_discovery_in_progress = False


@router.get("/whatsapp/status", response_model=WhatsAppStatusOut)
def get_whatsapp_status(provider: WhatsAppProvider = Depends(get_provider)) -> WhatsAppStatusOut:
    connection_status = provider.get_connection_status()
    return WhatsAppStatusOut(
        state=connection_status.state,
        qr_code_data_url=connection_status.qr_code_data_url,
        detail=connection_status.detail,
        discovery_in_progress=_discovery_in_progress,
    )


@router.post(
    "/whatsapp/connect",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role(UserRole.owner, UserRole.admin))],
)
def connect_whatsapp(provider: WhatsAppProvider = Depends(get_provider)) -> None:
    if not isinstance(provider, WppconnectProvider):
        raise bad_request("Current provider does not support an explicit connect step.")
    try:
        provider.start_session()
    except WhatsAppProviderUnavailableError as exc:
        raise service_unavailable("WhatsApp service is unreachable right now. Please try again shortly.") from exc


def _discovery_failure_reason(exc: Exception) -> str:
    """A safe, generic, user-facing explanation for a per-community sync
    failure — never `str(exc)` directly (could echo transport internals,
    see `wppconnect.py::_safe_error_detail`'s same reasoning)."""
    if isinstance(exc, WhatsAppProviderUnavailableError):
        return "WhatsApp took too long to respond (large communities are more likely to hit this) — try again."
    if isinstance(exc, SyncInProgressError):
        return "A sync for this community was already in progress."
    return "Sync failed unexpectedly — check the server logs for details."


@router.post(
    "/whatsapp/discover-and-sync",
    response_model=DiscoverAndSyncResultOut,
    dependencies=[Depends(require_role(UserRole.owner, UserRole.admin))],
)
def discover_and_sync(
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(get_current_user),
) -> DiscoverAndSyncResultOut:
    global _discovery_in_progress
    with _discovery_lock:
        if _discovery_in_progress:
            raise conflict("A discovery is already in progress — please wait for it to finish.")
        _discovery_in_progress = True

    try:
        try:
            provider_communities = provider.get_communities()
        except WhatsAppNotConnectedError as exc:
            raise bad_request(f"WhatsApp is not connected (state={exc!s}).") from exc
        except WhatsAppProviderUnavailableError as exc:
            raise service_unavailable("WhatsApp service is unreachable right now. Please try again shortly.") from exc

        # One community's sync failing must not discard every other
        # community's already-committed work (`sync_community` commits per
        # call) — each is isolated in its own try/except so discovery keeps
        # going. `WhatsAppNotConnectedError` is the one exception that still
        # aborts the whole loop immediately: it means the session itself
        # dropped, so every remaining community would fail identically.
        # Anything else caught here (a per-community `WhatsAppProviderUnavailableError`,
        # `SyncInProgressError`, or an unexpected bug) is recorded in
        # `failed` (not just logged) so the caller can actually tell a
        # community was found but didn't make it, instead of it just never
        # appearing anywhere with no explanation.
        synced: list[Community] = []
        failed: list[DiscoverAndSyncFailureOut] = []
        first_error: Exception | None = None
        for provider_community in provider_communities:
            try:
                synced.append(
                    sync_community(
                        db,
                        provider,
                        provider_community.wa_id,
                        actor_user_id=user.id,
                        provider_community=provider_community,
                    )
                )
            except WhatsAppNotConnectedError as exc:
                raise bad_request(f"WhatsApp is not connected (state={exc!s}).") from exc
            except Exception as exc:  # noqa: BLE001 — deliberately broad, see comment above
                db.rollback()
                logger.warning(
                    "Skipping community %s during discovery: %s", provider_community.wa_id, exc
                )
                failed.append(
                    DiscoverAndSyncFailureOut(
                        wa_id=provider_community.wa_id,
                        name=provider_community.name,
                        reason=_discovery_failure_reason(exc),
                    )
                )
                if first_error is None:
                    first_error = exc

        # Same "nothing at all could be synced" escalation as before this
        # response gained a `failed` list: a *partial* failure is reported
        # via `failed` below, but a *total* one still raises the same clean
        # 503/409/500 rather than a technically-200 empty result.
        if not synced and first_error is not None:
            if isinstance(first_error, WhatsAppProviderUnavailableError):
                raise service_unavailable(
                    "WhatsApp service is unreachable right now. Please try again shortly."
                ) from first_error
            if isinstance(first_error, SyncInProgressError):
                raise conflict(
                    "A sync for this community is already in progress — please try again shortly."
                ) from first_error
            raise first_error

        # Same admin-only standing `GET /communities` (communities/router.py)
        # filters on — computed here too so the Setup page can say, right
        # after discovery, "found N, M of them won't show up because this
        # WhatsApp number isn't an admin there" instead of a newly-synced
        # community just silently never appearing.
        admin_wa_ids = provider.get_admin_community_wa_ids()
        hidden_non_admin_wa_ids = (
            [c.wa_id for c in synced if c.wa_id not in admin_wa_ids] if admin_wa_ids is not None else []
        )
    finally:
        _discovery_in_progress = False

    return DiscoverAndSyncResultOut(
        communities=[_summary(db, community) for community in synced],
        hidden_non_admin_wa_ids=hidden_non_admin_wa_ids,
        failed=failed,
    )
