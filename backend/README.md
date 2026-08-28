# Communeer backend

FastAPI + SQLAlchemy + Alembic API for the Communeer WhatsApp-community admin
dashboard. WhatsApp access is abstracted behind a `WhatsAppProvider`
interface (`communeer/providers/whatsapp/`) with two implementations:
`MockWhatsAppProvider` (deterministic fixture data, the default) and
`WppconnectProvider` (a real WPPConnect Server-backed session, opt-in via
`WHATSAPP_PROVIDER=wppconnect`).

## Quickstart

```bash
uv sync
cp .env.example .env   # adjust SESSION_SECRET_KEY etc. as needed
uv run alembic upgrade head
uv run uvicorn communeer.main:app --reload
```

API docs: http://localhost:8000/docs

## Tests

```bash
uv run pytest -q
```
