# ADR-002 — Realtime authority

## Status

Accepted.

## Decision

Postgres stores durable room and scene state. FastAPI validates commands and
appends durable events in the same transaction. Redis carries ephemeral
presence, WebSocket tickets, drag previews, rate limits, and cross-process
fan-out.

Supabase Realtime is not used for gameplay mutation. Clients send idempotent
commands with an expected aggregate version and recover through snapshot plus
missed events.

## Consequences

- Redis loss cannot erase confirmed gameplay state.
- Reconnect is deterministic.
- High-frequency drag previews remain ephemeral; the final transform is the
  only durable mutation.
