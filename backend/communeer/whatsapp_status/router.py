"""Session-lifecycle endpoints (not per-community data sync — that's
`sync/router.py`). The frontend polls `/whatsapp/status` alone; it never
needs to know which provider is active behind it.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from communeer.communities.router import _summary
from communeer.communities.schemas import CommunitySummaryOut
from communeer.deps import get_current_user, get_db, get_provider, require_role
from communeer.errors import bad_request, conflict, service_unavailable
from communeer.models import User, UserRole
from communeer.providers.whatsapp.base import (
    WhatsAppNotConnectedError,
    WhatsAppProvider,
    WhatsAppProviderUnavailableError,
)
from communeer.providers.whatsapp.wppconnect import WppconnectProvider
from communeer.sync.service import SyncInProgressError, sync_community
from communeer.whatsapp_status.schemas import WhatsAppStatusOut

router = APIRouter(tags=["whatsapp"], dependencies=[Depends(get_current_user)])


@router.get("/whatsapp/status", response_model=WhatsAppStatusOut)
def get_whatsapp_status(provider: WhatsAppProvider = Depends(get_provider)) -> WhatsAppStatusOut:
    connection_status = provider.get_connection_status()
    return WhatsAppStatusOut(
        state=connection_status.state,
        qr_code_data_url=connection_status.qr_code_data_url,
        detail=connection_status.detail,
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


@router.post(
    "/whatsapp/discover-and-sync",
    response_model=list[CommunitySummaryOut],
    dependencies=[Depends(require_role(UserRole.owner, UserRole.admin))],
)
def discover_and_sync(
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(get_current_user),
) -> list[CommunitySummaryOut]:
    try:
        provider_communities = provider.get_communities()
        synced = [
            sync_community(
                db,
                provider,
                provider_community.wa_id,
                actor_user_id=user.id,
                provider_community=provider_community,
            )
            for provider_community in provider_communities
        ]
    except WhatsAppNotConnectedError as exc:
        raise bad_request(f"WhatsApp is not connected (state={exc!s}).") from exc
    except WhatsAppProviderUnavailableError as exc:
        raise service_unavailable("WhatsApp service is unreachable right now. Please try again shortly.") from exc
    except SyncInProgressError as exc:
        raise conflict("A sync for this community is already in progress — please try again shortly.") from exc

    return [_summary(db, community) for community in synced]
