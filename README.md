# Communeer

Self-hosted admin dashboard for managing large WhatsApp communities — an
overview and moderation tool for admins, not a chatbot or marketing
automation platform.

## What it does today

- **Community, group, and member overview** — synced from WhatsApp into a
  local database, so the dashboard stays fast even for communities with
  thousands of members.
- **Real WhatsApp integration** via [WPPConnect](https://github.com/wppconnect-team/wppconnect-server)
  (opt-in), or a deterministic mock provider for trying the app without a
  real account. Only communities the connected account actually administers
  are shown. An inbound WPPConnect webhook (secured with a shared
  `WEBHOOK_SECRET`) keeps member activity current between syncs — new
  messages and reactions update a member's last-activity fields live,
  without needing a manual "Sync now".
- **Growth analytics** — member-count-over-time and per-group growth charts,
  built from a snapshot recorded on every sync.
- **Renewal campaigns** — a manual tracking tool for periodic
  re-confirmation rounds ("does this person still belong here?"). Communeer
  tracks who's confirmed and who's overdue; it never sends WhatsApp messages,
  reads reactions, or removes anyone on its own — those steps stay with you,
  in WhatsApp, deliberately.
- **Moderation queue** — a tracking-only radar over four signals that are
  otherwise easy to miss: groups with too few admins to stay manageable if
  one leaves (admin-coverage gaps), members who've never posted in any
  group, sudden join bursts, and groups nearing their member cap or sitting
  on pending join requests. Same posture as renewals: Communeer only
  surfaces candidates for a human to check in WhatsApp, never acts on its
  own. Dismissing an item hides it only until its underlying signal
  genuinely gets worse again (e.g. a dismissed admin-coverage gap resurfaces
  once the admin count drops further, not on every unrelated sync).
- **CSV export** for both the community-wide and per-group member lists,
  safe against spreadsheet formula injection (member display names are
  synced verbatim from WhatsApp, so they're fully attacker-controlled).
- **Audit log** of every sync and admin action, filterable by action,
  target type, and date range.

## What it deliberately does *not* do (yet)

No automated messaging, no automatic member removal, no inactivity-based
"cleanup" — see [`poc/whatsapp/FINDINGS.md`](poc/whatsapp/FINDINGS.md) and
the renewals feature's own in-app explanation for why. This is intentional:
automating writes to a real WhatsApp account carries real risk (rate
limiting, account flags), so every destructive or messaging capability is a
conscious, separate decision, not a default.

## Quickstart — Docker (recommended)

```bash
cp .env.example .env    # set SESSION_SECRET_KEY, SEED_ADMIN_USERNAME/PASSWORD, WPPCONNECT_SECRET_KEY
docker compose up -d
```

Open <http://localhost> and log in with the `SEED_ADMIN_USERNAME`/
`SEED_ADMIN_PASSWORD` from `.env`. Runs against mock data by default —
see [Connecting a real WhatsApp account](#connecting-a-real-whatsapp-account)
to use it for real.

`docker-compose.yml` builds both images from source by default. Tagged
releases also publish pre-built images to the GitHub Container Registry
(`ghcr.io/friedjof/communeer-backend`, `ghcr.io/friedjof/communeer-frontend`)
if you'd rather pull instead of build — see the
[Releases](../../releases) page for available tags.

## Quickstart — local dev (no Docker)

Backend (FastAPI, uv-managed, port 8000):

```bash
cd backend
cp .env.example .env
uv sync
uv run uvicorn communeer.main:app --reload
```

Migrations, the seed admin user, and an initial sync of the mock WhatsApp
data all run automatically on startup — nothing else to set up.

Frontend (React + Vite, pnpm-managed, port 5173, proxies `/api` to the
backend):

```bash
cd frontend
pnpm install
pnpm dev
```

Open <http://localhost:5173> and log in with `admin` / `changeme123` (from
`backend/.env.example`, unless you changed it).

## Connecting a real WhatsApp account

Set `WHATSAPP_PROVIDER=wppconnect` in `.env`, then `docker compose up -d`.
Open the dashboard, go to the WhatsApp setup page, and scan the QR code with
an account that administers at least one WhatsApp Community. The
[`wppconnect`](https://github.com/wppconnect-team/wppconnect-server)
container is never exposed to the host — only the Communeer backend talks
to it, over the internal Docker network.

## Repo layout

```text
backend/    FastAPI + SQLAlchemy + Alembic, independent uv project
frontend/   React + Vite + TanStack Router/Query/Table + Recharts, pnpm project
poc/        throwaway WPPConnect-capability spikes, not part of the app
```

## Architecture

```text
Browser → Caddy (TLS + reverse proxy)
              ├── React SPA (static)
              └── FastAPI backend → SQLite
                                   → WhatsAppProvider (mock | wppconnect)
                                          → WPPConnect Server (internal only)
```

WhatsApp access is fully abstracted behind a `WhatsAppProvider` interface
(`backend/communeer/providers/whatsapp/`) — nothing else in the codebase
talks to WPPConnect directly, so a future integration (or a fix to the
current one) only touches that one module.

## Development

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for setting up a dev environment,
running tests/lint, and submitting a pull request. Every push and PR runs
the same checks in CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml));
tagged releases (`vX.Y.Z`) publish Docker images to GHCR and cut a GitHub
release automatically ([`.github/workflows/release.yml`](.github/workflows/release.yml)).

## Security notes

- **`/docs`, `/redoc`, and `/openapi.json` are live and unauthenticated** at
  the FastAPI level — `backend/communeer/main.py`'s `FastAPI(...)` call sets
  no `docs_url`/`redoc_url`/`openapi_url` override. Every functional route
  under them still requires a session cookie, but the route list and schema
  themselves are visible to anyone who can reach the backend. This is a
  deliberate choice for admin convenience on a self-hosted tool that
  normally sits behind Caddy/Docker's internal network, not an oversight.
  To lock it down for an internet-facing deployment, set
  `docs_url=None, redoc_url=None, openapi_url=None` in that same
  `FastAPI(...)` call.
- See [`SECURITY.md`](SECURITY.md) for how to report a vulnerability — this
  app handles real member phone numbers and a real, connected WhatsApp
  account.

## License

[AGPL-3.0](LICENSE) — if you run a modified version of Communeer as a
network service, you're required to make that modified source available to
its users.
