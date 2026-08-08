PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin
PIP_AUDIT_CACHE ?= /tmp/dnd-vtt-pip-audit

.PHONY: bootstrap dev-backend dev-frontend test test-backend test-frontend test-database build verify security-static security release-check test-e2e

bootstrap:
	$(PYTHON) -m venv $(VENV)
	$(BIN)/python -m pip install --upgrade pip
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
	$(BIN)/ruff check backend tests scripts
	$(BIN)/mypy backend scripts
	$(BIN)/pytest
	npm --prefix frontend run typecheck
	npm --prefix frontend run test
	npm --prefix frontend run build
	node /Users/skaleush/.codex/skills/development-os/scripts/validate-project.mjs --manifest .ai-studio/project.yaml
	node /Users/skaleush/.codex/skills/development-os/scripts/validate-spec.mjs --spec docs/specs/VTT-001-foundation.md

security-static:
	! git grep -n -E "(sb_secret_[A-Za-z0-9_-]{20,}|BEGIN (RSA |EC )?PRIVATE KEY|eyJ[A-Za-z0-9_-]{20,}\\.[A-Za-z0-9_-]{20,}\\.)" -- ':!docs/**' ':!.env.example'
	! rg -n "sb_secret_[A-Za-z0-9_-]{20,}|BEGIN (RSA |EC )?PRIVATE KEY|eyJ[A-Za-z0-9_-]{20,}\\.[A-Za-z0-9_-]{20,}\\." frontend/dist

security: security-static
	$(BIN)/pip-audit --cache-dir $(PIP_AUDIT_CACHE)
	npm --prefix frontend audit --omit=dev

release-check: verify security
	docker compose config --quiet

test-e2e:
	@echo "Playwright suite is introduced with the first playable vertical slice."
	@exit 1
