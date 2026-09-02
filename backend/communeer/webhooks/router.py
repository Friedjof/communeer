"""Inbound webhook receiver for WPPConnect Server events.

WPPConnect Server supports webhooks unconditionally via the `WEBHOOK_URL` env
var (see `docker-compose.yml`'s `wppconnect` service): on every event it
cares about, it POSTs `{"event": "<name>", "session": "...", ...the raw
wa-js event object's own fields merged flat at the top level}`. Confirmed
against `wppconnect-server`'s own `callWebHook` helper:
`data = Object.assign({event, session}, data)` — no nesting, the event
payload's fields sit directly alongside `event`/`session`. This module
relies on that flat shape for every event handled below:

- `onmessage`: `data` is the raw wa-js `Message` object as-is (`type`,
  `body`, `t`, `fromMe`, `from`/`chatId` (the chat), `author` (the sending
  participant, present only for group messages) — same field names
  `providers/whatsapp/wppconnect.py`'s own `_fetch_last_message_by_author`
  already reads from `get-messages`, just not pre-scoped to one group here).
- `onreactionmessage`: `data` is wa-js's raw reaction object — `{id, msgId,
  reactionText, read, sender, orphan, orphanReason, timestamp}` — where
  `msgId` is a `MsgKey`-shaped object (`{fromMe, remote, id, participant,
  _serialized}`) and `.remote` is the chat/group JID the reacted-to message
  belongs to (this is how a reaction, whose own fields carry no chat id, is
  matched to the right group).
- `onparticipantschanged`: `data`'s exact shape isn't pinned down anywhere in
  WPPConnect's own source (typed `any` end to end) — handled defensively by
  probing a few plausible id fields rather than assuming one.

Not behind `get_current_user` — this is a server-to-server call from the
`wppconnect` container, not a browser request. Instead, a shared secret is
threaded into the URL path itself (`Settings.webhook_secret`, wired the same
way `WPPCONNECT_SECRET_KEY` already is) and compared here. A wrong or
missing secret returns 404, not 401: there must be no observable difference
from "this route doesn't exist" for an outside caller probing the API.

`last_seen_at` / `ActivityType.view`: intentionally never touched by this
module. There is no WPPConnect/wa-js event for "someone else read a
message" (`onAck` only ever covers the connected account's own outgoing
messages) — see `models/membership.py`'s `ActivityType` docstring for the
same honest-non-availability posture already established for `last_seen_at`.

`onmessage` additionally inserts a `GroupMessage` history row (see
`models/message.py`) alongside the existing `last_activity_*` stamping —
idempotent on `(group_id, wa_message_id)` since WPPConnect makes no
delivery-once guarantee. `onreactionmessage` never writes to that table
(reactions aren't message history, see that handler below).
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from communeer.config import Settings, get_settings
from communeer.deps import get_db, get_provider
from communeer.errors import not_found
from communeer.models import (
    ActivityType,
    Group,
    GroupMembership,
    GroupMessage,
    Member,
    MessageType,
)
from communeer.providers.whatsapp.base import (
    WhatsAppProvider,
    WhatsAppProviderUnavailableError,
)
from communeer.providers.whatsapp.wppconnect import WppconnectProvider
from communeer.renewals.service import (
    RENEWAL_CONFIRM_REACTION,
    RENEWAL_DECLINE_REACTION,
    apply_renewal_confirm_reaction,
    apply_renewal_decline_reaction,
)
from communeer.sync.service import (
    CommunityNotFoundError,
    SyncInProgressError,
    _as_utc,
    sync_community,
)

logger = logging.getLogger("communeer.webhooks")

router = APIRouter(tags=["webhooks"])

_ACTIVITY_CONTENT_MAX_LEN = 200

# `onmessage` payload `type` values this module stores message history for.
# Everything outside this union (`fromMe`'s own filter aside) is left
# ignored exactly as before this table existed — an unconfirmed/unrecognized
# `type` (e.g. a group-system notice) is skipped rather than guessed at.
_TEXT_MESSAGE_TYPES = {"chat"}
_MEDIA_MESSAGE_TYPES = {"image", "video", "audio", "ptt", "document", "sticker", "location", "vcard"}
_MEDIA_PLACEHOLDER = "[media message]"


def _jid(value: object) -> str | None:
    """Normalize a WPPConnect JID-ish field. Reuses
    `WppconnectProvider._jid_str` (a `@staticmethod`, safe to call without an
    instance) rather than duplicating it — see that module's own docstring
    for why this is needed: JID fields are inconsistently a plain string vs.
    a `{"server", "user", "_serialized"}` object depending on
    endpoint/event."""
    return WppconnectProvider._jid_str(value)


def _truncate(text: str | None, limit: int = _ACTIVITY_CONTENT_MAX_LEN) -> str | None:
    if text is None:
        return None
    return text if len(text) <= limit else text[:limit]


def _to_datetime(raw: Any) -> datetime | None:
    if not isinstance(raw, (int, float)):
        return None
    return datetime.fromtimestamp(raw, tz=UTC)


def _find_membership(db: Session, group_wa_id: str | None, member_wa_id: str | None) -> GroupMembership | None:
    if not group_wa_id or not member_wa_id:
        return None
    return db.execute(
        select(GroupMembership)
        .join(Group, Group.id == GroupMembership.group_id)
        .join(Member, Member.id == GroupMembership.member_id)
        .where(Group.wa_id == group_wa_id, Member.wa_id == member_wa_id)
    ).scalar_one_or_none()


def _find_memberships_by_member_wa_id(db: Session, member_wa_id: str) -> list[GroupMembership]:
    return list(
        db.execute(
            select(GroupMembership).join(Member, Member.id == GroupMembership.member_id).where(
                Member.wa_id == member_wa_id
            )
        ).scalars()
    )


def _handle_onmessage(db: Session, payload: dict[str, Any]) -> None:
    message_type_raw = payload.get("type")
    if payload.get("fromMe") or message_type_raw not in (_TEXT_MESSAGE_TYPES | _MEDIA_MESSAGE_TYPES):
        return

    group_wa_id = _jid(payload.get("chatId")) or _jid(payload.get("from"))
    author_wa_id = _jid(payload.get("author"))
    if not group_wa_id or not author_wa_id:
        # No `author` field at all means this wasn't a group message (a DM
        # has no participant distinct from the chat itself) — GroupMembership
        # only exists for group members, nothing to stamp.
        return

    membership = _find_membership(db, group_wa_id, author_wa_id)
    if membership is None:
        # A message from a group/member Communeer hasn't synced yet — a
        # normal, non-error condition for a live webhook, not a bug.
        return

    timestamp = _to_datetime(payload.get("t"))
    if timestamp is None:
        return
    body = payload.get("body")
    is_text = message_type_raw in _TEXT_MESSAGE_TYPES
    raw_content = body if isinstance(body, str) and body else None
    content = _truncate(raw_content)

    changed = False
    # `last_message_at`: the same forward-only field `sync_community`
    # already maintains (needed by `get_renewal_suggestions`'s "never
    # posted first" sort, unchanged here) — advanced live so a fresh message
    # doesn't require a manual "Sync now" to show up.
    if _as_utc(membership.last_message_at) is None or timestamp > _as_utc(membership.last_message_at):
        membership.last_message_at = timestamp
        changed = True

    # Unified "last activity" — a separate forward-only comparison against
    # `last_activity_at` specifically, since a later reaction could in
    # principle advance that field past this message's timestamp without
    # `last_message_at` moving.
    if _as_utc(membership.last_activity_at) is None or timestamp > _as_utc(membership.last_activity_at):
        membership.last_activity_type = ActivityType.message
        membership.last_activity_at = timestamp
        membership.last_activity_content = content
        changed = True

    # Message-history insert: independent of the forward-only stamping above
    # (an out-of-order delivery that doesn't advance `last_activity_at` still
    # gets its own history row) and idempotent on `(group_id, wa_message_id)`
    # since WPPConnect makes no delivery-once guarantee for webhooks.
    wa_message_id = _extract_wa_message_id(payload.get("id"))
    if wa_message_id is not None:
        already_stored = db.execute(
            select(GroupMessage.id).where(
                GroupMessage.group_id == membership.group_id,
                GroupMessage.wa_message_id == wa_message_id,
            )
        ).scalar_one_or_none()
        if already_stored is None:
            db.add(
                GroupMessage(
                    group_id=membership.group_id,
                    member_id=membership.member_id,
                    wa_message_id=wa_message_id,
                    message_type=MessageType.text if is_text else MessageType.media,
                    content=raw_content if is_text else (raw_content or _MEDIA_PLACEHOLDER),
                    sent_at=timestamp,
                    raw_metadata=payload,
                )
            )
            changed = True

    if changed:
        db.commit()


def _extract_wa_message_id(msg_id: Any) -> str | None:
    """The id of a message, in whichever shape it arrived in — a plain
    string (`onmessage`'s own `id` field) or the `{fromMe, remote, id,
    participant, _serialized}` `MsgKey`-shaped dict wa-js uses elsewhere
    (`onreactionmessage`'s `msgId`, referencing the *reacted-to* message).
    Used both to store message history (`_handle_onmessage`) and to
    correlate a ❌ reaction back to a renewal reminder DM (see
    `renewals/service.py`) via `_handle_onreactionmessage`."""
    if isinstance(msg_id, str) and msg_id:
        return msg_id
    if not isinstance(msg_id, dict):
        return None
    serialized = msg_id.get("_serialized")
    if isinstance(serialized, str) and serialized:
        return serialized
    raw_id = msg_id.get("id")
    return raw_id if isinstance(raw_id, str) and raw_id else None


def _handle_onreactionmessage(db: Session, payload: dict[str, Any]) -> None:
    msg_id = payload.get("msgId")
    reaction_text = payload.get("reactionText")
    reacted_message_id = _extract_wa_message_id(msg_id)
    # A renewal reminder is a direct message, not a group message — no
    # group/membership matching applies to it, so this short-circuits before
    # (and independent of) the group-activity logic below. If no confirmation
    # matches, this reaction has nothing to do with a renewal (e.g. a plain
    # 👍/❌ on a group message) — fall through as normal.
    if reacted_message_id and reaction_text == RENEWAL_CONFIRM_REACTION and apply_renewal_confirm_reaction(
        db, reacted_message_id
    ):
        return
    if (
        reacted_message_id
        and reaction_text == RENEWAL_DECLINE_REACTION
        and apply_renewal_decline_reaction(db, reacted_message_id)
    ):
        return

    sender_wa_id = _jid(payload.get("sender"))
    if not sender_wa_id:
        return

    group_wa_id = _jid(msg_id.get("remote")) if isinstance(msg_id, dict) else None

    if group_wa_id:
        membership = _find_membership(db, group_wa_id, sender_wa_id)
    else:
        # No usable group id on this payload (unexpected shape) — fall back
        # to an unambiguous match only: if this member belongs to exactly
        # one group anywhere, that's safe; more than one and we'd be
        # guessing which group the reaction actually happened in, so no-op
        # instead of writing possibly-wrong data.
        candidates = _find_memberships_by_member_wa_id(db, sender_wa_id)
        membership = candidates[0] if len(candidates) == 1 else None
        if len(candidates) > 1:
            logger.warning(
                "onreactionmessage: no usable group id on payload and sender %s has "
                "multiple memberships — skipping rather than guessing.",
                sender_wa_id,
            )

    if membership is None:
        return

    timestamp = _to_datetime(payload.get("timestamp"))
    if timestamp is None:
        return
    reaction_text = payload.get("reactionText")
    content = reaction_text if isinstance(reaction_text, str) else None

    # Forward-only, and deliberately does NOT touch `last_message_at` — a
    # reaction is a weaker signal than an actual message and must not affect
    # the renewal "never posted first" sort.
    if _as_utc(membership.last_activity_at) is None or timestamp > _as_utc(membership.last_activity_at):
        membership.last_activity_type = ActivityType.reaction
        membership.last_activity_at = timestamp
        membership.last_activity_content = content
        db.commit()


def _handle_onparticipantschanged(db: Session, provider: WhatsAppProvider, payload: dict[str, Any]) -> None:
    group_wa_id = _jid(payload.get("chatId")) or _jid(payload.get("from")) or _jid(payload.get("id"))
    if not group_wa_id:
        return

    group = db.execute(select(Group).where(Group.wa_id == group_wa_id)).scalar_one_or_none()
    if group is None:
        return

    community = group.community
    try:
        sync_community(db, provider, community.wa_id)
    except CommunityNotFoundError:
        logger.warning(
            "onparticipantschanged: provider no longer reports community %s — skipping resync.",
            community.wa_id,
        )
    except WhatsAppProviderUnavailableError:
        # Fire-and-forget server-to-server call, not a browser request — log
        # and move on rather than crashing the whole webhook request with a
        # 500 over a transient WPPConnect failure.
        logger.warning(
            "onparticipantschanged: WhatsApp provider unavailable while resyncing community %s — skipping.",
            community.wa_id,
        )
    except SyncInProgressError:
        logger.warning(
            "onparticipantschanged: a sync for community %s is already in progress — skipping.",
            community.wa_id,
        )


@router.post("/webhooks/wppconnect/{secret}")
def wppconnect_webhook(
    secret: str,
    payload: dict[str, Any],
    db: Session = Depends(get_db),
    provider: WhatsAppProvider = Depends(get_provider),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not settings.webhook_secret or secret != settings.webhook_secret:
        # 404, not 401: no signal to an outside caller that this route
        # exists at all.
        raise not_found()

    event = payload.get("event")
    if event == "onmessage":
        _handle_onmessage(db, payload)
    elif event == "onreactionmessage":
        _handle_onreactionmessage(db, payload)
    elif event == "onparticipantschanged":
        _handle_onparticipantschanged(db, provider, payload)
    # any other/unrecognized event: no-op, still 200 below.

    return {"ok": True}
