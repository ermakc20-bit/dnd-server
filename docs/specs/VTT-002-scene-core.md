# VTT-002 — Private map-first scene core

## Goal

Extend the accepted campaign and Participant foundation with a Russian-language
scene/table workflow: private user maps, calibrated square grid, tokens and one
server-authoritative command path. This is a functional slice of the existing UI,
not a redesign or a second application.

## Users or callers

- Registered GM preparing a table for 4–5 players.
- Registered or guest Participant controlling assigned visible tokens.
- Scene renderer consuming only a server-authorized projection.

## Constraints

FastAPI is the sole gameplay authority. Postgres holds command receipt, event
and state in one transaction. React never writes gameplay tables. Storage is
private; grants are server-authorized and expire after 60 seconds. Guest actors
remain Participants without fabricated auth users. Pillow 12.3.0 is the only new
dependency. No hosted data is used. Full verification and browser smoke run in
an isolated check-copy without personal `.env` files.

## Non-goals

- AI, card import, rules, voice, dynamic light, fog drawing, dice or undo.
- Realtime fan-out, automated reconnect or replay: these remain the next slice;
  this slice provides the durable command receipt, cursor and atomic projection.
- Full fulfilment of the five-session gate (G16), 20-minute promise (G19),
  regional reliability (G06), or all tablet/mobile product scenarios (G27).
- Hosted Storage/Auth acceptance, deployment or a measured FPS guarantee.

## Requirements

- `FR-SCENE-LIFECYCLE`: R04/R05/G02/G05/G18/G19 — a GM creates, renames and switches campaign scenes through the existing room workflow.
- `FR-SCENE-ASSETS`: R09/G18/D03 — JPEG/PNG/WebP/AVIF images up to 50 MiB undergo real server decoding and remain private.
- `FR-SCENE-RENDER`: R05/G18/G27 — PixiJS displays maps/tokens, pan/zoom, square grid, snap, units and accessible transform controls.
- `FR-SCENE-TOKENS`: G18/G22 — tokens create, duplicate, move, resize, rotate, lock and sort; assignment can be granted and revoked.
- `NFR-SCENE-ACCESS`: G22 — the sole access policy excludes hidden/unassigned items and their assets even through direct HTTP requests.
- `NFR-SCENE-STATE`: G06/G16/G26 — idempotent commands use expected version; state/event/receipt commit together; failed loads retain a read-only confirmed snapshot.
- `NFR-SCENE-CAPACITY`: G05/G18 — projection, renderer frame, viewport and hit testing preserve 500 visible objects functionally.
- `NFR-SCENE-TRACE`: R08/R09/D02 — narrow native callbacks integrate the accepted campaign/join flow; this spec and deterministic tests preserve evidence.

## Acceptance criteria

- [x] `AC-LIFECYCLE` covers `FR-SCENE-LIFECYCLE`: multiple named scenes persist and active scene changes through the public command seam.
- [x] `AC-ASSETS` covers `FR-SCENE-ASSETS`: real files of all four formats upload; invalid MIME, size, corruption and decompression bombs are rejected without deleting metadata.
- [x] `AC-RENDER` covers `FR-SCENE-RENDER`: viewport transforms round-trip, zoom anchors its cursor, hit testing accounts for rotation, and scene UI exposes calibration.
- [x] `AC-TOKENS` covers `FR-SCENE-TOKENS`: commands cover transforms, lock, layer, duplication and server-validated ownership; drag preview sends one durable move on release.
- [x] `AC-ACCESS` covers `NFR-SCENE-ACCESS`: actual HTTP credentials resolve Participant; role-filtered projections and private download grants reject hidden/foreign data.
- [x] `AC-STATE` covers `NFR-SCENE-STATE`: duplicates do not create second items/events; stale/invalid commands leave durable state unchanged; offline UI disables commands.
- [x] `AC-CAPACITY` covers `NFR-SCENE-CAPACITY`: tests construct and project 500 objects and exercise the last object's hit/preview without altering the snapshot.
- [x] `AC-TRACE` covers `NFR-SCENE-TRACE`: old campaign assertions stay intact; callbacks and App transition are tested; spec traceability validates.

## Evidence map

- `AC-LIFECYCLE`: `tests/scenes/test_commands.py::test_scene_command_contract[lifecycle]` and actual Postgres read-back through a new repository instance.
- `AC-ASSETS`: `tests/assets/test_assets_http.py::test_private_image_upload_and_role_scoped_download` parameterized over JPEG/PNG/WebP/AVIF, plus runtime encode/open/load in the isolated Pillow wheel.
- `AC-RENDER`: `frontend/src/renderer/viewport.test.ts`, `frontend/src/features/scene/SceneCanvas.test.tsx` and `frontend/src/renderer/PixiSceneRenderer.test.ts`; opaque private grants explicitly select the texture parser. The latter regression failed on the URL-only load call before the fix. Browser/WebGL smoke is a separate local harness, not jsdom GPU evidence.
- `AC-TOKENS`: command scenarios lifecycle/authorization and the SceneCanvas drag component test.
- `AC-ACCESS`: `tests/scenes/test_scene_http.py` exercises signed ES256 JWT and real guest cookie resolution; asset HTTP test rejects a hidden map's direct download.
- `AC-STATE`: command concurrency/validation scenarios, transactional Postgres schema and SceneExperience read-only component test; SceneCanvas restores confirmed geometry when transport loss disables edits. `supabase/tests/scenes.sql` verifies DB access/relations. `test_scene_command_contract[event_scene_create/event_item_create/event_item_update/event_item_duplicate]` compares accepted events to independent SQL read-back and the public projection, including generated IDs and snapped transforms; repeating each command preserves its receipt, cursor, state and single event. All four regressions failed before repair because events stored the raw client payload instead of saved values, then passed after repair. Hidden event snapshots remain server-internal and are absent from the guest projection.
- `AC-CAPACITY`: `test_scene_command_contract[500]`, viewport 500-object hit test and SceneCanvas 500-object renderer-frame test. On 2026-10-11 the resumed local Chromium/WebGL2 smoke independently rendered 500 visible objects (one private map and 499 tokens) through FastAPI, Postgres and MemoryStorage. At 1440×1100, zoom, keyboard pan, reset and the last token's drag remained functional. During drag, durable version/accepted-command/event counts stayed 501/501/501; release sent exactly one `item.update`, and independent SQL read-back returned 502/502/502 with snapped coordinates (1408, 1152). Reload preserved the 500-object projection and confirmed position. The successful post-fix page reported zero console errors/warnings; screenshot `ticket02-runtime-500-drag.png` was inspected outside the application repository. This is functional runtime evidence, not an FPS benchmark or hosted-provider acceptance.
- `AC-TRACE`: `frontend/src/features/campaigns/CampaignExperience.test.tsx`, `frontend/src/App.test.tsx`, `make verify`, `scripts/validate_spec.py --spec docs/specs/VTT-002-scene-core.md` and `git diff --check`.

## Public interfaces

`GET /api/v1/rooms/{room_id}/scene?cursor=0 -> SceneProjection` gives current
version/cursor, actor session ID, authorized scenes/items and capability flags.
It deliberately does not serialize raw events or inactive scenes to players.
The optimistic aggregate is the room: event.aggregate_id equals room_id and
aggregate_version matches rooms.scene_version; scene_id identifies the affected scene.

Accepted event payloads are server-internal after-images read from the saved rows
inside the same transaction: scene commands use `{scene_id, scene}` and item
commands use `{scene_id, item}`. `scene` contains
`id,name,width,height,grid_size,grid_enabled,snap_enabled,unit_size,unit_label`;
`item` contains `id,kind,name,asset_id,x,y,width,height,rotation,z_index,visibility,
is_locked,owner_participant_id`. UUIDs are JSON strings. The generated duplicate ID
and the post-snap transform belong to the resulting item, not the original request.
Per-viewer `can_transform` is not event state. Event type and aggregate version
remain in the existing event envelope. Raw events are never returned by the scene
projection API; future fan-out must authorize and project these private snapshots.

`POST /api/v1/rooms/{room_id}/scene/commands -> CommandResult` accepts the shared
command envelope and scene.create/rename/activate/grid, item.create/update/duplicate.
Registered actor_session_id is Participant.id; guest actor_session_id is its
guest_session_id. The server verifies it against resolved credentials.

`POST .../assets/prepare -> AssetMetadata` creates pending metadata; `PUT
.../assets/{id}/content` validates bytes before a server-only Storage write;
`GET .../assets/{id}/download -> {url, expires_in:60}` reauthorizes every grant.
The test adapter enforces the same authorization at these APIs and short-lived
bearer grants; it is not proof of hosted provider integration.

`CampaignHome.onOpenRoom?(room: RoomSummary): void` and
`GuestJoin.onSession?(session: GuestSession): void` are the only campaign UI changes.

## Migration and rollback

`20261011125943_scene_core.sql` was generated by `supabase migration new
scene_core`. It migrates scenes toward campaign ownership, adds room aggregate
versions, command receipts, private asset status and Participant ownership.
Old assets remain pending metadata until validated. A foundation asset shared
across campaigns gets separate pending metadata IDs; additional copies preserve
the original source key internally and require a new upload, not an implicit
Storage copy. Shared-map forward migration is rehearsed by
`tests/scenes/test_migration.py` inside isolated namespaces and rollback.
Direct app-schema grants
remain revoked and RLS enabled. Local SQL tests run in the isolated disposable
Postgres fixture; schema migration rehearsal uses isolated namespaces and rollback.
After runtime fixture cleanup, all local pgTAP suites passed (46 assertions).
The live fixture schema was compared with a rollback-only replay of all current
migrations: 154 columns, 123 constraints, 44 indexes, 15 table RLS/grant definitions
and the private bucket matched. This fixture has no Supabase migration ledger and
does not establish hosted migration history or provider compatibility.
No hosted migration is applied. Rollback for a deployment remains a separately
authorized forward migration or prior immutable release, never a database reset.
