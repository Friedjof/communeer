import logging
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from communeer.audit.router import router as audit_router
from communeer.auth.router import router as auth_router
from communeer.auth.seed import seed_admin_user
from communeer.communities.router import router as communities_router
from communeer.config import get_settings
from communeer.db import SessionLocal
from communeer.errors import register_exception_handlers
from communeer.groups.router import router as groups_router
from communeer.members.router import router as members_router
from communeer.providers.whatsapp import get_provider
from communeer.providers.whatsapp.base import (
    WhatsAppConnectionState,
    WhatsAppNotConnectedError,
)
from communeer.renewals.router import router as renewals_router
from communeer.sync.router import router as sync_router
from communeer.sync.service import sync_community
from communeer.whatsapp_status.router import router as whatsapp_status_router

# Without this, `logger.exception(...)` calls throughout this codebase
# (e.g. errors.py's unhandled-exception handler) are silently discarded —
# uvicorn's own default logging config only wires handlers for its own
# `uvicorn.*` loggers, not the root logger, so an app-level logger with no
# handler of its own produces no output at all. Confirmed the hard way: a
# live 500 in Docker showed nothing in `docker compose logs` until this was
# added.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

logger = logging.getLogger("communeer")

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _run_migrations() -> None:
    alembic_cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    command.upgrade(alembic_cfg, "head")


def _seed_and_prime_data() -> None:
    """Seed the admin user, then make sure every provider community has at
    least one synced snapshot in the DB — so `GET /communities` already has
    something to show right after a fresh boot, without requiring the
    frontend to know to call `POST /sync` first. Cheap and idempotent
    against the deterministic mock provider, so it's safe to run on every
    startup.
    """
    db = SessionLocal()
    try:
        seed_admin_user(db)
        provider = get_provider()

        connection_status = provider.get_connection_status()
        if connection_status.state != WhatsAppConnectionState.connected:
            # Real (wppconnect) sessions start out unauthenticated until a
            # human scans a QR code via /whatsapp/connect — calling
            # get_communities() here would just raise. Mock's status is
            # always "connected", so this is a true no-op for mock mode.
            logger.info(
                "Skipping community priming at startup: WhatsApp provider is not "
                "connected (state=%s).",
                connection_status.state.value,
            )
            return

        try:
            for provider_community in provider.get_communities():
                sync_community(db, provider, provider_community.wa_id)
        except WhatsAppNotConnectedError:
            # A real session can drop mid-loop; don't let that crash the
            # whole lifespan — whatever was already synced stays synced.
            logger.warning(
                "WhatsApp session disconnected while priming communities at "
                "startup; continuing with a partially-synced state."
            )
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Idempotent by design: safe to run every time the process starts,
    # whether that's local `uvicorn --reload` or the Docker CMD.
    try:
        _run_migrations()
    except Exception:
        logger.exception("Failed to run database migrations on startup")
        raise

    _seed_and_prime_data()
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title="Communeer API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    api_prefix = "/api/v1"
    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(communities_router, prefix=api_prefix)
    app.include_router(groups_router, prefix=api_prefix)
    app.include_router(members_router, prefix=api_prefix)
    app.include_router(audit_router, prefix=api_prefix)
    app.include_router(sync_router, prefix=api_prefix)
    app.include_router(whatsapp_status_router, prefix=api_prefix)
    app.include_router(renewals_router, prefix=api_prefix)

    return app


app = create_app()
