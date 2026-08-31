"""Deterministic fixture provider.

Everything here is seeded off `random.Random(42)` so repeated syncs against
this provider are idempotent (same wa_ids, same names, same counts every
time the process runs) — that's what lets `sync_community`'s "second sync is
a no-op" test actually assert equality instead of just "didn't crash".

The two flagship groups intentionally reuse the numbers from the product
spec's own mockups (Marketplace 981/1024, Buy & Sell 400/512) so the
Overview/Groups screens can be checked against those mockups pixel-for-pixel
later. `raw` payloads mirror the exact WPPConnect field names spotted during
the `poc/whatsapp` spike (`isParentGroup`, `parentGroup`, `announce`,
`pastParticipants`, `pendingParticipants`, `membershipApprovalRequests`) so
the Advanced/raw-metadata viewer already looks like what a real provider will
eventually send.
"""

import base64
import hashlib
import random
from datetime import UTC, datetime, timedelta
from itertools import product

from communeer.providers.whatsapp.base import (
    ProviderCommunity,
    ProviderGroup,
    ProviderMember,
    ProviderMembership,
    WhatsAppConnectionState,
    WhatsAppConnectionStatus,
    WhatsAppProvider,
    WhatsAppProviderUnavailableError,
)

_SEED = 42
_NOW = datetime(2026, 8, 1, tzinfo=UTC)

_FIRST_NAMES = [
    "Amara", "Ben", "Carla", "Deniz", "Elin", "Farid", "Greta", "Hassan",
    "Ines", "Jonas", "Kira", "Luca", "Mira", "Noah", "Olga", "Pavel",
    "Quinn", "Rosa", "Sami", "Tara", "Uwe", "Vera", "Wiktor", "Xenia",
    "Yara", "Zane", "Aylin", "Bjorn", "Chiara", "Dario", "Esra", "Finn",
    "Gilda", "Hugo", "Ida", "Jamal", "Kaya", "Leon", "Maja", "Nils",
]
_LAST_NAMES = [
    "Berger", "Costa", "Duarte", "Eren", "Fischer", "Gonzalez", "Hoffmann",
    "Ibrahim", "Jansen", "Klein", "Lindgren", "Moreau", "Novak", "Oliveira",
    "Petrov", "Quintero", "Richter", "Santos", "Tanaka", "Ulrich", "Vogel",
    "Weber", "Xu", "Yildiz", "Zimmer", "Adler", "Brandt", "Costa-Reis",
    "Diallo", "Ebert", "Farah", "Graf", "Haas", "Ionescu", "Jung", "Krause",
    "Lund", "Meyer", "Nowak", "Ostrowski",
]

_BUSINESS_RATE = 0.06


class _NameFactory:
    """Deterministic, non-repeating (first, last) name pairs."""

    def __init__(self, rng: random.Random) -> None:
        pairs = list(product(_FIRST_NAMES, _LAST_NAMES))
        rng.shuffle(pairs)
        self._pairs = pairs
        self._next = 0

    def next(self) -> str:
        if self._next < len(self._pairs):
            first, last = self._pairs[self._next]
            self._next += 1
            return f"{first} {last}"
        # exhausted the combinatorial space (shouldn't happen at our fixture
        # sizes) — fall back to a numbered variant so names stay unique.
        first, last = self._pairs[self._next % len(self._pairs)]
        suffix = self._next // len(self._pairs) + 1
        self._next += 1
        return f"{first} {last} ({suffix})"


def _build_fixture() -> tuple[ProviderCommunity, ProviderCommunity]:
    rng = random.Random(_SEED)
    names = _NameFactory(rng)

    wa_counter = {"n": 0}

    def make_member() -> ProviderMember:
        wa_counter["n"] += 1
        idx = wa_counter["n"]
        wa_id = f"4915{100000000 + idx}@c.us"
        area = rng.choice(["151", "160", "170", "176", "179"])
        last4 = f"{rng.randint(0, 9999):04d}"
        is_business = rng.random() < _BUSINESS_RATE
        first_seen = _NOW - timedelta(days=rng.randint(5, 900))
        member = ProviderMember(
            wa_id=wa_id,
            display_name=names.next(),
            phone_number_masked=f"+49 {area} •••• {last4}",
            avatar_url=None,
            is_business=is_business,
            first_seen_at=first_seen,
            raw={"pushname": None, "isBusiness": is_business, "isMyContact": True},
        )
        return member

    def make_membership(member: ProviderMember, *, is_admin: bool = False,
                         is_super_admin: bool = False,
                         status: str = "member") -> ProviderMembership:
        joined = None
        if status == "member":
            joined = member.first_seen_at + timedelta(days=rng.randint(0, 30))
        else:
            joined = _NOW - timedelta(days=rng.randint(0, 5))

        # Synthetic, deterministic `last_message_at`, with real variety on
        # purpose: some members are recent posters, some haven't written in
        # a long while, and some have genuinely never posted — that last
        # case must be a real, visible outcome here too (not something only
        # the real provider ever produces), otherwise the frontend would
        # never see the "never posted" case in mock mode. A `pending`
        # member hasn't actually joined the group yet, so they get `None`
        # here unconditionally rather than a fabricated message history.
        # `last_seen_at` stays `None` unconditionally, even in mock mode:
        # faking presence data would suggest something the real provider
        # (WPPConnect) can never actually supply — see wppconnect.py.
        last_message_at = None
        if status == "member":
            roll = rng.random()
            if roll < 0.18:
                last_message_at = None  # never posted in this group
            elif roll < 0.55:
                # recent poster: sometime in the last two weeks.
                last_message_at = _NOW - timedelta(
                    days=rng.randint(0, 14), hours=rng.randint(0, 23)
                )
            else:
                # posted at some point between joining and now, but not
                # necessarily recently.
                span_days = max((_NOW - joined).days, 1)
                last_message_at = joined + timedelta(days=rng.randint(0, span_days))

        return ProviderMembership(
            member=member,
            is_admin=is_admin,
            is_super_admin=is_super_admin,
            status=status,
            joined_at=joined,
            last_message_at=last_message_at,
            last_seen_at=None,
            # Mirrors `last_message_at` above into the unified activity
            # fields too, for consistency with the real WPPConnect provider
            # (which now derives both from the same parsed chat history) —
            # no synthetic message body is generated here, so content stays
            # `None` rather than fabricating text nobody asked for.
            last_activity_type="message" if last_message_at is not None else None,
            last_activity_at=last_message_at,
            last_activity_content=None,
        )

    def make_pool(count: int) -> list[ProviderMember]:
        return [make_member() for _ in range(count)]

    def sample(pool: list[ProviderMember], count: int) -> list[ProviderMember]:
        count = min(count, len(pool))
        return rng.sample(pool, count)

    def group_raw(*, is_parent: bool, parent_wa_id: str | None, announce: bool,
                   pending_wa_ids: list[str], all_member_wa_ids: list[str]) -> dict:
        past_participants = rng.sample(
            all_member_wa_ids, k=min(len(all_member_wa_ids), rng.randint(0, 4))
        )
        return {
            "isParentGroup": is_parent,
            "parentGroup": parent_wa_id,
            "announce": announce,
            "pastParticipants": past_participants,
            "pendingParticipants": list(pending_wa_ids),
            "membershipApprovalRequests": [
                {
                    "wa_id": wa_id,
                    "requestedAt": (_NOW - timedelta(days=rng.randint(0, 3))).isoformat(),
                }
                for wa_id in pending_wa_ids
            ],
        }

    # ---- shared pool, reused across both communities for realistic overlap
    shared_pool = make_pool(150)

    # ======================================================================
    # Unity Alpha
    # ======================================================================
    unity_wa_id = "120363010000000001@g.us"

    unity_marketplace_wa_id = "120363010000000010@g.us"
    unity_general_wa_id = "120363010000000011@g.us"
    unity_events_wa_id = "120363010000000012@g.us"
    unity_announcements_wa_id = "120363010000000013@g.us"

    unity_filler = make_pool(900)  # enough to pad Marketplace to 981 uniques

    marketplace_members = (sample(shared_pool, 60) + unity_filler[:921])
    # de-dupe while preserving order, then trim/pad to exactly 981
    seen: set[str] = set()
    dedup: list[ProviderMember] = []
    for m in marketplace_members:
        if m.wa_id not in seen:
            seen.add(m.wa_id)
            dedup.append(m)
    marketplace_members = dedup[:981]
    while len(marketplace_members) < 981:
        marketplace_members.append(make_member())

    marketplace_pending = make_pool(3)

    general_members = sample(shared_pool, 70) + sample(marketplace_members, 110)
    general_members = list({m.wa_id: m for m in general_members}.values())[:180]
    while len(general_members) < 180:
        general_members.append(make_member())

    events_members = sample(shared_pool, 25) + sample(marketplace_members, 35)
    events_members = list({m.wa_id: m for m in events_members}.values())[:60]
    while len(events_members) < 60:
        events_members.append(make_member())

    unity_all_members = list(
        {
            m.wa_id: m
            for m in [*marketplace_members, *general_members, *events_members]
        }.values()
    )

    # a handful of *different* people hold admin rights across the various
    # groups (not just one person everywhere) — the community super-admin
    # (the one who's admin of the Announcements group) is a distinct role
    # from a plain group admin.
    unity_super_admin = unity_all_members[0]
    unity_marketplace_admin_ids = {marketplace_members[0].wa_id, marketplace_members[1].wa_id}
    unity_general_admin_id = general_members[0].wa_id
    unity_events_admin_id = events_members[0].wa_id
    unity_group_admin_ids = (
        unity_marketplace_admin_ids | {unity_general_admin_id, unity_events_admin_id}
    )

    marketplace_group = ProviderGroup(
        wa_id=unity_marketplace_wa_id,
        name="Marketplace",
        description="Buy, sell, and trade with fellow Unity Alpha members.",
        picture_url=None,
        is_announcement_group=False,
        member_limit=1024,
        memberships=[
            make_membership(m, is_admin=(m.wa_id in unity_marketplace_admin_ids))
            for m in marketplace_members
        ]
        + [make_membership(m, status="pending") for m in marketplace_pending],
        raw=group_raw(
            is_parent=False,
            parent_wa_id=unity_wa_id,
            announce=False,
            pending_wa_ids=[m.wa_id for m in marketplace_pending],
            all_member_wa_ids=[m.wa_id for m in marketplace_members],
        ),
    )
    general_group = ProviderGroup(
        wa_id=unity_general_wa_id,
        name="General",
        description="General chat for all Unity Alpha members.",
        picture_url=None,
        is_announcement_group=False,
        member_limit=1024,
        memberships=[
            make_membership(m, is_admin=(m.wa_id == unity_general_admin_id))
            for m in general_members
        ],
        raw=group_raw(
            is_parent=False,
            parent_wa_id=unity_wa_id,
            announce=False,
            pending_wa_ids=[],
            all_member_wa_ids=[m.wa_id for m in general_members],
        ),
    )
    events_group = ProviderGroup(
        wa_id=unity_events_wa_id,
        name="Events",
        description="Meetups, workshops, and community events.",
        picture_url=None,
        is_announcement_group=False,
        member_limit=512,
        memberships=[
            make_membership(m, is_admin=(m.wa_id == unity_events_admin_id)) for m in events_members
        ],
        raw=group_raw(
            is_parent=False,
            parent_wa_id=unity_wa_id,
            announce=False,
            pending_wa_ids=[],
            all_member_wa_ids=[m.wa_id for m in events_members],
        ),
    )
    announcements_group = ProviderGroup(
        wa_id=unity_announcements_wa_id,
        name="Announcements",
        description="Official announcements from Unity Alpha admins.",
        picture_url=None,
        is_announcement_group=True,
        member_limit=None,
        memberships=[
            make_membership(
                m,
                is_admin=(m.wa_id in unity_group_admin_ids or m.wa_id == unity_super_admin.wa_id),
                is_super_admin=(m.wa_id == unity_super_admin.wa_id),
            )
            for m in unity_all_members
        ],
        raw=group_raw(
            is_parent=False,
            parent_wa_id=unity_wa_id,
            announce=True,
            pending_wa_ids=[],
            all_member_wa_ids=[m.wa_id for m in unity_all_members],
        ),
    )

    unity_alpha = ProviderCommunity(
        wa_id=unity_wa_id,
        name="Unity Alpha",
        description="A friendly neighborhood community, kept in sync from WhatsApp.",
        picture_url=None,
        announcement_group_wa_id=unity_announcements_wa_id,
        groups=[announcements_group, marketplace_group, general_group, events_group],
        raw={
            "isParentGroup": True,
            "parentGroup": None,
            "announce": False,
            "pastParticipants": [],
            "pendingParticipants": [],
            "membershipApprovalRequests": [],
        },
    )

    # ======================================================================
    # Riverside Collective
    # ======================================================================
    riverside_wa_id = "120363020000000001@g.us"

    riverside_buysell_wa_id = "120363020000000010@g.us"
    riverside_neighbors_wa_id = "120363020000000011@g.us"
    riverside_volunteers_wa_id = "120363020000000012@g.us"
    riverside_announcements_wa_id = "120363020000000013@g.us"

    riverside_filler = make_pool(400)  # pads Buy & Sell to 400 uniques

    buysell_members = sample(shared_pool, 40) + riverside_filler[:360]
    buysell_members = list({m.wa_id: m for m in buysell_members}.values())[:400]
    while len(buysell_members) < 400:
        buysell_members.append(make_member())

    neighbors_members = sample(shared_pool, 50) + sample(buysell_members, 200)
    neighbors_members = list({m.wa_id: m for m in neighbors_members}.values())[:250]
    while len(neighbors_members) < 250:
        neighbors_members.append(make_member())

    volunteers_members = sample(shared_pool, 10) + sample(neighbors_members, 15)
    volunteers_members = list({m.wa_id: m for m in volunteers_members}.values())[:25]
    while len(volunteers_members) < 25:
        volunteers_members.append(make_member())
    volunteers_pending = make_pool(2)

    riverside_all_members = list(
        {
            m.wa_id: m
            for m in [*buysell_members, *neighbors_members, *volunteers_members]
        }.values()
    )

    riverside_super_admin = riverside_all_members[0]
    riverside_buysell_admin_ids = {buysell_members[0].wa_id, buysell_members[1].wa_id}
    riverside_neighbors_admin_id = neighbors_members[0].wa_id
    riverside_volunteers_admin_id = volunteers_members[0].wa_id
    riverside_group_admin_ids = riverside_buysell_admin_ids | {
        riverside_neighbors_admin_id,
        riverside_volunteers_admin_id,
    }

    buysell_group = ProviderGroup(
        wa_id=riverside_buysell_wa_id,
        name="Buy & Sell",
        description="A marketplace for Riverside Collective neighbors.",
        picture_url=None,
        is_announcement_group=False,
        member_limit=512,
        memberships=[
            make_membership(m, is_admin=(m.wa_id in riverside_buysell_admin_ids))
            for m in buysell_members
        ],
        raw=group_raw(
            is_parent=False,
            parent_wa_id=riverside_wa_id,
            announce=False,
            pending_wa_ids=[],
            all_member_wa_ids=[m.wa_id for m in buysell_members],
        ),
    )
    neighbors_group = ProviderGroup(
        wa_id=riverside_neighbors_wa_id,
        name="Neighbors",
        description="General chat for Riverside Collective neighbors.",
        picture_url=None,
        is_announcement_group=False,
        member_limit=1024,
        memberships=[
            make_membership(m, is_admin=(m.wa_id == riverside_neighbors_admin_id))
            for m in neighbors_members
        ],
        raw=group_raw(
            is_parent=False,
            parent_wa_id=riverside_wa_id,
            announce=False,
            pending_wa_ids=[],
            all_member_wa_ids=[m.wa_id for m in neighbors_members],
        ),
    )
    volunteers_group = ProviderGroup(
        wa_id=riverside_volunteers_wa_id,
        name="Volunteers",
        description="Coordination for neighborhood volunteer efforts.",
        picture_url=None,
        is_announcement_group=False,
        member_limit=512,
        memberships=[
            make_membership(m, is_admin=(m.wa_id == riverside_volunteers_admin_id))
            for m in volunteers_members
        ]
        + [make_membership(m, status="pending") for m in volunteers_pending],
        raw=group_raw(
            is_parent=False,
            parent_wa_id=riverside_wa_id,
            announce=False,
            pending_wa_ids=[m.wa_id for m in volunteers_pending],
            all_member_wa_ids=[m.wa_id for m in volunteers_members],
        ),
    )
    riverside_announcements_group = ProviderGroup(
        wa_id=riverside_announcements_wa_id,
        name="Announcements",
        description="Official announcements from Riverside Collective admins.",
        picture_url=None,
        is_announcement_group=True,
        member_limit=None,
        memberships=[
            make_membership(
                m,
                is_admin=(m.wa_id in riverside_group_admin_ids or m.wa_id == riverside_super_admin.wa_id),
                is_super_admin=(m.wa_id == riverside_super_admin.wa_id),
            )
            for m in riverside_all_members
        ],
        raw=group_raw(
            is_parent=False,
            parent_wa_id=riverside_wa_id,
            announce=True,
            pending_wa_ids=[],
            all_member_wa_ids=[m.wa_id for m in riverside_all_members],
        ),
    )

    riverside_collective = ProviderCommunity(
        wa_id=riverside_wa_id,
        name="Riverside Collective",
        description="Neighbors of the Riverside district, organizing together.",
        picture_url=None,
        announcement_group_wa_id=riverside_announcements_wa_id,
        groups=[
            riverside_announcements_group,
            buysell_group,
            neighbors_group,
            volunteers_group,
        ],
        raw={
            "isParentGroup": True,
            "parentGroup": None,
            "announce": False,
            "pastParticipants": [],
            "pendingParticipants": [],
            "membershipApprovalRequests": [],
        },
    )

    return unity_alpha, riverside_collective


class MockWhatsAppProvider(WhatsAppProvider):
    """Fixed, seeded fixture standing in for a real WhatsApp integration."""

    def __init__(self) -> None:
        self._unity_alpha, self._riverside_collective = _build_fixture()
        self._communities = [self._unity_alpha, self._riverside_collective]
        self._groups_by_wa_id = {
            g.wa_id: g for c in self._communities for g in c.groups
        }
        self._community_by_group_wa_id = {
            g.wa_id: c for c in self._communities for g in c.groups
        }

    def get_communities(self) -> list[ProviderCommunity]:
        return list(self._communities)

    def get_community(self, wa_id: str) -> ProviderCommunity | None:
        for c in self._communities:
            if c.wa_id == wa_id:
                return c
        return None

    def get_groups(self, community_wa_id: str) -> list[ProviderGroup]:
        community = self.get_community(community_wa_id)
        return list(community.groups) if community else []

    def get_group(self, wa_id: str) -> ProviderGroup | None:
        return self._groups_by_wa_id.get(wa_id)

    def get_members(self, group_wa_id: str) -> list[ProviderMembership]:
        group = self._groups_by_wa_id.get(group_wa_id)
        return list(group.memberships) if group else []

    def get_connection_status(self) -> WhatsAppConnectionStatus:
        # Mock has no session concept at all — it's always "connected" so
        # every downstream behavior (boot priming, the setup flow) is a
        # true no-op in mock mode.
        return WhatsAppConnectionStatus(state=WhatsAppConnectionState.connected)

    def get_admin_community_wa_ids(self) -> set[str] | None:
        # Mock has no "connected account" concept at all — always `None`
        # (no filtering) so mock mode keeps showing every fixture community,
        # completely unaffected by the admin-only filter.
        return None

    def get_group_invite_link(self, group_wa_id: str) -> str | None:
        # Deterministic per group (same code every call, like every other
        # fixture in this file) rather than random — a 22-char code derived
        # from a hash of the group's own id, shaped like a real WhatsApp
        # invite code but obviously never a working link.
        digest = hashlib.sha256(group_wa_id.encode()).hexdigest()
        code = base64.urlsafe_b64encode(bytes.fromhex(digest))[:22].decode()
        return f"https://chat.whatsapp.com/{code}"

    def _get_group_or_raise(self, group_wa_id: str) -> ProviderGroup:
        group = self._groups_by_wa_id.get(group_wa_id)
        if group is None:
            raise WhatsAppProviderUnavailableError(f"Unknown group: {group_wa_id!r}")
        return group

    def _find_membership_index(self, group: ProviderGroup, member_wa_id: str) -> int:
        for index, membership in enumerate(group.memberships):
            if membership.member.wa_id == member_wa_id:
                return index
        raise WhatsAppProviderUnavailableError(
            f"No membership for {member_wa_id!r} in group {group.wa_id!r}"
        )

    def _strip_pending_wa_id(self, group: ProviderGroup, member_wa_id: str) -> None:
        """Keep `raw`'s WPPConnect-shaped `pendingParticipants`/
        `membershipApprovalRequests` fields consistent with `memberships`
        after an approve/reject — the raw-metadata viewer reads directly from
        `raw`, so a stale pending entry there would look like a UI bug."""
        group.raw["pendingParticipants"] = [
            wa_id for wa_id in group.raw.get("pendingParticipants", []) if wa_id != member_wa_id
        ]
        group.raw["membershipApprovalRequests"] = [
            entry
            for entry in group.raw.get("membershipApprovalRequests", [])
            if entry.get("wa_id") != member_wa_id
        ]

    def approve_join_request(self, group_wa_id: str, member_wa_id: str) -> None:
        group = self._get_group_or_raise(group_wa_id)
        index = self._find_membership_index(group, member_wa_id)
        membership = group.memberships[index]
        if membership.status != "pending":
            raise WhatsAppProviderUnavailableError(
                f"Membership for {member_wa_id!r} in group {group_wa_id!r} is not pending"
            )
        group.memberships[index] = membership.model_copy(
            update={"status": "member", "joined_at": datetime.now(UTC)}
        )
        self._strip_pending_wa_id(group, member_wa_id)

    def reject_join_request(self, group_wa_id: str, member_wa_id: str) -> None:
        group = self._get_group_or_raise(group_wa_id)
        index = self._find_membership_index(group, member_wa_id)
        if group.memberships[index].status != "pending":
            raise WhatsAppProviderUnavailableError(
                f"Membership for {member_wa_id!r} in group {group_wa_id!r} is not pending"
            )
        del group.memberships[index]
        self._strip_pending_wa_id(group, member_wa_id)

    def remove_member(self, group_wa_id: str, member_wa_id: str) -> None:
        group = self._get_group_or_raise(group_wa_id)
        index = self._find_membership_index(group, member_wa_id)
        del group.memberships[index]
        self._strip_pending_wa_id(group, member_wa_id)

    def set_member_admin(self, group_wa_id: str, member_wa_id: str, is_admin: bool) -> None:
        group = self._get_group_or_raise(group_wa_id)
        index = self._find_membership_index(group, member_wa_id)
        group.memberships[index] = group.memberships[index].model_copy(update={"is_admin": is_admin})
