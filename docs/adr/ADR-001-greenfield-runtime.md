# ADR-001 — Greenfield runtime

## Status

Accepted.

## Decision

Use one FastAPI backend and one React frontend. Preserve the previous source in
Git history and the `legacy-4940146` tag instead of carrying broken legacy
runtimes into the new source tree.

Supabase provides Auth, Postgres, and Storage. FastAPI remains the only gameplay
authority. React may call Supabase Auth and approved Storage flows but cannot
write gameplay tables through the Data API.

## Consequences

- New behavior is built as independently verifiable vertical slices.
- Legacy data requires a dedicated, idempotent importer.
- Production authorization is enforced in backend services and database
  constraints, not browser-supplied metadata.
