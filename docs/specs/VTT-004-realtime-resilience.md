# VTT-004 — Realtime, commands and recovery

## Goal

Keep the existing map-first room and native cards synchronized for a GM and five
players. PostgreSQL remains authoritative; losing Redis or a transport connection
must not lose acknowledged state or replay a command twice.

## Requirements

- `FR-RT-TICKET`: authenticated, room/participant-bound, single-use WebSocket tickets.
- `FR-RT-SYNC`: authorized snapshot and compact missed-event descriptors; no raw
  card payloads, hidden fields, hidden tokens or inactive scenes for players.
- `FR-RT-COMMAND`: the existing SceneService owns all commands, room locks, versions,
  receipts and transactional state/event writes; notify only after commit.
- `FR-RT-EPHEMERAL`: Redis owns only tickets, fan-out notifications, presence,
  throttles and expiring drag previews; release submits one durable transform.
- `FR-RT-RECOVERY`: retain the last confirmed projection read-only, show last sync,
  reconnect with bounded backoff and atomically replace state before enabling input.
- `NFR-RT-ACCESS`: recheck membership and visibility before every delivery; revoked
  access closes the socket and removes the scene/card projection from the screen.
- `NFR-RT-LATENCY`: measure local reconnect for 1+5; p95 must be at most 10 seconds.

Autopilot mapping: R04/R08/R09/G18/G19 to the playable authoritative table,
G06/G16/G26 to resilience, G22/G28 to room/object authorization, G05 to the 1+5
local contour. Five full group sessions, hosted infrastructure, public availability,
offline mutation queues and later table tools are not claimed by this slice.

## Acceptance criteria

- [x] `AC-TICKET` covers `FR-RT-TICKET`: opaque ticket in first WS frame, 30-second
  Redis TTL, atomic GETDEL, room binding, no-store HTTP response and issue throttling.
- [x] `AC-SYNC` covers `FR-RT-SYNC`: an existing authority snapshot plus safe event
  invalidations bounded by its cursor; a matching room version is verified under
  the room share lock, with fresh participant authorization. Over 1000 descriptors
  are compacted explicitly; the full current snapshot still covers all state.
- [x] `AC-COMMAND` covers `FR-RT-COMMAND`: duplicate and stale commands retain the
  existing behavior; HTTP and WS paths converge on the same transaction owner.
- [x] `AC-EPHEMERAL` covers `FR-RT-EPHEMERAL`: preview expires after 2 seconds,
  never increments room version or creates an event; Redis errors after commit
  do not turn an accepted durable command into a failed save.
- [x] `AC-RECOVERY` covers `FR-RT-RECOVERY`: read-only during failure, fresh ticket,
  full atomic resync, single pending-command retry with the original ID; no queue.
- [x] `AC-ACCESS` covers `NFR-RT-ACCESS`: revoke is noticed by fan-out or periodic
  database recheck; 4403 clears scene, cards, asset URLs and pending callbacks.
- [x] `AC-LATENCY` covers `NFR-RT-LATENCY`: six authenticated protocol clients
  reconnect concurrently against local PostgreSQL and Redis, with measured results.

## Evidence map

- `AC-TICKET`: `tests/realtime/test_transport.py` ticket unavailable/single-use/
  room binding/cache-policy/rate-limit tests (real local Redis for integration).
- `AC-SYNC`: `test_ticket_is_single_use_room_bound_and_sync_is_filtered` checks
  that hidden token/card/notes/field strings never appear in the WS frame.
- `AC-COMMAND`: `test_two_clients_commands_duplicates_stale_and_reconnect`, plus
  the accepted scene/card transaction and canonical event tests.
- `AC-EPHEMERAL`: `test_drag_preview_is_ephemeral_filtered_and_revoke_closes_socket`;
  real rendered drag advanced version 5 to 6 and produced exactly one item.update.
- `AC-RECOVERY`: `frontend/src/features/realtime/Realtime.test.tsx` checks no
  control before resync, last-sync/read-only, replacement version and revoked view;
  the prolonged-outage regression advances 60 seconds beyond ten failed attempts,
  then restores the server and verifies automatic recovery only after a new sync;
  `LostAcknowledgement.test.tsx` retains the original two-requests/one-ID assertions.
- `AC-ACCESS`: actual HTTP participant revoke in the integration test; a real
  guest browser lost both the canvas and open card immediately after HTTP revoke.
- `AC-LATENCY`: isolated loopback harness `/private/tmp/dnd-vtt-ticket04-check`,
  `runtime_probe.py`; no harness, auth fixture or debug route is shipped in product.

## Local runtime results — 2026-10-11

Two rendered Chromium/IAB clients used the real SceneExperience, Pixi renderer,
HTTP APIs, WebSockets, JWT/guest-cookie resolvers, PostgreSQL and Redis. The GM saw
two tokens; the guest saw one. A scene rename, a guest drag and a new native card
arrived on the other screen. GM-only notes were absent from the guest card.

The dedicated Redis container was stopped and started, not mocked. Both screens
became read-only and retained their prior version and last-sync time. A scene
command committed successfully while Redis was down. After recovery both screens
received the newer snapshot and resumed control. Screenshots and harnesses remain
under `/private/tmp`, outside the product source tree.

The final-source protocol probe measured 30 reconnects (five concurrent rounds of
one GM and five distinct guests): p95 **0.0656 s**, maximum **0.0667 s**. Timing starts
before closing the old sockets and includes new HTTP ticket, WS handshake and first
authorized snapshot. This is protocol latency, not a frontend-animation or WAN SLO.
Redis-restart recovery is measured from starting the dedicated Redis service to the
first authorized snapshot: six clients, nearest-rank p95 **0.3853 s**. It is not a
claim that an intentional outage lasts zero.

Full `make verify VENV=/private/tmp/dnd-vtt-ticket01-venv` passed in the
content-matching isolated copy: **94 backend + 33 frontend tests**, coverage
**90.86%** (baseline 89 + 31, 91.56%); lint, mypy, TypeScript, build and repository
traceability checks passed. `VTT_TEST_DATABASE_URL` points only to the existing
loopback test database; `VTT_TEST_REDIS_URL=redis://127.0.0.1:56379/0` points only
to the disposable T04 container. The build retains the existing large-chunk warning.

## Public interfaces

- `POST /api/v1/rooms/{room_id}/realtime/ticket` with existing bearer/cookie identity
  returns `{ticket:string, expires_in:30}`, `Cache-Control:no-store`; 503
  `realtime_unavailable`, 429 `rate_limited`. At most 20 tickets per actor/30 seconds.
- `WS /api/v1/rooms/{room_id}/realtime/ws` accepts no query parameters and checks
  Origin against configured frontend origins when present. First frame within
  5 seconds: `{type:"subscribe", ticket:string, cursor:int>=0}`.
- Server: `{type:"sync", snapshot:SceneProjection, events:ProjectedEvent[],
  events_compacted:boolean}`; `ProjectedEvent={cursor,aggregate_version,
  type:"scene.changed"|"cards.changed"}`. No raw payload or historical secret.
- Client: `{type:"command",command:Command}` -> server
  `{type:"command_result",result:CommandResult}`; existing HTTP command unchanged.
- Client `{type:"resync"}` requests a new atomic sync; `{type:"ping"}` requests a
  heartbeat. Server `{type:"heartbeat",presence_count:int|null}` counts distinct active actors;
  null means the lease source is unavailable.
- Client/server `{type:"preview",item_id:UUID,x:number,y:number,clear?:boolean}`;
  positions are finite and bounded; send and recipient visibility are rechecked.
- Close codes: 4400 invalid frame, 4401 invalid/used ticket, 4403 access revoked/
  origin forbidden, 4429 frame rate limit, 1013 ephemeral service unavailable.
- `connectRoom(options:RealtimeOptions):RoomConnection`; connection exposes
  `refresh():Promise<boolean>`, `reconnect()`, `preview(ItemPreview|null)`, `close()`.
  Backoff 250 ms exponential capped at 3 s; automatic retries continue until the
  client closes or access is revoked. Manual refresh and browser online may retry
  immediately. Heartbeat timeout is 12 s.

## Limitations

Fan-out sends full role-filtered snapshots rather than raw event deltas. A bounded
one-second PostgreSQL recheck repairs dropped notifications and detects revocation.
No claims are made for multi-region latency, hosted Supabase, Safari/Firefox, five
full sessions or the future 10-client/500-object realtime load acceptance gate.

## Final branch repair: credential lifetime and shared scenes

Registered room resolution retains the verified JWT deadline as server-only
`Participant.authorization_expires_at`, excluded from public identity DTOs.
The single-use Redis ticket carries that deadline separately from the actor;
consumption after expiration and an already-open connection after expiration
close with4401 before sync, command processing, preview or heartbeat delivery.
A new valid JWT can obtain a fresh ticket. Guest expiry and membership remain
checked through the existing PostgreSQL authority.
The command transaction also rechecks the private deadline after acquiring its
room locks and before commit; a command queued across expiration creates no
accepted durable mutation, event or receipt. The public lock-wait regression
verifies the command reached the lock, expires the JWT, then checks SQL state
and successful fresh-JWT re-entry.

Scenes remain campaign-wide. Commands acquire all active campaign room locks
in ID order before reading optimistic versions or changing shared scene state.
Scene content mutations advance every room displaying that scene; creation and
rename also advance rooms whose campaign scene list changed. Activation, cards
and dice retain room-local semantics. One real author, immutable origin event
and command receipt remain stored; no copied events or fabricated actors exist.
Recipient cursors include eligible same-campaign shared scene events. Their
public signal is payload-free `scene.changed` with the recipient's current
version, and their snapshots use the recipient's existing visibility policy.
HTTP and WS commits wake campaign subscribers; periodic PostgreSQL checks also
compare versions to recover scene-list changes or lost wakeups. Stale versions
cannot overwrite shared scene state.

Public repair evidence: `tests/realtime/test_branch_repair.py` uses actual
RS256 verification for both expiration paths and valid re-entry, and two room
clients over HTTP/WS for token/grid/fog/annotation/undo/geometry convergence,
room-local cards, filtered hidden content and stale rejection. Local Origin
defaults are tested against the documented loopback address and a foreign
Origin. This repair does not extend hosted or real-session acceptance.


## F3 accepted recovery and room security contract

D15 maps R04/R09/G06/G22/G26/G28 to observable reconnect and private room audit.
`ConnectionDiagnostics={attempt:number,lastConfirmedSyncAt:string|null,
failureStartedAt:number|null}` accompanies transport state. A new connect attempt
increments the real attempt counter; exponential backoff has its own capped
exponent. Retries, socket open and heartbeat preserve the start of a continuous
failure and the last confirmed sync. Only a complete authorized sync resets the
failure, replaces the projection and enables commands.

After 30 seconds without a confirmed sync, a GM can download the last local
confirmed scene projection as a reference JSON. At 29.999 seconds the control
is absent. `schema_version=1`, `confirmed_at`, `room_id`, `aggregate_version`,
`event_cursor`, scenes/items/fog/annotations/ability presentations are explicitly
projected, including explicit nested fields. No auth/session identity, invitation,
PIN, signed URL, pending command, preview, raw event or SDK object is copied.
Missing asset bytes, cards and the full campaign are explicitly outside this
reference file. No fetch, upload or gameplay command is caused by the download.
Guests have no download control. Room/identity/revoke clears it; a full resync
replaces it. With no confirmed projection the GM sees an honest empty state.

`GET /api/v1/rooms/{room_id}/participants/status` is MANAGE_ROOM-only and returns
`{participants:[{id,display_name,role,connection_status,assigned_tokens}]}`;
`connection_status=connected|disconnected|unknown`; token entries are
`{id,name,scene_id,scene_name}`. Deleted tokens, cards and scenes are excluded.
Multiple alive socket leases for one actor count once; Redis failure means
unknown. Lease expiry is not claimed as an exact observed network-disconnect
time. The existing identity participant endpoint remains compatible.

`GET /api/v1/rooms/{room_id}/security-events?limit=50&before_id=N` is
MANAGE_ROOM-only, no-store, limit 1..100 with descending ID keyset pagination.
It returns `{events:[{id,participant_id,display_name,type,occurred_at,reason}],
next_before_id:number|null}`. The server rechecks current GM membership and
private JWT lifetime before delivering either summary. The native participant
panel shows assignments/status, safe audit rows, bounded older pages, source
errors and ignores late results after identity/room change or revoke.

Security event types are `participant.joined`, `connection.opened` and
`connection.closed`. Reasons are `guest_join`, `registered_join`,
`authorized_socket` and `socket_closed_actor_connected|disconnected|unknown`.
Closing one socket while another lease lives never announces a full actor exit.
The append-only private `app.room_security_events` table has service read/insert
ACL and RLS; browsers cannot read or append through the Data API. Guest and
registered joins append within the actual membership transaction. Only authorized
observed sockets append open/close, including ASGI cancellation cleanup. No fake
participant, token/session/IP or payload is written. Restart reads committed SQL.
The table never participates in gameplay versions, cursors, undo, sync or ZIP.

Public evidence: `Realtime.test.tsx`, `EmergencySnapshot.test.ts`,
`RoomParticipants.test.tsx`, `tests/test_room_security_journal.py` and
`tests/realtime/test_presence_security_journal.py`; private schema defense:
`supabase/tests/room_security_journal.sql`. The source-controlled explicit local
Chrome entry is `tests/e2e/room_security_run.py`, using the existing native App,
JWT/JWKS and Storage primitives with exact synthetic UUID cleanup. This evidence
does not close real group-session, hosted/WAN or other-device acceptance.
