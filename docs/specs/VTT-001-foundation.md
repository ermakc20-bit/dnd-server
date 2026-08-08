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
- `AC-TRACE`: Development OS `validate-spec.mjs` output.

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
