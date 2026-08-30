# Contributing to Communeer

Thanks for considering a contribution. Communeer is a small, self-hosted
project, so this is intentionally short — proportionate process, not
enterprise boilerplate.

## Setting up a dev environment

See the README's
[Quickstart — local dev (no Docker)](README.md#quickstart--local-dev-no-docker)
section for the backend/frontend setup commands. Docker Compose
(`docker compose up -d`) is also fine for trying a change end-to-end.

## Before opening a PR

Run the same checks CI runs (see `.github/workflows/ci.yml`):

Backend (from `backend/`):

```bash
uv run pytest
uv run ruff check .
```

Frontend (from `frontend/`):

```bash
pnpm lint
pnpm build
pnpm test
```

All four should pass locally before you open a PR.

## Opening a pull request

Use the PR template (`.github/PULL_REQUEST_TEMPLATE.md`) — it asks for
what changed and why, how to test it, and a short checklist. Keep PRs
focused on one change; smaller PRs are easier to review and merge.

## Project conventions

Read [`AGENTS.md`](AGENTS.md) (repo root) before making a non-trivial
change — it documents this repo's real, established conventions: setup
commands, architecture (the `WhatsAppProvider` abstraction, the camelCase
API contract), and non-negotiable principles. The single most important
one: **Communeer never writes to WhatsApp automatically** — every
WhatsApp-side action (sending a message, removing a member, promoting an
admin) stays a manual, human step performed by you, in WhatsApp itself.

## Reporting bugs or security issues

Regular bugs: open a GitHub issue. Security vulnerabilities: see
[`SECURITY.md`](SECURITY.md) instead — please don't file those as public
issues.

## License

By contributing, you agree that your contribution is licensed under the
project's [AGPL-3.0](LICENSE).
