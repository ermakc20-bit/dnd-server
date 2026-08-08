# DnD VTT v2

Greenfield, map-first virtual tabletop inspired by the fast room/scene workflow
of Owlbear Rodeo 2.0. This repository intentionally replaces the legacy
prototype runtime preserved by the `legacy-4940146` tag.

## Architecture

- React/TypeScript UI; PixiJS will own the scene renderer.
- FastAPI validates every gameplay command.
- Supabase provides Auth, Postgres, and Storage.
- Redis is ephemeral: tickets, presence, drag previews, fan-out, and limits.
- Durable room and scene state always lives in Postgres.

The current implementation is the production foundation slice. It provides a
verified Supabase JWT boundary, health endpoints, the authenticated VTT shell,
versioned schema work, CI, and container definitions. Scene mutation is the
next vertical slice.

## Prerequisites

- Python 3.13 or 3.14
- Node.js 20+
- Docker-compatible runtime for local Supabase and Compose checks

## Setup

```bash
cp .env.example .env
make bootstrap
```

Replace only local values in `.env`. Never commit it. The browser receives only
`VITE_SUPABASE_URL` and the publishable key; it must never receive a secret or
service-role key. `VTT_SUPABASE_SERVICE_ROLE_KEY` is server-only and is required
for private Storage operations.

## Run

```bash
make dev-backend
make dev-frontend
```

Backend: `http://127.0.0.1:8000`
Frontend: `http://127.0.0.1:5173`

## Verify

```bash
make verify
make security
docker compose config
```

Local Supabase is initialized through the pinned project dependency:

```bash
npx supabase start
npx supabase db reset
```

Database migration, security-boundary, and trigger checks run with:

```bash
make test-database
```

The local Supabase stack is development-only and must never be exposed to the
internet.

## Source of truth

- Product requirements: `docs/specs/`
- Architectural decisions: `docs/adr/`
- Development contract: `AGENTS.md` and `.ai-studio/project.yaml`
- Legacy migration evidence: `docs/migrations/legacy-sqlite.md`
