PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
PIP_AUDIT_CACHE ?= /tmp/dnd-vtt-pip-audit

.PHONY: bootstrap dev-backend dev-frontend test test-backend test-frontend test-database build verify security-static security release-check test-e2e test-load test-database-replay acceptance

bootstrap:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install "pip==26.2"
	$(BIN)/python -m pip install -e ".[dev]"
	npm ci
	npm --prefix frontend ci

dev-backend:
	$(BIN)/uvicorn app.main:app --app-dir backend --reload --host 127.0.0.1 --port 8000

dev-frontend:
	npm --prefix frontend run dev

test: test-backend test-frontend

test-backend:
	$(BIN)/pytest

test-frontend:
	npm --prefix frontend run test

test-database:
	npx supabase db reset --local --no-seed
	npx supabase test db --local supabase/tests
	npx supabase db lint --local --level warning

build:
	$(BIN)/python -c "from app.main import app; assert app"
	npm --prefix frontend run build

verify:
	$(BIN)/python -c "import os; assert all(os.getenv(k) for k in ('VTT_TEST_DATABASE_URL', 'VTT_TEST_REDIS_URL')), 'Explicit local PostgreSQL/Redis test services required; no skips'"
	$(BIN)/ruff check backend tests scripts
	$(BIN)/mypy backend scripts
	VTT_ACCEPTANCE_REQUIRED=1 $(BIN)/pytest
	npm --prefix frontend run typecheck
	npm --prefix frontend run test
	npm --prefix frontend run build
	$(BIN)/python scripts/validate_project.py --manifest .ai-studio/project.yaml
	@for spec in docs/specs/VTT-*.md; do $(BIN)/python scripts/validate_spec.py --spec "$$spec" || exit; done

security-static:
	$(BIN)/python scripts/acceptance_scan.py

security: security-static
	$(BIN)/pip-audit --cache-dir $(PIP_AUDIT_CACHE)
	npm --prefix frontend audit --omit=dev

release-check: verify security
	docker compose config --quiet

test-e2e:
	$(BIN)/python tests/e2e/run.py --browser-only

test-load:
	$(BIN)/python tests/e2e/run.py --load-only

test-database-replay:
	$(BIN)/python scripts/acceptance_database.py

acceptance: verify security test-database-replay test-e2e test-load
