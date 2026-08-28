import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from communeer.communities.router import get_community_or_404
from communeer.communities.schemas import CommunityDetailOut
from communeer.communities.service import (
    get_community_admin_count,
    get_community_pending_request_count,
)
from communeer.deps import get_current_user, get_db, get_provider
from communeer.errors import bad_request
from communeer.models import User
from communeer.providers.whatsapp.base import WhatsAppProvider
from communeer.sync.service import CommunityNotFoundError, sync_community

router = APIRouter(tags=["sync"], dependencies=[Depends(get_current_user)])


@router.post("/communities/{community_id}/sync")
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
