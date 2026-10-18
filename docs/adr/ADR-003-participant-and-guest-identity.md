# ADR-003 — Participant and guest identity

## Status

Accepted; implemented by VTT-001 and subsequent public authorization tests.

## Decision

A room Participant is the gameplay actor. Registered identity originates from a
verified Supabase-compatible JWT. A guest has a separate expiring opaque session
and HttpOnly cookie; no temporary auth account is manufactured. The server owns
room role and membership, never JWT user metadata. Participant and identity IDs
are distinct.

Invite tokens are unpredictable, stored as hashes and revocable. An optional PIN
and room lock gate new joins. Every HTTP/WS operation resolves current membership;
removal closes access while preserving historical event references.

## Consequences and evidence

Removed actors survive as inactive history, without renewed grants. Cookie scope,
room binding, restore, revoked invitations and cross-room mutation are covered by
`tests/test_campaigns.py`, `tests/test_campaigns_database.py` and
`tests/realtime/test_transport.py`. T10's local fixture uses actual RS256/JWKS
verification; it does not prove hosted sign-in, email or Supabase operations.
