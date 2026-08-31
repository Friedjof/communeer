.PHONY: dev dev-backend dev-frontend

# Runs backend and frontend dev servers together; Ctrl+C stops both.
dev:
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	cd backend && uv run uvicorn communeer.main:app --reload

dev-frontend:
	cd frontend && pnpm dev
