# ADR-004 — Campaign ownership and room aggregate

## Status

Accepted; implemented by VTT-001–004.

## Decision

A campaign owns persistent material; rooms are its live tables. Each room is the
command aggregate. FastAPI applies room lock, current Participant authorization,
expected version and command receipt before changing canonical state. State,
immutable event and receipt commit in one PostgreSQL transaction. Generated IDs
and acknowledged state come from persisted rows, never an echoed client request.

## Consequences and evidence

A single SceneService command path delegates cards, imports, fog, annotations,
dice and geometry to domain handlers. Redis loss cannot erase acknowledged state.
Duplicate receipts and stale versions are explicit results. Player delivery uses
current authorized projections rather than raw event payloads.
`tests/scenes/test_commands.py`, `tests/cards/test_cards.py`, import confirmation
and the HTTP/WS acceptance smoke verify these boundaries. Foundation chat/turn
tables do not create product requirements or an alternative state engine.
