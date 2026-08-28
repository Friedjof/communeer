FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

FROM base AS builder
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev
COPY communeer ./communeer
COPY migrations ./migrations
COPY alembic.ini ./
COPY README.md ./
RUN uv sync --frozen --no-dev

FROM base AS runtime
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
# Migrations + admin seed + initial community sync all run in main.py's
# lifespan on every boot (idempotent), so the CMD only needs to start the app.
CMD ["uvicorn", "communeer.main:app", "--host", "0.0.0.0", "--port", "8000"]
