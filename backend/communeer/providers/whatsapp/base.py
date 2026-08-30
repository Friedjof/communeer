"""Provider-facing DTOs and the `WhatsAppProvider` seam.

These are plain Pydantic models describing what *any* WhatsApp integration
(mock today, a real WPPConnect-backed provider later) hands back to
`sync/service.py`. The sync layer only ever talks to this interface, never to
a concrete provider, so swapping `mock` for `wppconnect` via the
`WHATSAPP_PROVIDER` env var touches no router or service code.

Read-only for now: `remove_member` / other mutating operations are a
documented future extension point, not a stubbed dead endpoint.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ProviderMember(BaseModel):
    """A WhatsApp contact, independent of any particular group."""

    model_config = ConfigDict(frozen=True)

    wa_id: str
    display_name: str
    phone_number_masked: str | None = None
    avatar_url: str | None = None
    is_business: bool = False
    first_seen_at: datetime
    raw: dict = {}


class ProviderMembership(BaseModel):
    """One member's standing within one group."""

    model_config = ConfigDict(frozen=True)

    member: ProviderMember
    is_admin: bool = False
    is_super_admin: bool = False
    status: Literal["member", "pending"] = "member"
    joined_at: datetime | None = None
    # Real activity signals. `last_message_at`: last time this member wrote a
    # real (non-system) message in this group — WPPConnect can supply this
    # (see `WppconnectProvider._build_memberships`). `last_seen_at`: last
    # presence/read-receipt info — always `None` for every provider today;
    # WhatsApp doesn't expose this in practice (verified live: `last-seen`/
    # `chat-is-online` return no data for real accounts), so this field
    # exists for a future provider that might actually supply it, not because
    # any current provider does.
    last_message_at: datetime | None = None
    last_seen_at: datetime | None = None
    # Unified "last activity" (message/reaction/view) — a richer sibling of
    # `last_message_at` above (type + timestamp + content, not just a
    # timestamp). A real provider can only ever supply `"message"` here (from
    # parsed chat history at sync time, see `WppconnectProvider`); `reaction`/
    # `view` are populated exclusively by the live webhook
    # (`webhooks/router.py`), never backfilled at sync — there's no bulk
    # "past reactions" API call this codebase is willing to make (N+1, one
    # call per message; see `wppconnect.py`'s own docstring), and no
    # "past views" API exists at all. A plain `Literal` rather than importing
    # the DB-layer `ActivityType` enum, matching how `status` above is
    # already a `Literal` instead of importing `MembershipStatus` — this
    # module stays decoupled from `communeer.models`.
    last_activity_type: Literal["message", "reaction", "view"] | None = None
    last_activity_at: datetime | None = None
    last_activity_content: str | None = None


class ProviderGroup(BaseModel):
    """A single WhatsApp group, with its membership roster embedded."""

    model_config = ConfigDict(frozen=True)

    wa_id: str
    name: str
    description: str | None = None
    picture_url: str | None = None
    is_announcement_group: bool = False
    member_limit: int | None = None
    memberships: list[ProviderMembership] = []
    raw: dict = {}


class ProviderCommunity(BaseModel):
    """A WhatsApp community, with its groups (and, transitively, their
    membership rosters) embedded — enough for `sync_community` to mirror the
    provider's current state in a single call.
    """

    model_config = ConfigDict(frozen=True)

    wa_id: str
    name: str
    description: str | None = None
    picture_url: str | None = None
    announcement_group_wa_id: str | None = None
    groups: list[ProviderGroup] = []
    raw: dict = {}


class WhatsAppConnectionState(str, Enum):
    """Lifecycle of a provider's underlying WhatsApp session (not a
    per-community sync state — this is about whether the provider can talk
    to WhatsApp at all)."""

    disconnected = "disconnected"
    qr_pending = "qr_pending"
    connecting = "connecting"
    connected = "connected"
    error = "error"


class WhatsAppConnectionStatus(BaseModel):
    """Snapshot of `WhatsAppProvider.get_connection_status()`."""

    model_config = ConfigDict(frozen=True)

    state: WhatsAppConnectionState
    qr_code_data_url: str | None = None
    detail: str | None = None


class WhatsAppNotConnectedError(Exception):
    """Raised by a provider method that requires a live session when the
    underlying connection isn't `connected`. Carries the actual state
    (as its string value) so callers can render something more specific than
    a generic failure."""


class WhatsAppProviderUnavailableError(Exception):
    """Raised when the underlying WhatsApp integration (e.g. the WPPConnect
    server) can't be reached or returns something unusable — a transport
    failure, not a "not connected yet" state. Callers should turn this into
    a fast, honest error response instead of letting it hang until an HTTP
    client timeout and fall through to a generic 500."""


class WhatsAppProvider(ABC):
    """Abstract seam every WhatsApp integration implements."""

    @abstractmethod
    def get_communities(self) -> list[ProviderCommunity]:
        """List every community visible to this provider (summary only —
        callers needing full group/member detail should use
        `get_community`)."""

    @abstractmethod
    def get_community(self, wa_id: str) -> ProviderCommunity | None:
        """Fetch one community with its full groups/memberships graph."""

    @abstractmethod
    def get_groups(self, community_wa_id: str) -> list[ProviderGroup]:
        """List the groups belonging to one community."""

    @abstractmethod
    def get_group(self, wa_id: str) -> ProviderGroup | None:
        """Fetch one group with its membership roster."""

    @abstractmethod
    def get_members(self, group_wa_id: str) -> list[ProviderMembership]:
        """List the memberships (member + standing) for one group."""

    @abstractmethod
    def get_connection_status(self) -> WhatsAppConnectionStatus:
        """Report whether this provider's underlying WhatsApp session is
        usable right now.

        Contract: **must never raise**. Any internal failure (network error,
        unexpected response shape, etc.) must be caught and reported back as
        `WhatsAppConnectionStatus(state=WhatsAppConnectionState.error,
        detail=...)` instead of propagating — callers (including the
        `/whatsapp/status` endpoint, which is polled from the frontend) rely
        on this always returning a value.
        """

    @abstractmethod
    def get_admin_community_wa_ids(self) -> set[str] | None:
        """Which communities (by `wa_id`) the connected account administers,
        for filtering the community selector down to "only what I can
        actually act on".

        Returns `None` to mean **"no filtering, show everything"** — either
        because this provider has no notion of "the connected account's own
        identity" at all, or because that identity couldn't be determined
        right now (not connected, a transient error, etc.). An empty set is
        a real, different answer: "identity is known, and it isn't admin of
        any visible community." Callers must treat `None` and `set()`
        differently — only `None` skips filtering.

        Contract: **must never raise** (same posture as
        `get_connection_status`) — any internal failure should degrade to
        `None` rather than propagate, since callers use this to *narrow* a
        list, and a crash here shouldn't take down an otherwise-working
        community list.
        """

    @abstractmethod
    def get_group_invite_link(self, group_wa_id: str) -> str | None:
        """The group's current `https://chat.whatsapp.com/...` invite link,
        fetched on demand (never prefetched/cached alongside the rest of a
        group's data — this is a separate, deliberately lazy WPPConnect
        call, matching this codebase's "no request nobody asked for" cost
        posture).

        Contract: **must never raise** — a group the connected account can't
        generate a link for (not an admin there, links revoked, a transient
        WPPConnect error) degrades to `None`, the same honest-unavailability
        posture as every other "WhatsApp doesn't give us this right now"
        case in this codebase, not an error to surface as a 500.
        """
