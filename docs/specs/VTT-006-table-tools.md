# VTT-006: Table tools and safe journal

## Goal and requirement traceability

R04/R05/R09/G07/G10/G16/G18/G22/G26/G27/D07 contribute to native map-first
table tools in the accepted command pipeline. T06 provides measurement and
simple annotations; ability-specific presentation remains T07. Durable actions
use the existing authority/version/receipt/event transaction and one new
migration, without dependencies.

## Requirements

- `FR-TABLE-FOG`: registered GM manually fills, resets and reveals bounded rectangle/polygon fog; authorized player projections and token grants follow the reveal geometry.
- `FR-TABLE-ANNOTATIONS`: line/arrow/label annotations follow player-owner versus GM permissions, everyone/gm_only visibility and tombstone deletion.
- `FR-TABLE-RULER`: ephemeral world-space measurement follows scene units and inverse viewport zoom/rotation; drafts remain scoped to the selected tool.
- `FR-TABLE-DICE`: bounded server-only NdS±K parsing creates immutable, idempotent public/private RollEvent results without eval or AI.
- `NFR-TABLE-JOURNAL`: allowlisted paginated journal entries show actor/time/action/result/visibility without raw payload or hidden data.
- `FR-TABLE-UNDO`: the latest not-yet-compensated forward gameplay action can be compensated with the exact room version, preserving history and explaining irreversible actions.
- `NFR-TABLE-INPUT`: disconnect preserves reading/pan/zoom/measurement while disabling durable tools until resync; mouse, keyboard and basic touch need no hover.
- `NFR-TABLE-SCOPE`: manual table tools preserve the existing authority and remain within D07, without dynamic light, walls, collision/turn engines, text chat or new dependencies.
- `NFR-TABLE-QUALITY`: public regressions, type/lint/build checks, local migration/SQL replay and actual desktop/tablet browser evidence support the slice.

## Acceptance criteria

- [x] `AC-TABLE-FOG` covers `FR-TABLE-FOG`: GM fills/resets fog and reveals a simple polygon with 3–32 bounded finite points; rectangles use four points. Maximum 100 reveal masks. GM sees all permitted objects; players receive only revealed footprints and authorized annotations. Background maps retain the existing asset policy. Hidden token asset grants and transforms are denied by the same geometry rule.
- [x] `AC-TABLE-ANNOTATIONS` covers `FR-TABLE-ANNOTATIONS`: Line/arrow/label annotations support everyone/gm_only. Players create and edit their own public annotations; GM edits any. Delete sets a tombstone. Maximum 500 live annotations; label text is at most 160 characters.
- [x] `AC-TABLE-RULER` covers `FR-TABLE-RULER`: The ephemeral ruler converts screen points through inverse zoom/rotation and computes Euclidean world distance × unit_size/grid_size. Tool drafts are keyed by tool so immediate keyboard input cannot reuse another tool's points.
- [x] `AC-TABLE-DICE` covers `FR-TABLE-DICE`: Server dice accepts NdS±K: 1–100 dice, 1–1000 sides, modifier ±10000. No eval or AI. Server RNG generates immutable RollEvent, and duplicate command IDs reuse the original result. Private rolls require a registered GM.
- [x] `AC-TABLE-JOURNAL` covers `NFR-TABLE-JOURNAL`: The journal exposes typed allowlisted entries, actor/time/action/result/visibility and authorized rolls. It excludes raw event payload and inverse state. Current and historical object visibility filter player entries; pagination scans at most 1000 events per response. Cache-Control is no-store.
- [x] `AC-TABLE-UNDO` covers `FR-TABLE-UNDO`: The latest not-yet-compensated forward event can be undone, with the exact current room version. Supported: every forward gameplay verb in the existing registry: scenes, plain/map/linked items, cards/resources, ability presentations, fog, annotations, confirmed import and dice. Compensation creates a new command/event/receipt; old events remain immutable. The latest not-yet-compensated forward action may be undone after safe compensation of newer actions. A live newer local/shared action blocks older undo; saved object versions count actual later immutable writes, and references are rechecked. Scene creation moves only an unused scene to campaign trash and restores the previous room pointer, including null. Import compensation soft deletes exactly its created IDs and retains terminal job/receipt and erased raw source. Dice compensation retains the original result with a visible revocation and never rerolls. Compensation itself is not undoable.
- [x] `AC-TABLE-INPUT` covers `NFR-TABLE-INPUT`: Disconnect cancels drafts and disables durable changes until resync; confirmed reading, pan, zoom and measurement remain available. Keyboard Enter/arrow/Escape and touch taps cover the same actions.
- [x] `AC-TABLE-SCOPE` covers `NFR-TABLE-SCOPE`: No dynamic light, walls, movement collision engine, turn engine or text chat is activated.

- [x] `AC-TABLE-QUALITY` covers `NFR-TABLE-QUALITY`: full backend and final frontend verification, local SQL/fresh migration replay and real desktop/tablet browser assertions pass; this document passes the existing traceability validator.

## Public contracts

- Existing Command/CommandResult and SceneService transaction remain the sole mutation seam.
- Commands: fog.fill {}, fog.reset {}, fog.reveal {points}; annotation.create AnnotationData, annotation.update {annotation_id,annotation:AnnotationData}, annotation.delete {annotation_id}; dice.roll {expression,visibility="everyone"}; action.undo {event_cursor}.
- SceneProjection adds fog {enabled,reveals:[{points:[{x,y}]}]} and annotations [{id,kind,points,label,visibility,owner_participant_id,can_edit}]. Frontend treats absent new fields as empty for compatible fixtures.
- GET /api/v1/rooms/{room_id}/journal?before_cursor=0&limit=30 (limit 1–50) returns JournalPage {entries:[{cursor,aggregate_version,actor_name,occurred_at,action,type,result,visibility,roll,can_undo,revoked}],next_cursor}. RollEvent {id,expression,results,modifier,total,visibility,created_at} is frozen.
- WS sync retains snapshots and safe cursor/version markers; dice emits journal.changed. The frontend uses the same authoritative snapshot path.
- Viewport.rotateAt(screenPoint,radians) keeps its anchor fixed; screenToWorld/worldToScreen and token drag honor rotation.
- Supabase CLI generated exactly supabase/migrations/20261014160027_table_tools.sql. Existing migration files are untouched. New tables use RLS/no browser grants; history mutation triggers permit only parent-room cascade cleanup. Deferred actor FKs preserve campaign cleanup order.

## Evidence map

- `AC-TABLE-FOG`: tests/scene_tools/test_tools.py::test_fog_commands_project_objects_and_realtime_safely and test_fog_blocks_known_hidden_token_transform_and_asset_grant; real GM/player HTTP/WebSocket fog scenario; tests/scene_tools/test_geometry_contract.py vertex/collinear concave-mask footprint/path/asset denial and accepted extreme derived coordinates across scene/journal/realtime/assets.
- `AC-TABLE-ANNOTATIONS`: tests/scene_tools/test_tools.py::test_annotation_owner_rights_hidden_projection_and_tombstone; rendered GM label and keyboard line edit/delete/undo; tablet player arrow.
- `AC-TABLE-RULER`: frontend/src/renderer/viewport.test.ts and frontend/src/features/scene-tools/CanvasTools.test.tsx; rendered 64 world px = 5 feet at 125% zoom and 45 degree rotation.
- `AC-TABLE-DICE`: tests/dice_log/test_dice.py::test_server_dice_is_bounded_idempotent_immutable_and_private; fixed 3d1+2 = 5, replay, unsafe/bounded/private failures and immutable SQL rows; rendered public/private dice.
- `AC-TABLE-JOURNAL`: tests/dice_log/test_dice.py safe HTTP journal/realtime assertions and typed JournalPage/RollEvent; real player private-roll/annotation exclusion.
- `AC-TABLE-UNDO`: tests/scene_tools/test_tools.py::test_undo_compensates_head_version_preserves_history_and_is_idempotent; tests/cards/test_blind_lifecycle_repair.py public lifecycle and reference controls; rendered fog, annotation, resource, card and token compensation.
- `AC-TABLE-INPUT`: frontend/src/features/scene-tools/ToolsFlow.test.tsx and CanvasTools.test.tsx, existing realtime regressions; rendered tablet offline/read-only/pan/zoom/automatic-resync assertions.
- `AC-TABLE-SCOPE`: changed scene_tools/dice_log modules, existing SceneService delegation and unchanged dependency declarations; manual geometry only.
- `AC-TABLE-QUALITY`: configured full backend 153 tests/89.54% branch coverage; frontend 38 tests/types/build and ruff/mypy; supabase/tests/table_tools.sql 12/12, full 82/82 and fresh six-migration replay with schema/ACL equality; scripts/validate_spec.py --spec docs/specs/VTT-006-table-tools.md.

Backend full configured branch-coverage run: 153 passed, no skips, 89.54% (baseline 146, 89.26%). Final frontend: 38 passed (baseline 34), including the persistent immediate-keyboard-after-tool-switch regression with RED → GREEN. Ruff/mypy/build passed. Root repeats the final frontend checks and exact source read-back before acceptance.

Rendered Chromium used local synthetic GM/player identities with the real FastAPI/Postgres/Redis authority and WebGL at 1440×900 and tablet touch at 1024×768. Public/private fog/annotations/dice/journal, mutation/undo, keyboard, zoom/rotation ruler, and disconnect/resync assertions passed. This does not verify hosted Supabase Auth/Storage, Firefox/Safari, WAN latency, or five full group sessions. Background map pixels already authorized for download are not erased by manual fog; token metadata and new hidden token grants are filtered server-side.

## Review regression evidence

The accepted concave reveal with vertices (-32,-32), (96,-32), (96,96),
(64,96), (64,0), (32,32), (0,0), (0,96), (-32,96) must conceal the token
footprint (0,0,64,64) and lines/arrows crossing its closed notch. Public scene,
realtime and journal projections exclude those objects; the token asset endpoint
returns 403. A fully revealed control token and label remain visible. The repair
partitions each segment at boundary contacts and checks every interval, including
vertex and collinear contacts, and rejects interior reveal boundaries within a
closed footprint. It introduces no movement collision rule.

Accepted item state x=1000000 with width=64, and a rotated million-pixel footprint,
remain readable through scene/journal/realtime/assets while fog is disabled.
Enabled fog computes unbounded internal world corners and conceals footprints
that extend beyond a reveal, returning a normal projection/403 instead of input
Point validation failure. Public input coordinate limits remain unchanged. Both
regressions passed RED before repair and GREEN afterward.

## F5 compensation evidence

`tests/scene_tools/test_undo_coverage.py` verifies all scene/item/dice verbs,
18 established registry verbs, local/shared access and lifecycle negatives,
and sequential item/card/fog/scene compensation with actual state read-back.
`tests/card_import/test_undo_confirm.py` verifies exact count-two card/token
IDs, independent existing cards, unchanged confirmed job and original receipt,
raw-source/fragments erasure and duplicate command replay.
`tests/campaign_transfer/test_transfer.py` preserves active lifecycle state and
revoked dice through ZIP/export/import without undo authority or private state.
`frontend/src/features/dice/DicePanel.test.tsx` preserves the rolled result,
revocation label and existing disabled/GM-only compensation control.
`supabase/tests/scenes_assets.sql` covers scene tombstones and safe references
on append-only migration `20261015110000_scene_undo_lifecycle.sql`.

Journal `revoked` is a derived boolean from the original event and a later
compensation; RollEvent and dice rows remain unchanged. Archived revoked dice
retain the safe action label and original result and cannot become authority.
Asset uploads and campaign transfer jobs are outside the gameplay registry.
