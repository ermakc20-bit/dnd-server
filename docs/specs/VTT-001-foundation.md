# VTT-001 — Production foundation

## Goal

Create a reproducible greenfield foundation for an Owlbear Rodeo 2.0-inspired,
map-first VTT with React, FastAPI, Supabase, Redis, and a server-authoritative
command model.

## Non-goals

- Implement the complete canvas, fog, turn engine, or legacy importer in this slice.
- Link or mutate hosted Supabase projects.
- Push, deploy, or create production secrets.
- Restore any legacy runtime.

## Users or callers

- GM creating rooms and scenes.
- Players joining rooms and controlling assigned tokens.
- Engineers extending the VTT through verified vertical slices.

## Current repo constraints

- Legacy code at `4940146faf83b144c9f36d9c79f52cceb7b13e5e` is preserved by tag.
- The original checkout had no reproducible dependency, test, CI, or migration contract.
- Docker is installed locally but the daemon is not currently available.
- Hosted Supabase credentials and projects are intentionally not configured.

## Requirements

- `FR-FOUNDATION-APP`: the repository exposes one FastAPI application and one React application.
- `FR-FOUNDATION-AUTH`: backend authentication verifies Supabase JWTs and never accepts client-selected authorization roles.
- `FR-FOUNDATION-HEALTH`: liveness and readiness endpoints expose machine-readable status.
- `FR-FOUNDATION-DATA`: a versioned Supabase migration defines private application data contracts.
- `FR-FOUNDATION-UI`: the frontend renders the authenticated VTT shell and centralizes Supabase configuration.
- `FR-FOUNDATION-DEV`: one documented command set covers development, tests, builds, and verification.
- `NFR-FOUNDATION-SECURITY`: secret and publishable configuration boundaries are explicit and tested.
- `NFR-FOUNDATION-QUALITY`: backend and frontend have deterministic unit tests, static checks, and CI gates.
- `NFR-FOUNDATION-OPS`: Docker and proxy definitions include health probes and no embedded credentials.
- `NFR-FOUNDATION-TRACE`: every acceptance criterion has deterministic evidence.

## Acceptance criteria

- [x] `AC-APP` covers `FR-FOUNDATION-APP`: backend import and frontend production build succeed.
- [x] `AC-AUTH` covers `FR-FOUNDATION-AUTH`: valid test JWTs pass and invalid issuer, audience, expiry, and signature cases fail.
- [x] `AC-HEALTH` covers `FR-FOUNDATION-HEALTH`: liveness succeeds and readiness reports dependency state without leaking secrets.
- [x] `AC-DATA` covers `FR-FOUNDATION-DATA`: the migration creates the private schema and required constraints in local Supabase.
- [x] `AC-UI` covers `FR-FOUNDATION-UI`: frontend tests render loading, unauthenticated, and authenticated shell states.
- [x] `AC-DEV` covers `FR-FOUNDATION-DEV`: README and Make targets work from a clean checkout.
- [x] `AC-SECURITY` covers `NFR-FOUNDATION-SECURITY`: secret scans and configuration tests show no server secrets in frontend output.
- [x] `AC-QUALITY` covers `NFR-FOUNDATION-QUALITY`: backend and frontend lint, type, test, and build gates pass.
- [x] `AC-OPS` covers `NFR-FOUNDATION-OPS`: Compose config renders without interpolation errors and images define health checks.
- [x] `AC-TRACE` covers `NFR-FOUNDATION-TRACE`: Development OS traceability validation passes.

## Evidence map

- `AC-APP`: `python -c 'from app.main import app'` and `npm run build`.
- `AC-AUTH`: `pytest tests/test_auth.py`.
- `AC-HEALTH`: `pytest tests/test_health.py`.
- `AC-DATA`: `make test-database` (reset, 13 pgTAP assertions, SQL lint).
- `AC-UI`: `npm run test -- --run`.
- `AC-DEV`: documented clean-install smoke run.
- `AC-SECURITY`: `make security-static` and configuration redaction tests.
- `AC-QUALITY`: `make verify`.
- `AC-OPS`: `docker compose config`.
- `AC-TRACE`: repository-local `scripts/validate_spec.py --spec docs/specs/VTT-001-foundation.md` output and `pytest tests/test_validation.py` negative fixtures; project manifest is checked by `scripts/validate_project.py --manifest .ai-studio/project.yaml` in `make verify`.

## Verification commands

- `make test-backend`
- `make test-frontend`
- `make build`
- `make verify`
- `make test-database`
- `make security-static`
- `docker compose config`
- `npx supabase db reset`

## Migration and rollback

This slice creates only a new schema. It does not import legacy data. Rollback
removes the new local environment or redeploys the prior immutable image. The
legacy tag remains available for audit and import development.


## F3 private room security boundary

The runtime room aggregate uses private `app.room_security_events`, introduced
by append migration `20261015120000_room_security_journal.sql`. Existing foundation
`public.security_events` and gameplay `app.room_events` retain their contracts.
The new table stores a real same-room participant, server time, a bounded safe
reason and one joined/opened/closed type, with no payload, credentials or session
identifier. Its room-bound foreign key prevents invented and cross-room actors.
Service-role ACL permits only select/insert and identity-sequence usage; anon and
authenticated Data API roles have no audit grants. RLS has only service read and
append policies. Membership joins append in the existing transaction; observed
authorized WebSocket open/close appends are durable and independent of gameplay
versions/cursors/history/export. HTTP reads require current MANAGE_ROOM.

The migration leaves the previous ten DDL files immutable. The dedicated schema
suite `supabase/tests/room_security_journal.sql` checks private access, safe columns,
server time, actor FK and no gameplay version/cursor effect. Runtime proof is
actual HTTP joins and authorized socket lifetime in
`tests/test_room_security_journal.py` and
`tests/realtime/test_presence_security_journal.py`; inserting an audit fixture
row alone is not evidence of runtime audit. Fresh replay uses a new owned local
database with exact finally drop/read-back, never an existing database reset.
