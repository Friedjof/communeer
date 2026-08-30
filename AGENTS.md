# AGENTS.md

Guidance for AI coding agents (and human contributors) working in this repo.

## Project overview

Communeer is a self-hosted WhatsApp-community admin dashboard: FastAPI +
SQLAlchemy + SQLite backend (`backend/`), React + Vite + TanStack
frontend (`frontend/`), Docker Compose stack (frontend/Caddy, backend,
redis (reserved, unused today), wppconnect). WhatsApp integration goes
through a `WhatsAppProvider` abstraction
(`backend/communeer/providers/whatsapp/base.py`) with two
implementations: `MockWhatsAppProvider` (deterministic fixtures, default)
and `WppconnectProvider` (real WPPConnect Server REST API). Never call
WPPConnect directly from anywhere else — always go through the provider
interface.

## Setup / build / test commands

Backend (from `backend/`):

```bash
uv sync                 # install deps
uv run pytest -q        # run the test suite
uv run ruff check .     # lint
```

Frontend (from `frontend/`):

```bash
pnpm install
pnpm lint                # oxlint
pnpm build               # tsc -b && vite build
```

Full stack: `docker compose up -d` from the repo root. See `README.md`
for the complete quickstart.

## Non-negotiable principles

These are established, deliberate decisions in this codebase — don't
casually reverse them:

- **Never fabricate data.** If something genuinely isn't available (e.g.
  WhatsApp read-receipts/"last seen" — verified live, not exposed by the
  platform for most accounts), represent it honestly as unavailable
  (`lastSeenAt`, the `view` activity type) rather than inventing a
  plausible-looking value or silently dropping the field.
- **Never let Communeer write to WhatsApp automatically.** Renewal
  campaigns and the moderation queue are deliberately *tracking-only* —
  Communeer surfaces candidates/signals, a human always performs the
  actual WhatsApp action (posting a message, removing a member,
  promoting an admin) manually. This is a considered account-safety
  decision (WPPConnect is unofficial browser automation, not the
  official WhatsApp Business API — bulk/automated actions are the
  pattern most associated with account bans), not an oversight. Don't
  add a "just do it automatically" shortcut without an explicit,
  separate decision to accept that risk.
- **Forward-only stamping for activity timestamps.** Fields like
  `last_message_at`, `last_seen_at`, `last_activity_at` only ever move
  forward in time and never get blanked by a later sync that happens to
  report `None` or an older value — see `sync/service.py`'s comments for
  the exact pattern, and reuse it for any new activity-style field.
- **API contract is camelCase.** Every Pydantic schema extends
  `CamelModel` (`backend/communeer/schemas.py`, `alias_generator=to_camel`)
  — write snake_case Python field names as usual, the camelCase JSON
  conversion is automatic. Don't hand-roll aliases.
- **No pagination envelope.** List endpoints return bare JSON arrays, not
  `{items: [...], total: ...}` wrappers.

## Code style

- Comments explain *why*, never *what* — well-named identifiers already
  say what the code does. Only comment a hidden constraint, a subtle
  invariant, or a workaround for a specific external quirk (WPPConnect's
  inconsistent JID shapes are a recurring example worth documenting where
  encountered).
- No speculative abstraction. Match the existing per-file style (e.g.
  the explicit, non-abstracted style of `moderation/service.py`) rather
  than introducing a new pattern for its own sake.
- Backend: type hints throughout, no `# type: ignore` except the standard
  SQLAlchemy `noqa: F821` for forward-referenced `Mapped["ClassName"]`
  relationships.
- Frontend: no `as any`/`@ts-ignore`/non-null assertions — if the type is
  genuinely uncertain (e.g. a raw WPPConnect webhook payload), type it as
  `dict[str, Any]`/`unknown` and narrow explicitly.

## Testing

- Backend: `backend/tests/`, pytest, one file per feature area. Follow
  the existing pattern for role-gate tests (seed a `viewer` user directly
  via the DB, assert 403; assert 200/204 for the owner/admin seed user) —
  see `test_moderation.py`.
- Frontend: co-locate `*.test.tsx` next to the component under test
  (vitest + `@testing-library/react`, `pnpm test` to run).

## Working with the live Docker stack

- **Never restart the `wppconnect` service casually.** It holds a real,
  live WhatsApp session backed by a persistent Chromium profile
  (`wppconnect_user_data` volume). An ungraceful restart can leave a
  stale `SingletonLock`/`SingletonCookie`/`SingletonSocket` file that
  blocks the browser from launching on next start — recoverable, but
  avoidable. Only restart it when explicitly required, and prefer
  targeted fixes over `docker compose down`.
- Editing `docker-compose.yml`'s `wppconnect` service block (even
  something like adding a `restart:` policy) causes the next
  `docker compose up` to recreate that container too, even without
  naming it explicitly — Compose reconciles any service whose config
  changed. Be aware of this before editing that block.
- After any backend/frontend change: `docker compose build <service> &&
  docker compose up -d --force-recreate <service>` — never `docker
  compose down` unless truly necessary.
