# VTT-008 — Portable campaign archives

## Goal and requirement traceability

R04/R09, G04/G12/G13/G17/G18/G23/G25/G26 and D09 are implemented as
creator-only native campaign export/import. ZIP v1 preserves confirmed gameplay
semantics and assets, remaps identities and commits an independent campaign.

## Requirements

- `FR-TRANSFER-ARCHIVE`: export all confirmed campaign rooms, cards/resources/custom fields, scenes/grid/fog, items/card links, annotations including tombstones, assets and current ability geometry.
- `FR-TRANSFER-PORTABLE`: versioned manifest covers every JSON/asset entry with MIME, exact byte size and SHA-256; archive-local references replace database IDs and Storage object keys.
- `FR-TRANSFER-CONFIG`: bounded gameplay config and package definitions retain user semantics; unsupported sensitive/provider settings fail explicitly.
- `FR-TRANSFER-HISTORY`: optional last 1000 safe journal summaries/dice results and confirmed room snapshot preserve visibility without raw payload/undo authority.
- `FR-TRANSFER-RESTORE`: validate the whole archive before gameplay writes, regenerate all IDs and create independent state/resources/assets in one metadata transaction.
- `FR-TRANSFER-OWNERS`: restore importer GM plus removed historical actors without sessions/memberships; unchanged historical ownership remains editable by GM and may be explicitly reassigned.
- `FR-TRANSFER-JOBS`: durable progress, request receipt, cancellation, expiry/recovery and scoped blob cleanup have truthful terminal results.
- `FR-TRANSFER-UI`: native campaign library offers import before a first campaign, export/download, readable progress/error/cancel and reload status recovery.
- `NFR-TRANSFER-ACCESS`: registered creator alone accesses jobs; export/download recheck owner and active GM authority; Data API privileges are denied.
- `NFR-TRANSFER-SAFETY`: ZIP paths, duplicates, symlinks, encryption, versions, checksums, MIME, images, references and resource limits are validated before writes.
- `NFR-TRANSFER-SECRETS`: no auth user IDs, guest sessions, memberships, invitations, PIN/hashes, signed URLs, command receipts or server settings enter the archive.
- `NFR-TRANSFER-QUALITY`: public-seam regression tests, isolated full verification, SQL replay and native browser scenarios provide local evidence.

## Acceptance criteria

- [x] `AC-TRANSFER-ARCHIVE` covers `FR-TRANSFER-ARCHIVE`: real PNG bytes, fog, annotations, presentation geometry, owned linked cards and independent HP survive the public roundtrip.
- [x] `AC-TRANSFER-PORTABLE` covers `FR-TRANSFER-PORTABLE`: ZIP v1 checksums and local refs survive restoration; original auth/DB IDs and provider keys are excluded.
- [x] `AC-TRANSFER-CONFIG` covers `FR-TRANSFER-CONFIG`: custom nested gameplay config survives unchanged; unsafe config fails without source mutation.
- [x] `AC-TRANSFER-HISTORY` covers `FR-TRANSFER-HISTORY`: imported immutable journal exposes safe original labels/dice/visibility and cannot undo old authority.
- [x] `AC-TRANSFER-RESTORE` covers `FR-TRANSFER-RESTORE`: request replay creates no second campaign; removed result stays a terminal receipt; invalid references create no campaign.
- [x] `AC-TRANSFER-OWNERS` covers `FR-TRANSFER-OWNERS`: GM edits an unchanged removed owner, cannot assign/create against removed actor, can reassign card/token to a new active player.
- [x] `AC-TRANSFER-JOBS` covers `FR-TRANSFER-JOBS`: accepted upload cancel remains cancelled; live delayed put/lease-expiry/delete failure/recovery retains exact new keys and source bytes.
- [x] `AC-TRANSFER-UI` covers `FR-TRANSFER-UI`: library import and local file errors are rendered; late completed cancel cannot regress to an older progress response.
- [x] `AC-TRANSFER-ACCESS` covers `NFR-TRANSFER-ACCESS`: other identities cannot read/cancel/download/export source; SQL proves RLS and revoked direct privileges.
- [x] `AC-TRANSFER-SAFETY` covers `NFR-TRANSFER-SAFETY`: duplicate JSON keys, future version, checksum corruption, traversal, symlink, missing package and late invalid asset reference fail before gameplay writes.
- [x] `AC-TRANSFER-SECRETS` covers `NFR-TRANSFER-SECRETS`: archive content excludes fixture auth IDs, PIN marker, object keys and session fields.
- [x] `AC-TRANSFER-QUALITY` covers `NFR-TRANSFER-QUALITY`: final isolated make verify and native browser checks passed; root independent review/acceptance remains separate.

## Evidence map

- `AC-TRANSFER-ARCHIVE`: tests/campaign_transfer/test_transfer.py::test_full_state_roundtrip_retains_usable_ownership_and_independent_resources.
- `AC-TRANSFER-PORTABLE`: tests/campaign_transfer/test_transfer.py::test_empty_campaign_portable_roundtrip_and_request_replay; test_storage.py public adapter contract.
- `AC-TRANSFER-CONFIG`: full state roundtrip; archive.py public validate_archive config contract.
- `AC-TRANSFER-HISTORY`: tests/campaign_transfer/test_transfer.py::test_imported_history_remains_readable_and_filtered_without_undo.
- `AC-TRANSFER-RESTORE`: empty campaign receipt/result deletion test and hostile archive matrix.
- `AC-TRANSFER-OWNERS`: full state roundtrip followed by GM update/resource, rejected removed-owner create, active player reassignment/resource/token movement.
- `AC-TRANSFER-JOBS`: tests/campaign_transfer/test_lifecycle.py public upload interruption and live put/delete recovery regressions.
- `AC-TRANSFER-UI`: CampaignExperience.test.tsx ZIP recovery and campaign-transfer/TransferPanel.test.tsx wrong-file/late-cancel regressions.
- `AC-TRANSFER-ACCESS`: cross-owner HTTP assertions; supabase/tests/campaign_transfer.sql.
- `AC-TRANSFER-SAFETY`: tests/campaign_transfer/test_transfer.py::test_duplicate_json_keys_and_late_invalid_references_never_create_campaign.
- `AC-TRANSFER-SECRETS`: full state archive-content assertions.
- `AC-TRANSFER-QUALITY`: isolated /private/tmp/dnd-vtt-t08-check verification and local browser runtime, final evidence below.

## Public contracts and limits

`POST /api/v1/campaign-transfers/{job_id}/export` accepts
`{campaign_id,include_history=false,include_snapshot=false}`. `PUT .../import`
accepts application/zip or application/octet-stream. Both return 202 TransferJob.
`GET .../{job_id}`, `DELETE .../{job_id}` and `GET .../{job_id}/archive` require the
same registered creator. All responses disable caching. UUID reuse replays the
existing receipt; a new UUID deliberately creates an independent import.

TransferJob exposes id/kind/phase/progress/cancel_requested/result_campaign_id/
error_code/expires_at/archive_available. Internal blobs, leases and source bytes
are private. Public domain seams are export_campaign/validate_archive/import_campaign.
Storage extends the existing private adapter with bounded get(key,max_bytes) and
idempotent delete(key); production credentials/provider URLs never become archive data.
The synthetic HTTP adapter test checks the private GET contract against
[official download documentation](https://supabase.com/docs/guides/storage/serving/downloads)
and scoped DELETE prefixes against the
[official Storage SDK implementation](https://github.com/supabase/storage-js/blob/main/src/packages/StorageFileApi.ts).

ZIP 256 MiB; expanded 512 MiB; JSON 32 MiB; image 50 MiB; 5000 ZIP entries;
10000 entities including nested ability/inventory IDs; history 1000 entries.
Gameplay config/metadata/payload: 64 KiB, depth 8, 2000 nodes; non-object,
credential/provider/server fields and signed URL values are rejected, never removed
silently. Complete archive/schema/card/ability/package v1 only; unknown versions fail.
Archive validation has two process slots, 60s wall/30s CPU and 768 MiB memory guard
(macOS RSS watchdog is not an instantaneous hard ceiling). Upload/expanded limits
apply independently. Source campaign export is a consistent database snapshot.

Receiving uploads expire after one hour; running workers refresh a 120s lease.
Metadata plus completed/result receipt commit under the final cancellation row lock.
Late cancel returns completed result. A PostgreSQL advisory session lock protects
live provider writes against recovery. Newly reserved keys are tracked before put;
cleanup never deletes source or another job's blobs. Uncertain provider errors or
shutdown retain cleanup_pending through 120s grace; failed deletion retains keys
for startup/periodic retries while API is running. Source bytes are nulled at terminal
import; export bytes expire after one hour. Receipts remain without content, and a
removed result is shown as unavailable rather than imported again.

Imported historical events are immutable campaign.history summaries with new
identifiers and can_undo=false. Their original visibility remains server filtered.
Non-owner actors are removed guest placeholders, never active sessions; unchanged
historical ownership is retained only for GM updates/resources of existing cards.

## Evidence and limitations — local only, 2026-10-14

Migration 20261014175928_campaign_transfer.sql SHA-256
e3960ff22f1c5a95f227ad16fc8c53cbb9c2b3aad143522853ad4b8bef9ce864.
SQL support confirmed all eight migrations and 97/97 pgTAP assertions on clean
replay; current/replay complete schema and ACL SHA-256
f109324f11281aff0497f6cce50b36cf34419e567e27f6cc84efba662bf38ebc.

Final env-free snapshot make verify passed 170 backend and 44 frontend tests,
with no skips, branch coverage 87.54%, ruff/mypy (89 source files), TypeScript,
build and project/spec validation. Log: /private/tmp/dnd-vtt-t08-verify.log.
VTT-008 separately passes validate_spec.py. Baseline: 163 backend/41 frontend.
Browser used installed Google Chrome 154.0.8037.97 in an isolated headless profile
with the existing Playwright package; the cached executable path in interfaces
was absent. Native AppView exercised real local API/Postgres/Redis and
MemoryStorage/Auth fixture: ZIP download, independent import, reload receipt,
corrupt archive/error with file retained, cancelled in-flight image upload,
export Storage outage with source preserved, desktop 1440 and tablet viewport
1024 without overflow or page errors. Fixture/runtime lived only in /private/tmp;
both servers stopped and all fixture-owned jobs/campaigns/account were cleaned.
This is local candidate evidence, not independent root acceptance.

Repair 1 after point review tightened archive validation only: required references
cannot be null, and active scene/card-token/owner/creator/annotation/presentation/
history references are scoped to the corresponding room before Storage put or
gameplay writes. Known credential/provider/server field names are normalized
across snake/camel/case/separator spellings; signed Supabase/S3/GCS/Azure/CloudFront
URLs are rejected in generic config/metadata/payload. Ordinary gameplay fields,
public image URLs, valid two-room state and legitimately nullable links survive
unchanged. New public archive regressions initially had 68 failures because the
validator accepted invalid input; three HTTP regressions performed one forbidden
Storage put. All pass after repair, with zero puts and no campaign writes.
The full targeted transfer slice passes 100 tests; final repair make verify passes
263 backend and 44 frontend tests without skips. Evidence:
/private/tmp/dnd-t08-repair1-verify.log. No migration, runtime dependency, UI or
other gameplay handler changed in this repair.

Repair 2 extends the existing signed-URL query check to protocol-relative URLs.
Public validate_archive regressions first failed for both S3 and Azure signed
forms in config, metadata and payload (six failures); the focused slice now
passes 22 tests. Unsigned protocol-relative URLs, ordinary gameplay fields,
valid two-room state and legitimately nullable links remain unchanged.
Final env-free make verify passes 279 backend and 44 frontend tests without
skips, branch coverage 87.77%, plus lint, mypy, TypeScript, build and project/spec
validation. Evidence: /private/tmp/dnd-t08-repair2-verify.log. This repair changes
only URL matching, its regressions and this evidence; SQL and UI are unchanged.

Early focused checks used source cwd, where default application import could
consult source settings before explicit isolated fixture overrides. No values
were printed or hosted connections used; final checks use an env-free snapshot
and explicit localhost database/Redis settings. Hosted Auth/Storage, remote
provider writes after process crash, WAN, physical devices, Firefox/Safari and
five real game sessions remain unverified. Recovery/cleanup promises are limited
to observed adapter timeout/grace and retry behavior, not universal distributed
transaction guarantees.

## Final branch repair: portable scope and confirmed assets

Every portable text subtree, including typed card notes, subtitle, fields,
ability descriptions and inventory names, is checked for known signed URLs
before export bytes or import Storage writes. Unsafe text fails with a generic
`unsafe_config` and never echoes the URL. Ordinary gameplay text and unsigned
public reference URLs retain their exact values; source cards are unchanged.

Unused pending image metadata is excluded from confirmed campaign exports,
without deleting or changing the abandoned upload. All ready library images
remain portable. A pending image referenced by confirmed gameplay still fails
`asset_unavailable` rather than producing a broken archive.

Scene origin-room refs preserve provenance, while active-scene and history scene
refs use campaign scope. Shared scene items, annotations and presentations may
refer to campaign actors/cards originating in another room. Card ownership and
history authors still require their own room; mandatory/null/missing and
out-of-archive refs remain validated before writes. Restoring two rooms that
display one scene creates one shared remapped scene and preserves its content,
without weakening room-local gameplay/card access.

Public repair evidence: `tests/campaign_transfer/test_branch_repair.py` covers
signed text rejection and ordinary-text roundtrip, abandoned invalid upload
read-back, and two-room scene/token/card/annotation/history restore.
`test_validation_repair.py` retains mandatory and unknown-reference negative
controls and adds explicit same-campaign shared-graph positive controls.
