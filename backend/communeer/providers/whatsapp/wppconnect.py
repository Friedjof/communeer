"""Real WhatsApp integration, backed by a `wppconnect-server` instance.

Caching/rate-limit posture (read this before adding a cache): **there is
none, deliberately.** No in-process caching, no TTL, no background polling
loop anywhere in this module. The only rate-limiting boundary is the
caller — `sync_community()` (see `communeer.sync.service`) is invoked only
by an explicit user action (the "Discover communities" / per-community
"Sync now" buttons), never on page load or on a timer. The one exception is
`get_connection_status()`: it's a single cheap `status-session` call with no
side effects, and it is the one method on this provider that's safe for a
caller (e.g. the frontend, via `/whatsapp/status`) to poll frequently.

**Central, explicitly unverified hypothesis** (see
`poc/whatsapp/FINDINGS.md` and the plan this module was built from): the
non-deprecated `POST /api/{session}/list-chats` endpoint (called with
`{"onlyGroups": true}`) embeds, per chat, a `groupMetadata` object carrying
`isParentGroup` / `parentGroup` / `announce` — the fields WhatsApp
"communities" are actually built from under the hood. A prior spike
confirmed a real WPPConnect session works end-to-end, but the test account
had zero groups, so the response was an empty array — inconclusive either
way. If a non-empty `list-chats` response never carries these fields, the
`RuntimeError` raised in `get_communities()` below is the deliberate
tripwire that surfaces that (instead of silently reporting "no
communities", which would be indistinguishable from a real empty account).

**Second verified hypothesis** (admin-only community filter, see
`get_admin_community_wa_ids` below): the connected account's own identity,
in the namespace `group-admins` uses to list a group's admins, is **not**
what `status-session`/`host-device`/`get-phone-number` report (those give
the real phone-number JID, e.g. `4917645790258@c.us`). Confirmed live:
modern WhatsApp accounts are addressed within group rosters via an opaque
`@lid` id instead (e.g. `236794549432473@lid`), and the two never match by
naive string comparison — tested against an account that IS a real admin
of one community, `host-device`'s id was absent from every
`group-admins` result, including that one. The field that actually
bridges the two namespaces: `isMe: true` on the connected account's own
entry within any `group-members` response, whichever namespace its `id`
happens to use — see `_find_own_wa_id` below.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from communeer.config import Settings
from communeer.providers.whatsapp.base import (
    ProviderCommunity,
    ProviderGroup,
    ProviderMember,
    ProviderMembership,
    WhatsAppConnectionState,
    WhatsAppConnectionStatus,
    WhatsAppNotConnectedError,
    WhatsAppProvider,
)

# The endpoint used to list groups. `all-groups` is documented as deprecated
# in favor of `list-chats`, but per the plan's own fast-follow note: if a
# real session shows `list-chats` returning thinner data than `all-groups`
# used to (missing the `ensureGroup` hydration step), swap this one constant.
_LIST_CHATS_PATH_TEMPLATE = "/api/{session}/list-chats"

_STATUS_DISCONNECTED = {None, "CLOSED", "INITIALIZING"}
_STATUS_QRCODE = {"QRCODE"}
_STATUS_CONNECTING = {"CONNECTING", "PAIRING"}
_STATUS_CONNECTED = {"CONNECTED"}

# WhatsApp's own publicly documented platform caps — not derived from any
# WPPConnect field (there isn't one; `groupMetadata.size` is the *current*
# member count, confirmed against real data, not a configured limit). A
# regular group (any subgroup that isn't the announcement group) is capped
# at 1024 participants; a community's announcement group effectively shares
# the community-wide cap (everyone in the community can be a member of it),
# which is 2000 total across every subgroup + the announcement group
# combined. These are current, stable platform constants, not per-account
# settings, so hardcoding them is legitimate — unlike guessing `size` was.
_REGULAR_GROUP_MEMBER_LIMIT = 1024
_ANNOUNCEMENT_GROUP_MEMBER_LIMIT = 2000


def _mask_digits(digits: str) -> str:
    if not digits:
        return ""
    if len(digits) <= 4:
        return f"+{digits}"
    return f"+{digits[:-4]} •••• {digits[-4:]}"


def _mask_phone(jid: str, formatted_name: str | None = None) -> str:
    """Best-effort phone masking, mirroring the visual style `mock.py` uses
    for its synthetic numbers (country-code-ish prefix, masked middle, last
    4 digits visible) — there's no shared helper in this codebase to import,
    so this mirrors the style rather than reusing code.

    Confirmed against real data: newer WhatsApp accounts are addressed by an
    opaque `@lid` id (e.g. `180887295635569@lid`) whose digits are an
    internal identifier, NOT a phone number — extracting "digits" from such
    a JID produces garbage. `group-members`' `formattedName` field carries
    the real, already-human-formatted number for these contacts, so prefer
    it when present; only fall back to parsing the JID for classic `@c.us`
    contacts, which mock.py's own fixtures also model this way.
    """
    if formatted_name:
        digits = "".join(ch for ch in formatted_name if ch.isdigit())
        if digits:
            return _mask_digits(digits)
    digits = "".join(ch for ch in jid.split("@")[0] if ch.isdigit())
    return _mask_digits(digits) if digits else jid


def _format_phone_from_jid(jid: str, formatted_name: str | None = None) -> str:
    """Fallback display name: a human-readable phone number, used when no
    pushname/name field is present on a participant. See `_mask_phone` for
    why `formatted_name` (when present) is preferred over parsing the JID."""
    if formatted_name:
        return formatted_name
    digits = "".join(ch for ch in jid.split("@")[0] if ch.isdigit())
    return f"+{digits}" if digits else jid


def _participant_id(participant: dict) -> str | None:
    """WPPConnect's participant id shape is inconsistent across endpoints
    (seen elsewhere in this codebase's own spike, `poc/whatsapp/explore.py`,
    unwrapping different envelope shapes per endpoint) — try the structured
    `{"_serialized": ...}` form first, then a bare string id field.

    Confirmed against real data: `group-members` nests this under an `"id"`
    key, but `group-admins` (after `_flatten_participant_list`) returns the
    Wid object itself as the participant — i.e. `_serialized` sits at the
    top level, not under `.id`. Check both shapes."""
    top_level_serialized = participant.get("_serialized")
    if isinstance(top_level_serialized, str) and top_level_serialized:
        return top_level_serialized
    raw_id = participant.get("id")
    if isinstance(raw_id, dict):
        serialized = raw_id.get("_serialized")
        if serialized:
            return str(serialized)
    if isinstance(raw_id, str) and raw_id:
        return raw_id
    for key in ("wa_id", "waId"):
        value = participant.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _unwrap_list_response(body: Any) -> list:
    """WPPConnect's own endpoints inconsistently wrap list payloads —
    sometimes a bare list, sometimes `{"status": ..., "response": [...]}`.
    Mirrors the defensive unwrapping `poc/whatsapp/explore.py` already does
    for `all-groups`."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        response = body.get("response")
        if isinstance(response, list):
            return response
    return []


def _flatten_participant_list(items: list) -> list[dict]:
    """`group-admins` was confirmed against a real account to nest its
    result one level deeper than `group-members` does — `{"response":
    [[admin1, admin2, ...]]}` rather than a flat list — even for a single
    group. Flattening defensively handles both shapes (a flat list of dicts
    passes through unchanged) rather than hardcoding the extra nesting only
    for the one endpoint observed to have it."""
    flattened: list[dict] = []
    for item in items:
        if isinstance(item, list):
            flattened.extend(x for x in item if isinstance(x, dict))
        elif isinstance(item, dict):
            flattened.append(item)
    return flattened


class WppconnectProvider(WhatsAppProvider):
    """Talks to a `wppconnect-server` instance over its REST API."""

    def __init__(self, settings: Settings) -> None:
        self._session_name = settings.wppconnect_session_name
        self._secret_key = settings.wppconnect_secret_key
        self._client = httpx.Client(
            base_url=settings.wppconnect_base_url or "",
            timeout=settings.wppconnect_http_timeout_seconds,
        )
        self._token: str | None = None

    # -- session/token plumbing -------------------------------------------

    def _ensure_token(self) -> str:
        resp = self._client.post(
            f"/api/{self._session_name}/{self._secret_key}/generate-token"
        )
        resp.raise_for_status()
        body = resp.json()
        token = body.get("token") or body.get("Token") or body.get("result")
        if not token:
            raise RuntimeError(f"wppconnect generate-token: no token in response: {body!r}")
        self._token = str(token)
        return self._token

    def _authed_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if self._token is None:
            self._ensure_token()

        headers = kwargs.pop("headers", {}) or {}
        headers["Authorization"] = f"Bearer {self._token}"
        resp = self._client.request(method, path, headers=headers, **kwargs)

        if resp.status_code == 401:
            # Token may have expired server-side — regenerate exactly once
            # and retry, rather than looping forever on a persistently bad
            # token/misconfigured secret key.
            self._token = None
            self._ensure_token()
            headers["Authorization"] = f"Bearer {self._token}"
            resp = self._client.request(method, path, headers=headers, **kwargs)

        return resp

    # -- connection status --------------------------------------------------

    def get_connection_status(self) -> WhatsAppConnectionStatus:
        # Contract (see base.py): never raise, no matter what goes wrong.
        try:
            resp = self._authed_request("GET", f"/api/{self._session_name}/status-session")
            resp.raise_for_status()
            body = resp.json()
        except httpx.HTTPError as exc:
            return WhatsAppConnectionStatus(state=WhatsAppConnectionState.error, detail=str(exc))
        except (ValueError, KeyError, TypeError) as exc:
            # Defensive: malformed/non-JSON response body, unexpected shape.
            return WhatsAppConnectionStatus(state=WhatsAppConnectionState.error, detail=str(exc))

        raw_status = body.get("status") if isinstance(body, dict) else None

        if raw_status in _STATUS_DISCONNECTED:
            return WhatsAppConnectionStatus(state=WhatsAppConnectionState.disconnected)
        if raw_status in _STATUS_QRCODE:
            return WhatsAppConnectionStatus(
                state=WhatsAppConnectionState.qr_pending,
                qr_code_data_url=body.get("qrcode"),
            )
        if raw_status in _STATUS_CONNECTING:
            return WhatsAppConnectionStatus(state=WhatsAppConnectionState.connecting)
        if raw_status in _STATUS_CONNECTED:
            return WhatsAppConnectionStatus(state=WhatsAppConnectionState.connected)

        return WhatsAppConnectionStatus(
            state=WhatsAppConnectionState.error,
            detail=f"Unrecognized status-session value: {raw_status!r}",
        )

    def _require_connected(self) -> None:
        status = self.get_connection_status()
        if status.state != WhatsAppConnectionState.connected:
            raise WhatsAppNotConnectedError(status.state.value)

    # -- wppconnect-only extra, not part of the shared ABC -------------------

    def start_session(self) -> None:
        """Kick off (or resume) a WPPConnect session. Not part of
        `WhatsAppProvider` — `MockWhatsAppProvider` has no session concept,
        and a fake no-op on the shared ABC would mask real bugs. The
        `whatsapp_status` router calls this only when it knows (via
        `isinstance`) that it's talking to this concrete provider."""
        resp = self._authed_request(
            "POST",
            f"/api/{self._session_name}/start-session",
            json={"waitQrCode": False},
        )
        resp.raise_for_status()

    # -- group/community listing --------------------------------------------

    def _fetch_groups_raw(self) -> list[dict]:
        resp = self._authed_request(
            "POST",
            _LIST_CHATS_PATH_TEMPLATE.format(session=self._session_name),
            json={"onlyGroups": True},
        )
        resp.raise_for_status()
        return _unwrap_list_response(resp.json())

    @staticmethod
    def _metadata_of(chat: dict) -> dict:
        meta = chat.get("groupMetadata")
        return meta if isinstance(meta, dict) else chat

    @staticmethod
    def _wa_id_of(chat: dict, meta: dict) -> str | None:
        id_field = meta.get("id")
        if isinstance(id_field, dict):
            serialized = id_field.get("_serialized")
            if serialized:
                return str(serialized)
        if isinstance(id_field, str) and id_field:
            return id_field
        top_id = chat.get("id")
        if isinstance(top_id, str) and top_id:
            return top_id
        return None

    @staticmethod
    def _jid_str(value: object) -> str | None:
        """Normalize a WPPConnect JID field to its serialized string form.

        Confirmed against real data: fields like `groupMetadata.parentGroup`
        (and `.id`) come back as a `{"server", "user", "_serialized"}` object,
        not a plain string — a naive `== some_wa_id_string` comparison against
        the raw field silently never matches (this was the actual cause of
        every community showing zero groups)."""
        if isinstance(value, dict):
            serialized = value.get("_serialized")
            return str(serialized) if serialized else None
        if isinstance(value, str) and value:
            return value
        return None

    def _build_group(self, chat: dict) -> ProviderGroup:
        meta = self._metadata_of(chat)
        wa_id = self._wa_id_of(chat, meta)
        name = meta.get("subject") or chat.get("name") or wa_id or "Unnamed group"
        announce = bool(meta.get("announce", False))
        # Confirmed against real data: `groupMetadata.size` is the group's
        # *current* member count, not a configured limit — WPPConnect
        # exposes no field for the actual cap at all. An earlier version of
        # this code guessed `size` here, which made every group render as a
        # false "100% full". WhatsApp's platform limit is a known, stable
        # constant depending on group type (not a guess) — see the module
        # docstring's constants above.
        member_limit = _ANNOUNCEMENT_GROUP_MEMBER_LIMIT if announce else _REGULAR_GROUP_MEMBER_LIMIT

        pending_ids = set()
        for pending in meta.get("pendingParticipants") or []:
            if isinstance(pending, dict):
                pid = _participant_id(pending)
            else:
                pid = pending
            if pid:
                pending_ids.add(pid)

        memberships = self._build_memberships(wa_id, pending_ids) if wa_id else []

        return ProviderGroup(
            wa_id=wa_id or "",
            name=name,
            description=meta.get("desc"),
            picture_url=None,
            is_announcement_group=announce,
            member_limit=member_limit,
            memberships=memberships,
            raw=meta,
        )

    def _build_memberships(self, group_wa_id: str, pending_ids: set[str]) -> list[ProviderMembership]:
        members_resp = self._authed_request(
            "GET", f"/api/{self._session_name}/group-members/{group_wa_id}"
        )
        members_resp.raise_for_status()
        raw_members = _unwrap_list_response(members_resp.json())

        admins_resp = self._authed_request(
            "GET", f"/api/{self._session_name}/group-admins/{group_wa_id}"
        )
        admins_resp.raise_for_status()
        raw_admins = _flatten_participant_list(_unwrap_list_response(admins_resp.json()))
        admin_ids: set[str] = set()
        for admin in raw_admins:
            admin_id = _participant_id(admin)
            if admin_id:
                admin_ids.add(admin_id)

        memberships: list[ProviderMembership] = []
        for participant in raw_members:
            if isinstance(participant, dict):
                member_id = _participant_id(participant)
            else:
                member_id = participant
                participant = {}
            if not member_id:
                continue

            formatted_name = participant.get("formattedName")
            display_name = (
                participant.get("pushname")
                or participant.get("name")
                or participant.get("notifyName")
                or _format_phone_from_jid(member_id, formatted_name)
            )

            member = ProviderMember(
                wa_id=member_id,
                display_name=display_name,
                phone_number_masked=_mask_phone(member_id, formatted_name),
                avatar_url=None,
                is_business=bool(participant.get("isBusiness", False)),
                # WhatsApp doesn't expose a real "first seen" timestamp over
                # this API — unlike mock.py's backdated synthetic values,
                # this means "first seen *by Communeer*" (i.e. now, at sync
                # time), not "first seen by WhatsApp".
                first_seen_at=datetime.now(UTC),
                raw=participant,
            )
            memberships.append(
                ProviderMembership(
                    member=member,
                    is_admin=member_id in admin_ids,
                    # `group-admins` doesn't appear to distinguish a
                    # "super admin" tier from a regular admin — unverified,
                    # degrades to plain `is_admin` until checked against
                    # real data.
                    is_super_admin=False,
                    status="pending" if member_id in pending_ids else "member",
                    joined_at=None,
                )
            )

        return memberships

    def _list_chat_metas(self) -> list[tuple[dict, dict]]:
        """One `list-chats` fetch, paired with each chat's extracted
        `groupMetadata`. Does not itself hydrate any group's members/admins —
        callers decide which roots' subgroups are worth fanning out for, so
        `get_community(wa_id)` doesn't pay the cost of building every other
        community too (see its own docstring)."""
        raw_chats = self._fetch_groups_raw()
        metas = [(chat, self._metadata_of(chat)) for chat in raw_chats]
        if raw_chats and not any(
            "isParentGroup" in meta or "parentGroup" in meta for _, meta in metas
        ):
            raise RuntimeError(
                f"wppconnect list-chats returned {len(raw_chats)} groups but no "
                "isParentGroup/parentGroup fields were found on any of them — "
                "community structure cannot be derived; see "
                "backend/communeer/providers/whatsapp/wppconnect.py and "
                "poc/whatsapp/FINDINGS.md"
            )
        return metas

    def _build_community(
        self, chat: dict, meta: dict, metas: list[tuple[dict, dict]]
    ) -> ProviderCommunity | None:
        root_wa_id = self._wa_id_of(chat, meta)
        if not root_wa_id:
            return None

        subgroup_chats = [
            c for c, m in metas if self._jid_str(m.get("parentGroup")) == root_wa_id
        ]
        groups = [self._build_group(c) for c in subgroup_chats]
        announcement_group_wa_id = next(
            (g.wa_id for g in groups if g.is_announcement_group), None
        )

        return ProviderCommunity(
            wa_id=root_wa_id,
            name=meta.get("subject") or chat.get("name") or root_wa_id,
            description=meta.get("desc"),
            picture_url=None,
            announcement_group_wa_id=announcement_group_wa_id,
            groups=groups,
            raw=meta,
        )

    def get_communities(self) -> list[ProviderCommunity]:
        self._require_connected()
        metas = self._list_chat_metas()

        communities: list[ProviderCommunity] = []
        for chat, meta in metas:
            if not meta.get("isParentGroup"):
                continue
            community = self._build_community(chat, meta, metas)
            if community is not None:
                communities.append(community)

        return communities

    def get_community(self, wa_id: str) -> ProviderCommunity | None:
        """Builds only the requested community's tree — deliberately does
        NOT call `get_communities()` and filter, which would fan out
        `group-members`/`group-admins` calls for *every* community's
        subgroups just to answer for one. `sync_community()` calls this once
        per community returned by `get_communities()`, so that mistake would
        turn an N-community sync into O(N^2) WPPConnect requests — confirmed
        as a real, boot-hanging problem against a real account with several
        communities, not a hypothetical."""
        self._require_connected()
        metas = self._list_chat_metas()
        for chat, meta in metas:
            if meta.get("isParentGroup") and self._wa_id_of(chat, meta) == wa_id:
                return self._build_community(chat, meta, metas)
        return None

    def get_groups(self, community_wa_id: str) -> list[ProviderGroup]:
        community = self.get_community(community_wa_id)
        return list(community.groups) if community else []

    def get_group(self, wa_id: str) -> ProviderGroup | None:
        self._require_connected()
        raw_chats = self._fetch_groups_raw()
        for chat in raw_chats:
            meta = self._metadata_of(chat)
            if self._wa_id_of(chat, meta) == wa_id:
                return self._build_group(chat)
        return None

    def get_members(self, group_wa_id: str) -> list[ProviderMembership]:
        group = self.get_group(group_wa_id)
        return list(group.memberships) if group else []

    # -- "who am I" / admin-only community filter ---------------------------
    #
    # Empirically verified against a live, authenticated session (see the
    # plan this was built from): `status-session`, `host-device`, and
    # `get-phone-number` all report the connected account's real
    # phone-number JID (e.g. `4917645790258@c.us`) — but `group-members` /
    # `group-admins` address every participant, *including the connected
    # account itself*, via WhatsApp's newer opaque `@lid` identifier
    # instead (e.g. `236794549432473@lid`). These are two different ids for
    # the same account, in two different namespaces. Comparing the
    # `@c.us` id from `host-device` against a `group-admins` result
    # silently never matches — confirmed live: it returned `False` even
    # for a community the connected account genuinely administers.
    #
    # The one field that actually bridges the two namespaces: every entry
    # in a `group-members` response carries `isMe: true` on whichever
    # participant is the connected account, regardless of which namespace
    # its `id` happens to be expressed in. That flag — not `host-device` —
    # is the real "who am I" mechanism this provider relies on below.

    def _find_own_wa_id(self, metas: list[tuple[dict, dict]]) -> str | None:
        """Scan the account's visible groups for the `isMe: true`
        participant, returning its id in whatever namespace (`@c.us` or
        `@lid`) that group's roster uses — the same namespace
        `group-admins` uses, so the result can be compared against it
        directly. Tries each group in turn (cheap: one `group-members` call
        per group) until one succeeds; returns `None` if none do (e.g. no
        visible groups at all)."""
        for chat, meta in metas:
            wa_id = self._wa_id_of(chat, meta)
            if not wa_id:
                continue
            try:
                resp = self._authed_request(
                    "GET", f"/api/{self._session_name}/group-members/{wa_id}"
                )
                resp.raise_for_status()
            except httpx.HTTPError:
                continue
            for participant in _unwrap_list_response(resp.json()):
                if isinstance(participant, dict) and participant.get("isMe") is True:
                    own_id = _participant_id(participant)
                    if own_id:
                        return own_id
        return None

    def get_own_wa_id(self) -> str | None:
        """The connected account's own participant id, in the same
        namespace `group-admins`/`group-members` use for it (see the block
        comment above — this is *not* the `@c.us` id `host-device` or
        `get-phone-number` report).

        Not part of the shared `WhatsAppProvider` ABC — mirrors how
        `start_session()` is already wppconnect-only, since
        `MockWhatsAppProvider` has no session/identity concept at all.

        Never raises: returns `None` if the session isn't connected, no
        groups are visible, or nothing in any visible group's roster is
        flagged `isMe`.
        """
        try:
            self._require_connected()
            metas = self._list_chat_metas()
        except (WhatsAppNotConnectedError, httpx.HTTPError, RuntimeError):
            return None
        return self._find_own_wa_id(metas)

    def get_admin_community_wa_ids(self) -> set[str] | None:
        """See `WhatsAppProvider.get_admin_community_wa_ids` for the
        contract. Deliberately does NOT call `get_communities()` — that
        fully hydrates every subgroup's members *and* admins for every
        community, which is fine for an explicit "Discover and sync"
        action but far too expensive to run on an ordinary community-list
        page load. This instead does one `list-chats` call plus one
        `group-admins` call per community's *announcement group only*
        (skipping every other subgroup), plus whatever `group-members`
        calls `_find_own_wa_id` needs (usually just one)."""
        try:
            self._require_connected()
            metas = self._list_chat_metas()
        except (WhatsAppNotConnectedError, httpx.HTTPError, RuntimeError):
            return None

        own_wa_id = self._find_own_wa_id(metas)
        if own_wa_id is None:
            return None

        admin_wa_ids: set[str] = set()
        for chat, meta in metas:
            if not meta.get("isParentGroup"):
                continue
            root_wa_id = self._wa_id_of(chat, meta)
            if not root_wa_id:
                continue

            announcement = next(
                (
                    (c, m)
                    for c, m in metas
                    if bool(m.get("announce", False))
                    and self._jid_str(m.get("parentGroup")) == root_wa_id
                ),
                None,
            )
            if announcement is None:
                continue
            ann_chat, ann_meta = announcement
            ann_wa_id = self._wa_id_of(ann_chat, ann_meta)
            if not ann_wa_id:
                continue

            try:
                resp = self._authed_request(
                    "GET", f"/api/{self._session_name}/group-admins/{ann_wa_id}"
                )
                resp.raise_for_status()
            except httpx.HTTPError:
                continue
            raw_admins = _flatten_participant_list(_unwrap_list_response(resp.json()))
            admin_ids = {_participant_id(a) for a in raw_admins if _participant_id(a)}
            if own_wa_id in admin_ids:
                admin_wa_ids.add(root_wa_id)

        return admin_wa_ids
