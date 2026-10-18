# ADR-006 — Provider-neutral transfer and authorized realtime

## Status

Accepted; implemented by VTT-004, 006–008; complements ADR-002.

## Decision

PostgreSQL is durable authority; Redis stores only ephemeral transport state.
HTTP and WS share command handling. Reconnect re-resolves access and supplies a
current role-filtered snapshot plus allowlisted event summaries. Backoff remains
bounded while retries continue until success, revocation or client close.

The private Storage adapter owns put/get/delete/sign operations. A ZIP v1 manifest
contains bounded JSON and actual asset bytes with MIME, sizes and SHA-256.
Import validates the complete reference graph before writes, remaps all internal
IDs and creates an independent campaign atomically. Accounts, sessions,
memberships, invites, PINs, signed URLs and provider authority are excluded.
Historical actors restore as removed placeholders. Optional history is safe and
immutable; imported history grants no undo authority.

## Consequences and evidence

Per-recipient fog/hidden visibility precedes geometry hit testing. Export does
not silently omit unavailable assets. Durable job receipts, cancellation and
scoped newly written blob cleanup preserve truthful outcomes; universal remote
write completion under provider crashes is not claimed.
`tests/realtime`, `tests/scene_tools`, `tests/ability_geometry` and
`tests/campaign_transfer` cover these seams. Native acceptance checks raster bytes,
independent resources/new IDs and confirmed geometry after a roundtrip. Local
MemoryStorage and loopback latency do not establish hosted/WAN reliability.
