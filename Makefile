BACKEND := cd backend && uv run
FRONTEND := cd frontend && npm

.PHONY: setup migrate seed demo backend frontend test lint check

setup:            ## install backend and frontend dependencies
	cd backend && uv sync
	$(FRONTEND) ci

migrate:          ## create/upgrade the schema (Alembic on Postgres, create_all on SQLite)
	$(BACKEND) python -m itk.cli init-db

seed: migrate     ## load fabricated demo subscribers and cached events
	$(BACKEND) python -m itk.cli seed

demo: seed        ## run the weekly pipeline offline; issues land in backend/.outbox/
	$(BACKEND) python -m itk.cli run-pipeline

backend:          ## API on :8000
	$(BACKEND) uvicorn itk.main:app --reload --port 8000

frontend:         ## Next.js on :3000 (proxies /api to the backend)
	$(FRONTEND) run dev

test:
	$(BACKEND) pytest
	$(FRONTEND) test

lint:
	$(BACKEND) ruff check .
	$(BACKEND) ruff format --check .
	$(BACKEND) mypy
	$(FRONTEND) run lint
	$(FRONTEND) run typecheck

check: lint test
