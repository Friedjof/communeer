import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from communeer.communities.router import get_community_or_404
from communeer.communities.schemas import CommunityDetailOut
from communeer.communities.service import (
    get_community_admin_count,
    get_community_pending_request_count,
)
from communeer.deps import (
    get_current_user,
    get_db,
    get_provider,
    require_community_access,
    require_role,
)
from communeer.errors import bad_request, conflict, service_unavailable
from communeer.models import User, UserRole
from communeer.providers.whatsapp.base import (
    WhatsAppProvider,
    WhatsAppProviderUnavailableError,
)
from communeer.sync.service import (
    CommunityNotFoundError,
    SyncInProgressError,
    sync_community,
)

router = APIRouter(tags=["sync"], dependencies=[Depends(get_current_user)])


@router.post(
    "/communities/{community_id}/sync",
    # `group_admin` may trigger a sync of a community containing their own
    # group: sync is idempotent/read-only from WhatsApp's perspective (it
    # only refreshes the local mirror), already guarded against concurrent
    # runs (`SyncInProgressError`), and reveals nothing new through the API
    # that isn't separately scoped by every route that actually *returns*
    # data — a community-wide sync touching sibling groups' rows in the DB
    # doesn't let them see anything through a response they couldn't
    # already reach.
    dependencies=[
        Depends(require_role(UserRole.owner, UserRole.admin, UserRole.group_admin)),
        Depends(require_community_access()),
    ],
)
def sync_community_route(
    community_id: uuid.UUID,
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    user: User = Depends(get_current_user),
) -> Response:
    community = get_community_or_404(db, community_id)
    try:
        synced = sync_community(db, provider, community.wa_id, actor_user_id=user.id)
    except CommunityNotFoundError as exc:
        raise bad_request(f"Provider has no community with wa_id={exc!s}") from exc
    except WhatsAppProviderUnavailableError as exc:
        raise service_unavailable("WhatsApp service is unreachable right now. Please try again shortly.") from exc
    except SyncInProgressError as exc:
        raise conflict("A sync for this community is already in progress — please try again shortly.") from exc

    out = CommunityDetailOut(
        id=synced.id,
        wa_id=synced.wa_id,
        name=synced.name,
        picture_url=synced.picture_url,
        member_count=synced.member_count,
        group_count=synced.group_count,
        admin_count=get_community_admin_count(db, synced.id),
        pending_request_count=get_community_pending_request_count(db, synced.id),
        last_synced_at=synced.last_synced_at,
        description=synced.description,
        announcement_group_wa_id=synced.announcement_group_wa_id,
    )
    return Response(content=out.model_dump_json(by_alias=True), media_type="application/json")
