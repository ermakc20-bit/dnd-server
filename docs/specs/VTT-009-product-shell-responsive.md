# VTT-009: Native product route and responsive table

## Goal and traceability

R04/R05/R09/G02/G03/G05/G07/G08/G09/G16/G18/G19/G22/G26/G27/G28/D10
assemble the accepted slices into one Russian map-first route. FastAPI remains
sole gameplay authority. No dependency, hosted write, new backend API or prototype
activation is introduced. Phone participation is deliberately auxiliary.

## Requirements

- `FR-SHELL-ROUTE`: native /rooms/:roomId restores only a room returned by the current authenticated campaign API; /join/:token retains guest cookie restore and registered/guest join.
- `FR-SHELL-FIRST-RUN`: successful creation opens the authorized room; short skippable map/grid/card/invitation guidance permits continuing later without discarding safe input.
- `FR-SHELL-PANELS`: cards, image/scene controls and participant/invitation administration open in the active table, retaining the map and visited form drafts.
- `FR-SHELL-DEVICES`: desktop >=1280px provides full UI; tablet 768–1279px provides map/token/card/resources/dice/ability; phone <768px provides entry/cards/current resources/dice/journal only.
- `NFR-SHELL-STATES`: loading, empty, offline, forbidden/not-found and server quota errors use safe Russian messages; confirmed offline state stays read-only; no invented total storage quota.
- `NFR-SHELL-ACCESSIBILITY`: names, visible focus, keyboard Escape and non-hover controls support critical actions; selected controls expose semantic state.
- `NFR-SHELL-MEASUREMENT`: durable local E2E records preparation from ready PNG/filled XLSX through acknowledged map/cards/token and invitation; synthetic duration does not close the real twenty-minute product gate.
- `NFR-SHELL-SCOPE`: voice/video/text chat/marketplace/payment and full phone preparation do not appear; existing authority/auth/renderer/realtime contracts remain.
- `NFR-SHELL-QUALITY`: public rendered regressions, actual desktop/tablet/phone browser checks and full existing verification support the slice.

## Acceptance criteria

- [x] `AC-SHELL-ROUTE` covers `FR-SHELL-ROUTE`: authenticated direct route and refresh resolve via campaign API, without deriving permissions or persisting credentials; current credential/path scope discards stale opened sessions. Malformed and unknown paths safely render a missing-page state; unauthorized rooms reveal no campaign. Email return path accepts only native same-origin product paths.
- [x] `AC-SHELL-FIRST-RUN` covers `FR-SHELL-FIRST-RUN`: first-run creation enters its returned room; guidance opens existing map/grid/import/cards/participants panels. Steps can be skipped. A quota error retains the campaign name for retry. Existing import/asset failure retention is preserved.
- [x] `AC-SHELL-PANELS` covers `FR-SHELL-PANELS`: visited panels remain mounted behind hidden wrappers, preserving card draft while canvas remains mounted. RoomAdmin reuses existing room API and capabilities inside the table. Host ResizeObserver forwards local layout changes to the existing Pixi window-resize seam, without a new renderer contract.
- [x] `AC-SHELL-DEVICES` covers `FR-SHELL-DEVICES`: phone renders no canvas or preparation/invite/import/geometry controls, including for a GM; permitted current resource and dice commands retain the existing authoritative command path. Tablet panels can collapse for placement; map is retained across panel switches.
- [x] `AC-SHELL-STATES` covers `NFR-SHELL-STATES`: safe missing/unauthorized/invalid-invite messages, retained quota input and real offline confirmed map/resource read-only behavior are checked. Existing 50 MiB image limit remains; undefined commercial or total quota is not invented.
- [x] `AC-SHELL-ACCESSIBILITY` covers `NFR-SHELL-ACCESSIBILITY`: labelled actions, aria-pressed/expanded state, focus-visible and keyboard Escape return focus to the active panel button. Panels scroll independently; entry/library pages scroll instead of clipping narrow-screen controls.
- [x] `AC-SHELL-MEASUREMENT` covers `NFR-SHELL-MEASUREMENT`: frontend/e2e/native-flow.cjs records preparation_ms and explicitly marks real_twenty_minute_gate not_verified in a local result artifact.
- [x] `AC-SHELL-SCOPE` covers `NFR-SHELL-SCOPE`: production main.tsx/Auth SDK/API/backend contracts are unchanged. Native acceptance fixture is an explicit local entry, never imported by production main.tsx.
- [x] `AC-SHELL-QUALITY` covers `NFR-SHELL-QUALITY`: full verification and actual browser viewport/flow checks pass with stated limitations.

## Interfaces

- `productRoute(path) -> ProductRoute`: home, room{id}, join{token}, missing; bounded safe path segment parsing.
- `safeReturnPath(path) -> native path | "/"`; `useProductRoute() -> {route,path,navigate}` observes browser history.
- `RoomRoute({id,accessToken,onRoom,onBack})` resolves only authorized campaign rooms.
- `CampaignHome.onOpenRoom` also runs after successful campaign creation; `RoomAdmin` exported for native in-table reuse; `disabled?:boolean=false` blocks durable admin actions while retaining reads.
- `CardsPanel.auxiliary?:boolean=false`: hides structural editing, token/geometry and export controls while retaining current resource capability and an existing draft in the same tab.
- Existing HTTP/Command/CommandResult, WS sync, SceneProjection, renderer, Auth and backend contracts are unchanged.

## Evidence map

- `AC-SHELL-ROUTE`: frontend/src/app/ProductRoute.test.tsx authorized direct/refresh regression; frontend/e2e/native-flow.cjs unknown/malformed/unauthorized route, guest restore and invalid/revoked invite paths.
- `AC-SHELL-FIRST-RUN`: frontend/src/features/campaigns/CampaignExperience.test.tsx quota failure/name retention/retry-to-room regression; native E2E ready map/filled-template preparation.
- `AC-SHELL-PANELS`: frontend/src/app/NativeTable.test.tsx card draft/invite/participants and one renderer creation/no destroy; browser canvas identity and measured buffer/host alignment.
- `AC-SHELL-DEVICES`: frontend/src/app/NativeTable.test.tsx phone GM public resource/dice commands with no map/preparation; native browser desktop1440x900/tablet touch1024x768/phone390x844 and320x700.
- `AC-SHELL-STATES`: quota/room capability tests, existing realtime/card/import regressions; native browser offline/resync and failed invite/name retention.
- `AC-SHELL-ACCESSIBILITY`: native browser keyboard Escape/focus, touch card/token/ability and viewport overflow assertions; explicit labels/semantic state/global focus styles.
- `AC-SHELL-MEASUREMENT`: frontend/e2e/native-flow.cjs preparation_ms from ready fixture files through server read-back and issued invitation; frontend/e2e/native_runtime.py fills the canonical XLSX v1 template.
- `AC-SHELL-SCOPE`: scoped source diff and unchanged production entry/dependency manifests/backend; fixture local-only URL/database guards.
- `AC-SHELL-QUALITY`: make verify on an exact env-free source snapshot, separate validate_spec.py invocation and actual native browser result; final evidence below.

## RED proof and practical limits

Authorized /rooms refresh initially displayed the library instead of the requested
room. First-run retry saved the campaign but never called onOpenRoom. Switching
cards -> scene -> cards discarded the edited draft. Phone GM exposed new/structure
card preparation. These public regressions failed for the named behavior before
implementation and pass afterward. Browser layout initially had host height483
versus canvas buffer653 after preparation expanded; observer repair gives483/483.
Persistent native E2E checks buffer alignment after map/panel/device layout changes.

Local acceptance uses real FastAPI/Postgres/Redis and MemoryStorage, with only
synthetic JWT verification replaced. Guest cookies, join/restore, command policy,
HTTP/WebSocket state, server dice and projections remain native. This is browser
touch, not physical-device evidence. Hosted Supabase Auth/Storage, Firefox/Safari,
WAN, five full internal games and the real twenty-minute preparation gate remain
unverified. No invitation is sent to another person.

Native browser final result: eight paths passed, five viewport checks (GM/player desktop1440x900, touch tablet1024x768, phone390x844 and320x700), zero page errors. Synthetic preparation1768ms: map672ms, import1007ms, invitation89ms. Source-controlled E2E result explicitly marks the real twenty-minute gate not_verified. Tracked native HTML fallback separately passes malformed UTF8 and authorized route refresh. Owned API/Vite stopped; fixture users/campaigns/jobs each read back0. Results and screenshots: /private/tmp/dnd-t09-e2e/.

Initial candidate executor make verify:279 backend +48 frontend, no skips (baseline279+44), branch coverage87.77%; ruff/mypy89/types/build/project/spec PASS. VTT009 separately passes validate_spec.py. Existing Pixi bundle >500kB warnings remain for acceptance; dependencies/backend/migrations were not changed. Full log: /private/tmp/dnd-t09-final-verify.log. Root independent verification and fresh point review follow before acceptance.

To repeat the explicit native browser fixture, use an env-free source snapshot with existing pinned dependencies, set VTT_TEST_DATABASE_URL to the dedicated test database at127.0.0.1:55439 and VTT_TEST_REDIS_URL to dedicated Redis at127.0.0.1:56439/15, then run native_runtime:app from frontend/e2e on18009 with cwd outside source. Start Vite with e2e/native-vite.config.ts from the snapshot frontend directory on5189. Production index/main do not need replacement: this explicit config serves tracked e2e/native.html for HTML routes. Run frontend/e2e/native-flow.cjs with VTT_PLAYWRIGHT_MODULE pointing to the existing Playwright runtime and VTT_CHROME_EXECUTABLE pointing to installed Chrome. VTT_E2E_OUTPUT controls local fixture files/results/screenshots; both processes must use the same directory. Stop only owned API/Vite and inspect cleanup.json exact synthetic owner counts. No installation, hosted Auth, emails or external invite delivery is part of this acceptance.

## Point-review repair evidence

The campaign preparation form is unavailable after desktop1440->phone390 transition; name/package state remains in CampaignHome and returns unchanged on a large screen. Campaign submit also guards phone mode. RoomAdmin receives the table disabled state: issue/rotate/revoke invitation, PIN/access changes and participant removal are disabled and request-guarded while disconnected or connecting. Only snapshot resync plus connected restores actions; cached participant reading and draft PIN remain. No backend/API/dependency changes.

Persistent frontend/src/app/ShellBoundaries.test.tsx passed RED->GREEN for both conditions: visible phone Save campaign before repair; seven durable offline requests before repair versus zero after. Connecting without a new confirmed snapshot stays disabled. Native frontend/e2e/native-boundaries.cjs passed phone form absence/draft restoration, seven disabled offline actions/zero durable requests, one successful admin write after real reconnect/resync and zero page errors. Own API/Vite stopped; exact synthetic user/campaign/job counts each0. Browser result: /private/tmp/dnd-t09-boundaries/boundary-results.json; cleanup: /private/tmp/dnd-t09-boundaries/cleanup.json.

Final repair executor verification:279 backend +50 frontend, no skips (previous candidate279+48), branch87.77%; ruff/mypy89/types/build/project/spec PASS. Separate VTT009 validator and git diff --check PASS. Full repair log: /private/tmp/dnd-t09-repair-verify.log. Both public boundary regressions and bounded native browser pass; fresh root fix-only review follows. No source changes after final freeze.
