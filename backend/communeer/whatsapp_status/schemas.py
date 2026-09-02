from communeer.communities.schemas import CommunitySummaryOut
from communeer.providers.whatsapp.base import WhatsAppConnectionState
from communeer.schemas import CamelModel


class WhatsAppStatusOut(CamelModel):
    state: WhatsAppConnectionState
    qr_code_data_url: str | None
    detail: str | None
    # Whether `POST /whatsapp/discover-and-sync` is currently running (see
    # `whatsapp_status/router.py`'s module-level lock) — lets the frontend
    # keep showing "Discovering…" across a page reload, since that endpoint
    # is a single long-running synchronous request with no other persisted
    # progress signal.
    discovery_in_progress: bool


class DiscoverAndSyncFailureOut(CamelModel):
    """A community the provider found but whose sync itself failed —
    surfaced to the caller instead of only a backend log line, so the
    Setup page can tell the difference between "nothing to find" and
    "something went wrong partway through" (see `WhatsAppSetupPage.tsx`)."""

    wa_id: str
    name: str
    reason: str


class DiscoverAndSyncResultOut(CamelModel):
    """Every community the provider actually found and synced —
    deliberately unfiltered, unlike `GET /communities`. `hidden_non_admin_wa_ids`
    is the subset of `communities` that `GET /communities` will go on to hide
    because the connected WhatsApp number isn't an admin there (see that
    route's own admin-only filter) — included here so the Setup page can
    say so honestly instead of a newly-synced community just silently never
    appearing anywhere."""

    communities: list[CommunitySummaryOut]
    hidden_non_admin_wa_ids: list[str]
    failed: list[DiscoverAndSyncFailureOut]
