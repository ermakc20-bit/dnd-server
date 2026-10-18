# VTT-010 — Native local acceptance

Version 1. This slice supplies explicit, repeatable checks and evidence for the
implemented internal platform. Developer OS means specs, ADRs and verification;
legacy development/design prototypes remain preserved and inactive.

## Requirements

- `FR-ACCEPT-SLICES`: every implemented vertical slice has a validated FR/NFR → acceptance → evidence map and load-bearing ADRs.
- `FR-ACCEPT-BROWSER`: a new owned local fixture checks native GM/guest, map/token, filled template confirmation, resource/geometry, offline/reconnect and campaign export/import.
- `FR-ACCEPT-LOAD`: 1+5 and ten simultaneous room connections converge through HTTP/WS, command retry and reconnect without hidden canary leakage or duplicate application.
- `FR-ACCEPT-LOCAL`: local setup and explicit acceptance commands use disposable services and refuse incomplete integration coverage.
- `FR-ACCEPT-GATES`: distinguish local technical evidence, historical market/reference evidence and unverified real-user/hosted/infrastructure/commercial gates.
- `NFR-ACCEPT-DATABASE`: replay only in newly created owned synthetic databases, run all pgTAP assertions, read back exact cleanup and never reset an existing database.
- `NFR-ACCEPT-PRIVACY`: bounded source/build/log scans distinguish findings from scanner failure; runtime canaries prove the tested player projection excludes hidden payload.
- `NFR-ACCEPT-NOAI`: product dependency/network source checks reject AI SDKs and model endpoints; no AI, hosted writes or prototype routing enters acceptance.
- `NFR-ACCEPT-DEPENDENCIES`: apply only approved patched packages, preserve unrelated lock nodes and pass advisory audits plus JWT and raster/overlay regressions.
- `NFR-ACCEPT-CI`: source CI provides PG/Redis, uses test URLs and fails when tests skip; local source validation is not a remote CI result.

## Acceptance criteria

- [x] `AC-ACCEPT-SLICES` covers `FR-ACCEPT-SLICES`: all VTT specs are checked by make verify; ADR-003–006 record identity/aggregate/cards/portability decisions.
- [x] `AC-ACCEPT-BROWSER` covers `FR-ACCEPT-BROWSER`: native loopback browser flow acknowledges each state transition and verifies restored asset bytes/current resources/geometry with new IDs.
- [x] `AC-ACCEPT-LOAD` covers `FR-ACCEPT-LOAD`: both simultaneous connection cohorts acknowledge thirty mutations, duplicate receipts and reconnect with cursor/version convergence.
- [x] `AC-ACCEPT-LOCAL` covers `FR-ACCEPT-LOCAL`: fresh env-free dependency/runtime setup and full make verify pass without skipped integration tests.
- [x] `AC-ACCEPT-GATES` covers `FR-ACCEPT-GATES`: all original requirement IDs retain coverage; external/real-use gates below remain explicitly unverified.
- [x] `AC-ACCEPT-DATABASE` covers `NFR-ACCEPT-DATABASE`: new database replay passes eight migrations/97 assertions, zero owned databases remain; nonlocal/existing-name CLI regressions fail safely.
- [x] `AC-ACCEPT-PRIVACY` covers `NFR-ACCEPT-PRIVACY`: secret/config canary negatives and missing-build errors pass; native hidden-data canaries supplement bounded scans.
- [x] `AC-ACCEPT-NOAI` covers `NFR-ACCEPT-NOAI`: dependency/network negatives pass and product source/build scan checks the actual graph without consulting env files.
- [x] `AC-ACCEPT-DEPENDENCIES` covers `NFR-ACCEPT-DEPENDENCIES`: approved pins and one-node lock change pass audits/JWT/actual raster/overlay checks with no blanket ignores.
- [x] `AC-ACCEPT-CI` covers `NFR-ACCEPT-CI`: CI source starts dedicated local services and create-only integration DB; skipped tests fail acceptance. Actual remote execution remains unverified.

## Evidence map

- `AC-ACCEPT-SLICES`: Makefile all-spec loop; scripts/validate_spec.py; VTT-001–010; docs/adr/ADR-003–006.
- `AC-ACCEPT-BROWSER`: tests/e2e/run.py, runtime.py and browser.cjs; safe local results plus exact cleanup.json.
- `AC-ACCEPT-LOAD`: tests/load/room-smoke.cjs; safe participant/receipt/convergence/latency counters.
- `AC-ACCEPT-LOCAL`: README explicit native recipes; make verify with mandatory VTT_TEST_DATABASE_URL/VTT_TEST_REDIS_URL and no-skip hook.
- `AC-ACCEPT-GATES`: original-requirement coverage table and dated gate status below.
- `AC-ACCEPT-DATABASE`: scripts/acceptance_database.py; tests/e2e/test_acceptance_database.py; /private/tmp/dnd-t10-database-results.json.
- `AC-ACCEPT-PRIVACY`: scripts/acceptance_scan.py; tests/e2e/test_acceptance_scan.py; filtered runtime canary assertions.
- `AC-ACCEPT-NOAI`: dependency/network negative scanner regression; production code/lock scan.
- `AC-ACCEPT-DEPENDENCIES`: pyproject/Dockerfile/Makefile exact pins; frontend override/lock structural identity; pip-audit/npm production audit; auth and browser regressions.
- `AC-ACCEPT-CI`: .github/workflows/ci.yml; tests/e2e/conftest.py; create-only acceptance database recipe.

## Original requirement coverage and factual limits

| Original IDs | Implemented evidence or explicit deferred boundary |
|---|---|
| R01, R02, R03, R08, R09 | authoritative deep interview/spec/audit preserved; VTT-001–010 and ADR evidence reflect implemented slices |
| R04, R05, G02, G18 | map-first native table, scenes/items/tools; VTT-002/006/009 and browser flow |
| R06, R07 | dated 2026-09-03 qualitative market investigation supports a pilot, not Russian TAM, retention or paid demand; not refreshed in this slice |
| R10i, G01 | internal group first; organic growth and commercial stage remain later gates |
| R11i, G09, G28 | registered GM and optional-account guest model; VTT-001 and actual signed synthetic JWT/cookie browser flow |
| R12i, G17 | neutral fields/resources/packages and licensed-content boundary; VTT-003/005 and ADR-005 |
| R13i, G05, G16 | local 1+5/10 smoke prepares internal validation; five real games and willingness to continue are unverified |
| G03, G08 | external communication remains external; no integrated voice/video is delivered |
| G04, G12, G13, G14, G23, G24 | native cards, unique instances, no-AI drafts/confirmation and legacy fixtures; VTT-003/005/008 |
| G06, G26 | deterministic local reconnect evidence; accessibility/reliability from Russia over WAN remains unverified |
| G07, G10 | manual geometry, visible-token highlights, at most three launch actions counted from the open card including ability/source selection and confirmation; VTT-007 and permanent F7 desktop/touch browser assertions; no automated rules |
| G11 | deferred rules automation; versioned ability automation=null preserves the agreed boundary |
| G15, G20 | provider/production region and Russian infrastructure gates remain closed |
| G19 | synthetic ready-material preparation timing only; real twenty-minute preparation gate unverified |
| G21 | five external masters' consent remains deferred; no invitations/messages sent |
| G22 | role/current-membership permissions, fog/hidden projection and immutable safe journal; API/SQL/runtime canaries |
| G25 | complete independent campaign transfer; VTT-008 and native byte/resource/geometry roundtrip |
| G27 | desktop and browser-touch tablet, auxiliary phone; physical devices and Safari/Firefox remain unverified |
| G29, G30 | public library/copy growth and commercial version remain deferred |

Five sequential full internal games have not occurred. Neither guest join speed
in a synthetic browser nor loopback p95 proves the real one-minute entry/30-second
outage limits. Hosted Auth/Storage/migrations, WAN, physical devices, Safari/Firefox,
remote CI, external cohort consent and paid/business readiness remain unverified.
Existing >500 kB Pixi build warnings are a documented performance follow-up.

## Bounded security evidence

Scanner exit 0 means checked patterns/graph passed, 1 means findings, 2 means an
incomplete/error scan. No Git command failure is negated into success. Files/counts
are bounded; env files are excluded. Canary values and matched source text are
never printed. This does not prove the absence of every possible secret or data
flow: focused server-authority tests and native hidden-projection assertions
provide separate behavioral evidence. Own local dnd-vtt package is not on PyPI;
advisory audit skip does not audit its source.

## Reproduction and measurements

Use README's explicit local recipes. No source .env, old dataless dependency tree,
legacy prototype or hosted project is required by the native acceptance runner.
Source edits to CI are reviewable configuration, not evidence of a completed
remote run. Final measured counters and source identity follow after full checks.


## Final local evidence — 2026-10-14

Fresh Python installation from project declarations plus temporary constraints
contains exactly the same 75 distributions/versions as the approved patched
isolated environment. Fresh Node npm ci used the repaired project lockfile.
Structural comparison changed only node_modules/@xmldom/xmldom from0.8.13 to0.8.15;
Pixi8.19.0 and every other lock node remained identical. Pins: PyJWT2.15.1,
only dev urllib3 2.8.0, pip26.2. No blanket audit ignores or global runtime changes.

Full env-free make verify:287 backend/tooling and50 frontend tests, zero skips,
branch coverage87.77%, ruff/mypy91/types/build/project and all ten VTT validators
PASS. Baseline279+50; eight new CLI tests include seven RED->GREEN failures:
four scanner false-greens (secret/config/AI/missing build) and two unsafe database
CLI successes (nonlocal URL/existing-name option), plus deleted unowned output
evidence before the native runner ownership guard. The clean no-Git fixture is a
positive control. Independent synthetic skip probe exits1 as required.
Full log:/private/tmp/dnd-t10-final-verify.log.

Final bounded security scan:192 source/build files, zero findings; pip-audit
reports no known vulnerable third-party packages and npm production audit reports
zero vulnerabilities. Own local dnd-vtt0.1.0 remains not-on-PyPI and unaudited by
the advisory service. Scanner negative tests and runtime tests cover its source
separately. Full log:/private/tmp/dnd-t10-final-security.log.

Eight migrations and eight pgTAP suites passed97/97 in a new random synthetic
DB; read-back confirmed owned_database_remaining=0. Existing vtt_ticket01 was
not reset. Final result:/private/tmp/dnd-t10-final-database.json.

Actual Chrome154.0.8037.97 native browser passed seven required paths with zero
page errors. Assigned-token UI issued one durable command; GM/guest read back the
new position. Current HP7 persisted independently. Touch geometry took two
placement actions after selection and one durable confirmation. Offline retained
a read-only canvas/resource, then reconnect read back a GM position change.
Native ZIP download/import created new IDs and preserved exact PNG bytes, HP7,
confirmed geometry and current token position. Actual map texture/private-grant
proxy and overlay flow were rerun after test-harness fixes. T09 mouse/touch drag
is previous evidence, not a new T10 result. RS256/JWKS verification was native,
without substituting JWT verifier. Vite envDir is a new empty temporary directory;
API cwd/settings and filtered env avoid reading source env files.
Final results:/private/tmp/dnd-t10-final-acceptance/results.json.

Final protocol smoke kept six (1+5) and ten simultaneous WS participants.
Each case acknowledged30 mutations and30 duplicate receipts; every recipient
received each allowlisted accepted event cursor and converged to the same version.
One subsequent mutation was recovered after reconnect; version delta31 proves
retries did not duplicate application. Hidden token canary leaks0.
Local p95:263.41ms/252.90ms; reconnect31.23ms/27.79ms, respectively.
These are synthetic loopback measurements, not WAN SLO. Final result:
/private/tmp/dnd-t10-final-acceptance/load-results.json.

Both final browser/load runs stopped only owned API/Vite; exact synthetic
account/campaign/job rows read back0. No flush/reset of user data or original
Redis service was used. Temporary images/archive/results are local fixtures.
README fresh local recipes and CI source are updated; actual full Supabase
Auth/Storage stack and remote CI execution remain unverified. Existing bundle
warnings remain. Independent root/source identity and fresh review follow this
executor evidence; passing commands alone do not declare platform acceptance.

## Bounded point-review repair — 2026-10-15

Three conditions were independently reproduced against the staged T10 candidate:
NUL-containing text build/log files were skipped, TAP SKIP/TODO rows counted as
passed, and an owned output directory could overwrite an external target through
log/marker/ancestor symlinks. Seven persistent public CLI regressions failed for
those exact reasons before code repair; ten existing/positive controls passed.

The scanner now decodes/scans text even when it contains NUL. Invalid UTF-8 is
scanner_error, never clean. Only explicit PNG/JPEG/WebP/AVIF assets whose format
and structure pass Pillow verification are excluded as binary images. The clean
text/no-Git control and genuine PNG control remain separate passing tests.
TAP SKIP/TODO directives fail closed before an assertion can contribute to PASS;
an executed known-result control still reports one passed assertion. The real
fresh SQL replay retains eight migrations/eight suites/97 executed assertions,
owned_database_remaining=0, without resetting vtt_ticket01.

The native runner checks each lexical ancestor and all existing descendants for
symlinks before marker writes, result deletion or log opening. Ambiguous parent
traversal is rejected. Its own generated temporary root is canonical so macOS
system temporary aliases do not interfere with a legitimate default launch.
External log/marker targets and ancestor-routed files remain unchanged; all17
public CLI tests pass. No dependency or product source was changed by this repair.

Repair full env-free make verify:296 backend/tooling +50 frontend, zero skips,
branch87.84%, ruff/mypy91/types/build/project/all ten VTT specs PASS. Repair
security:193 bounded source/build files/findings0; Python advisory0/npm0, with
the same not-on-PyPI own-package limitation. Logs:/private/tmp/dnd-t10-repair-verify.log
and /private/tmp/dnd-t10-repair-security.log. Fresh SQL result:
/private/tmp/dnd-t10-repair-database.json.

The changed launch/output guard was repeated through the ordinary native fixture
on owned loopback18011/5191. Chrome154 passed the same seven required paths with
zero page errors, token UI command1/geometry1, HP7, raster-byte/new-ID/geometry
roundtrip and changed-state reconnect. Six/ten simultaneous participants each
received30 accepted events/30 duplicate receipts with cursor/version convergence,
hidden canary leaks0; local p95 258.05/261.61ms, reconnect31.07/28.87ms. Exact
synthetic account/campaign/job counts and owned API/Vite processes read back0.
Repair results:/private/tmp/dnd-t10-repair-acceptance/; native log:
/private/tmp/dnd-t10-repair-native.log. These remain synthetic local results;
previously documented real-user/hosted/WAN/device/remote-CI gates stay unverified.
Independent root repetition and fresh fix-only review follow this executor evidence.
