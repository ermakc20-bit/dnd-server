# VTT-007: Manual ability geometry presentation

## Goal and requirement traceability

R04/R05/R09/G07/G10/G12/G13/G17/G18/G19/G22/G26/G27/D08 implement
story 14 through the accepted T03 cards, T04 realtime and T06 fog/journal.
FastAPI remains the sole authority; the existing room lock, aggregate version,
command receipt and immutable event transaction are reused. One new migration
stores current presentations, without new dependencies or a rule engine.

## Requirements

- `FR-ABILITY-SCHEMA`: reuse versioned Ability and Geometry with circle/cone/line/cube/radius, token/point origin, range/radius/length/width/angle/units/color and automation null.
- `FR-ABILITY-FLOW`: from an open visible card, launch the ability including explicit origin selection, direction when needed, and confirmation in at most three desktop or touch actions.
- `NFR-ABILITY-BOUNDARY`: server hit tests use token centers, analytic shapes, inclusive boundaries and fixed world tolerance with independent public fixtures.
- `FR-ABILITY-ACCESS`: player presents only a visible ability of their assigned visible card; registered GM presents a permitted room card; token sources must be explicitly chosen visible linked tokens.
- `NFR-ABILITY-PRIVACY`: affected IDs are computed only from current authorized token projections, including fog; no global affected list, card/ability secrets or hidden-target tests enter recipient geometry processing.
- `FR-ABILITY-PREVIEW`: local preview is ephemeral; explicit confirmation persists current presentation and journals an immutable event; cancel/disconnect/resync discard draft.
- `FR-ABILITY-MANUAL`: no presentation changes HP/resources/uses/saves/damage/states; range is informational and point origin requires no implicit caster or linked token.
- `NFR-ABILITY-RENDER`: Pixi draws confirmed and preview shapes and highlights server-authorized affected tokens across desktop/tablet and viewport transformations.
- `NFR-ABILITY-EXTENSION`: Ability schema_version remains 1 and automation remains null; future versioned automation does not introduce an executor in this slice.
- `NFR-ABILITY-QUALITY`: public commands/HTTP/realtime, local SQL replay, frontend types/tests/build and actual browser evidence verify this slice.

## Acceptance criteria

- [x] `AC-ABILITY-SCHEMA` covers `FR-ABILITY-SCHEMA`: existing backend Geometry/Ability are reused; typed frontend Geometry and native CardEditor controls expose all five shapes, origin, required dimensions, angle, units, color and informational range. Presentation requires positive radius for discs, positive length for cone/line/cube, positive width for line and angle for cone, with exact scene-unit equality. Partial imported geometry remains readable and can be corrected before presentation.
- [x] `AC-ABILITY-FLOW` covers `FR-ABILITY-FLOW`: token-origin launch buttons in the open card explicitly choose ability plus one current visible linked source, including multiple representations; direction for cone/line/cube and confirmation total three actions (discs two). Point-origin launch plus one origin-to-direction placement gesture plus confirmation totals three actions; discs use one point. Repeated placement moves/rotates the local draft. Bounded numeric/keyboard and staged map alternatives remain available. The count includes the first card ability/source choice; no implicit source selection is allowed.
- [x] `AC-ABILITY-BOUNDARY` covers `NFR-ABILITY-BOUNDARY`: disc distance, circular cone sector, forward line rectangle and centered oriented cube square use closed boundaries with 1e-7 world-pixel tolerance. Cone angular tolerance derives from that spatial tolerance. Token size/rotation does not introduce game-system area-intersection rules; its center is the hit point. Fixtures cover boundary, vertex, immediately outside and rotated cone/cube cases.
- [x] `AC-ABILITY-ACCESS` covers `FR-ABILITY-ACCESS`: PRESENT_ABILITY uses the shared policy; player ownership and both card/ability visibility are checked server-side. Unknown/inaccessible card/ability/token sources produce generic forbidden results. Geometry comes from the saved card, never arbitrary client replacement. Numeric input Point bounds remain +/-1000000 and finite; derived token centers use an unbounded finite output model.
- [x] `AC-ABILITY-PRIVACY` covers `NFR-ABILITY-PRIVACY`: presentation DTO contains only id/geometry/created_at/can_clear/affected_item_ids. Every recipient sees the same explicitly presented geometry; affected IDs vary with their current authorized scene projection. Hidden targets never enter ability hit tests, target-dependent response branches or target-count metadata. Existing fog/projection/database work is reused; this is not a cryptographic constant-time claim for the whole HTTP request. Generic journal and realtime notifications contain no raw ability/card/event payload.
- [x] `AC-ABILITY-PREVIEW` covers `FR-ABILITY-PREVIEW`: only ability.present writes state; preview has no Redis/database/event mutation. One current area per actor/scene is replaced on subsequent confirmation; ability.clear removes current area without rewriting immutable history. Repeat command IDs return duplicate and preserve one event. Tool switching, cancel, offline and resync remove unconfirmed drafts.
- [x] `AC-ABILITY-MANUAL` covers `FR-ABILITY-MANUAL`: card equality before/after confirms unchanged HP and hidden uses. Point origin with range=0 works without a token for assigned player and GM; range stays canonical card metadata and visible guidance, without legality checks, implicit caster selection or automatic resource changes.
- [x] `AC-ABILITY-RENDER` covers `NFR-ABILITY-RENDER`: Pixi Graphics overlays use world coordinates, confirmed affected highlights use only server IDs, and retained T06 SVG fog obscures unrevealed pixels. Native Chromium coverage at 1440x900 and touch at 1024x768 includes all five shapes and both origin modes, counting from the open card and requiring exactly one durable command only after confirmation.
- [x] `AC-ABILITY-EXTENSION` covers `NFR-ABILITY-EXTENSION`: existing Ability.automation accepts only null in version 1, unchanged schema_version and dependency files; no saves/damage/turn/state automation is added.
- [x] `AC-ABILITY-QUALITY` covers `NFR-ABILITY-QUALITY`: targeted public tests, full configured backend and frontend checks pass; seven migration-specific pgTAP checks pass in a disposable local database. Exact spec validator, lint/types/build and diff checks accompany final source delivery.

## Public contracts

`ability.present {card_id,ability_id,origin_item_id?|origin{x,y},direction{x,y}?}`
uses the existing Command/CommandResult. Token-origin requires origin_item_id and
forbids origin; point-origin requires origin and forbids origin_item_id. Directed
shapes require a nonzero direction vector. Direction selects orientation; card
dimensions determine the area size. Range does not determine casting legality.

`ability.clear {presentation_id}` is allowed for the presenter or registered GM.
Accepted present/clear events have the current scene, actor, aggregate version,
receipt and cursor. They do not support T06 inverse undo; an explicit clear is a
new journaled action. Old commands do not resurrect a replaced/cleared area.

`SceneProjection.ability_presentations[]` contains:
`{id,geometry,created_at,can_clear,affected_item_ids}`. Geometry is
`{schema_version:1,shape,origin:{x,y},rotation,radius,length,width,angle,color}`;
rotation is radians, dimensions are world pixels, angle is degrees. Scene units
convert through grid_size/unit_size. Discs share geometry; cube is a centered
square and line extends forward from its origin. Confirmed geometry remains a
fixed manual presentation if source tokens/cards or calibration later change;
the affected list is recomputed from currently visible token centers.

`SceneFrame.abilityPreview` is local PresentedGeometry or null;
`buildFrame(projection,itemPreview?,abilityPreview?)` preserves existing item
drag and Pixi rendering. `CardsPanel.onPresentAbility` passes an authorized card
selection to the scene; it does not issue a gameplay command itself.

## Evidence map

- `AC-ABILITY-SCHEMA`: backend/app/cards/models.py unchanged Geometry/Ability; frontend/src/features/ability-geometry/types.ts and GeometryEditor.test.tsx RED missing native geometry control to GREEN saved card; public shape fixtures in tests/ability_geometry/test_boundaries.py; real GM native controls saved radius25/range0/point, card version2, HP10/schema1/automationnull unchanged.
- `AC-ABILITY-FLOW`: frontend/src/features/ability-geometry/AbilityFlow.test.tsx counts launch from the open card for all five shapes and both origins, explicit second-source selection, pending and reconnect; frontend/src/features/cards/CardsPanel.test.tsx covers source and card-access gates; tests/e2e/browser.cjs retains the native baseline and adds desktop/touch three-action launch/public readback/source-coordinate/offline assertions. Earlier T07 counts excluded the ability choice and did not prove the original three-action requirement.
- `AC-ABILITY-BOUNDARY`: tests/ability_geometry/test_boundaries.py public command/HTTP fixtures for all five shapes; origin/edge/outside/rotated expected results use independent numeric coordinates.
- `AC-ABILITY-ACCESS`: tests/ability_geometry/test_privacy.py::test_authorization_token_origin_bounds_stale_and_clear and derived center(1000032,1000032) outside accepted input range; existing shared Action policy and generic denials.
- `AC-ABILITY-PRIVACY`: tests/ability_geometry/test_privacy.py hidden/fog/realtime/journal assertions and equality after adding eight hidden targets; backend/app/ability_geometry/service.py consumes projected visible tokens only.
- `AC-ABILITY-PREVIEW`: first AbilityFlow regression RED missing launch button, then GREEN local preview/confirm/cancel/offline/resync; tool-switch regression RED retained preview after changing tool, then GREEN annotation flow.
- `AC-ABILITY-MANUAL`: tests/ability_geometry/test_present.py unchanged full card/one event/duplicate; test_point_origin_with_range_needs_no_token_and_does_not_infer_casting_legality; real rendered HP=10 after ten confirmed desktop/tablet areas.
- `AC-ABILITY-RENDER`: real Chromium/WebGL2 shape and affected-list assertions at 1440x900 and tablet1024x768 hasTouch=1, screenshots /private/tmp/dnd-t07-desktop.png and /private/tmp/dnd-t07-tablet.png; AbilityCanvas.test.tsx explicit token source/keyboard direction/viewport regression plus local touch placement/move/rotate, pointercancel, source replacement/deletion and stale/pending projection guards; PixiSceneRenderer world Graphics overlays.
- `AC-ABILITY-EXTENSION`: unchanged backend/app/cards/models.py Ability.automation and dependency manifests; canonical source/command code has no resource/rule execution path.
- `AC-ABILITY-QUALITY`: final isolated make verify backend163 passed/89.89% branch coverage (baseline153/89.54%); frontend41 passed (baseline38), ruff/mypy/types/build/project/spec PASS; supabase/tests/ability_geometry.sql7/7 and fresh seven-migration replay89/89 with matching schema/ACL; scripts/validate_spec.py --spec docs/specs/VTT-007-ability-geometry.md.

## Verification limits

All execution used local disposable PostgreSQL/Redis and synthetic registered
GM/player identities; no hosted Auth/Storage, WAN latency, Safari/Firefox, or
five full group sessions are certified. Fixed presentation geometry never
discloses card/ability identity or private fields; explicitly showing an area is
intentional public presentation. Root independently verifies final source and
the fresh seven-migration replay before accepting the slice.
