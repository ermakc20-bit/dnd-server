# VTT-005 — Deterministic card templates and reviewed import

## Goal and requirement traceability

R04/R09 and G04/G12/G13/G14/G17/G18/G23/G24/D06 are implemented as a GM-only
native import panel: download versioned Russian XLSX/DOCX forms, upload one file,
review/edit/exclude/count drafts, then explicitly confirm independent cards and
optional tokens. No AI service, SDK, OCR or network parser is used.

## Requirements

- `FR-IMPORT-FORMS`: the GM downloads versioned Russian XLSX and DOCX forms with examples.
- `FR-IMPORT-PARSE`: deterministic JSON/XLSX/DOCX and explicitly marked TXT/PDF adapters produce DraftSet v1; a separate adapter reads verified legacy HTML blocks.
- `FR-IMPORT-DIAGNOSTICS`: diagnostics identify severity, entity, section, row and field; unknown labeled fields are preserved.
- `FR-IMPORT-REVIEW`: the GM can resume, edit, exclude and set instance counts before confirmation.
- `FR-IMPORT-CONFIRM`: the existing SceneService transaction creates independent cards and optional tokens atomically, preserving command receipt replay.
- `FR-IMPORT-DUPLICATES`: repeat files require an explicit update-drafts or new-instances choice and never silently overwrite confirmed cards.
- `NFR-IMPORT-ACCESS`: import jobs remain private to their active registered GM creator and room; Data API access is denied.
- `NFR-IMPORT-SOURCE`: source bytes are removed after confirm, cancel or expiry and source content is not logged.
- `NFR-IMPORT-SAFETY`: bounded parsing rejects dangerous archives, XML, formulas, active attachments and PDF actions.
- `NFR-IMPORT-NOAI`: import uses no AI dependency or external inference/network parsing call.
- `NFR-IMPORT-QUALITY`: public-seam tests, full verification, local SQL assertions and actual browser/template checks provide acceptance evidence.

## Acceptance criteria

- [x] `AC-IMPORT-FORMS` covers `FR-IMPORT-FORMS`: both downloaded forms round-trip through the public parser and render readably in a local office renderer.
- [x] `AC-IMPORT-PARSE` covers `FR-IMPORT-PARSE`: repeated parsing is deterministic, v0 compatibility migrates explicitly, future versions fail, and sanitized legacy fixtures retain known semantic values.
- [x] `AC-IMPORT-DIAGNOSTICS` covers `FR-IMPORT-DIAGNOSTICS`: preserved unknown resource fields report their original sheet, row, field and entity.
- [x] `AC-IMPORT-REVIEW` covers `FR-IMPORT-REVIEW`: actual browser editing, exclusion, count changes, save and reload retain the reviewed draft.
- [x] `AC-IMPORT-CONFIRM` covers `FR-IMPORT-CONFIRM`: confirmation creates unique cards and linked tokens; repeated receipt creates no extra batch; a late invalid reference rolls back all writes.
- [x] `AC-IMPORT-DUPLICATES` covers `FR-IMPORT-DUPLICATES`: duplicate upload returns an explicit choice and concurrent uploads cannot silently create two jobs.
- [x] `AC-IMPORT-ACCESS` covers `NFR-IMPORT-ACCESS`: players, another GM and another room cannot read or confirm the creator's job; SQL checks verify RLS and revoked direct rights.
- [x] `AC-IMPORT-SOURCE` covers `NFR-IMPORT-SOURCE`: confirm, cancel and expiry null source bytes; parser failures do not log the private source marker.
- [x] `AC-IMPORT-SAFETY` covers `NFR-IMPORT-SAFETY`: malicious Office/PDF, oversized/corrupt/unmarked content and child processing deadline cases fail safely.
- [x] `AC-IMPORT-NOAI` covers `NFR-IMPORT-NOAI`: the import module and dependency declarations pass the static no-AI/network-client check.
- [x] `AC-IMPORT-QUALITY` covers `NFR-IMPORT-QUALITY`: full make verify, all local pgTAP files, actual browser scenarios and this document's traceability validator pass.

## Evidence map

- `AC-IMPORT-FORMS`: tests/card_import/test_parse.py::test_templates_roundtrip_and_explicit_markup; actual downloaded DOCX/XLSX browser and LibreOffice evidence described below.
- `AC-IMPORT-PARSE`: tests/card_import/test_parse.py JSON/v0, legacy semantic, future-card-version and explicit Unicode PDF tests; templates/cards/README.md compatibility contract.
- `AC-IMPORT-DIAGNOSTICS`: tests/card_import/test_parse.py::test_xlsx_unknown_resource_field_reports_original_sheet_and_row and JSON unknown-field assertions.
- `AC-IMPORT-REVIEW`: frontend/src/features/card-import/ImportPanel.test.tsx and /private/tmp/dnd-vtt-ticket05-browser.cjs actual saved-draft reload scenario.
- `AC-IMPORT-CONFIRM`: tests/card_import/test_jobs.py atomic confirmation/receipt and late-reference rollback tests; browser verifies three unique cards and three unique linked tokens.
- `AC-IMPORT-DUPLICATES`: tests/card_import/test_jobs.py explicit duplicates and concurrent upload scenarios; browser repeat-file choice.
- `AC-IMPORT-ACCESS`: tests/card_import/test_jobs.py player/other-GM/cross-room assertions; supabase/tests/card_import.sql nine private-schema assertions; actual guest browser API403.
- `AC-IMPORT-SOURCE`: tests/card_import/test_jobs.py confirm/cancel/expiry source-null assertions; tests/card_import/test_limits.py private-marker logging assertion.
- `AC-IMPORT-SAFETY`: tests/card_import/test_parse.py unsafe ZIP/XML and PDF action cases; tests/card_import/test_limits.py formula/size/corruption and bounded worker deadline cases.
- `AC-IMPORT-NOAI`: tests/card_import/test_limits.py::test_static_import_graph_has_no_ai_or_network_clients.
- `AC-IMPORT-QUALITY`: /private/tmp/dnd-vtt-ticket05-verify.log, /private/tmp/dnd-vtt-ticket05-sql-tests.log and scripts/validate_spec.py --spec docs/specs/VTT-005-card-import.md.

## Public contracts

- `parse(data: bytes, format: str) -> DraftSet`; `parse_bounded(...)` runs that
  same parser in an isolated child process. Formats: JSON/XLSX/DOCX/TXT/PDF/HTML.
- `DraftSet={schema_version:1,drafts:CardDraft[],diagnostics:Diagnostic[]}`;
  `CardDraft={external_key,card:CardData,count,included,create_token,source}`.
  Diagnostics contain severity/code/message/entity/section/row/field; document
  parser exceptions are never exposed. Unknown labeled fields become extra fields.
- `GET /api/v1/rooms/{room_id}/imports/templates/{xlsx|docx|txt}` downloads forms.
- `POST .../imports?format=...&mode=update_drafts|new_instances` accepts raw bytes
  with matching MIME or application/octet-stream. Mode is optional for a new hash;
  repeat file without choice returns 409 `duplicate_file`.
- `GET .../imports` lists the creator's open jobs; `GET .../imports/{job_id}`
  resumes a durable draft. `PATCH` accepts `{expected_version,drafts}`;
  `DELETE .../{job_id}?expected_version=N` cancels and removes source bytes.
- Existing `SceneService` command `import.confirm` accepts
  `{job_id,expected_job_version}`. There is no parallel command engine: room lock,
  expected aggregate version, receipt, savepoint, event insert and post-commit
  realtime publication remain owned by the existing service. Same command ID
  returns its receipt; retry cannot create another batch.
- Canonical event payload has `job_id,card_ids,cards,items`; player realtime sees
  only authorized `cards.changed` invalidation, never raw import data.

`templates/cards/README.md` specifies v1 and the explicit compatible v0 contract.
v0 is not claimed as a historical release. Golden JSON examples are checked in;
XLSX/DOCX are generated by application code and round-tripped through public parse.
TXT, extracted PDF text and arbitrary DOCX must contain literal version/card/field
markup. Unmarked prose, image-only PDF and unknown HTML layouts are unsupported.

## Security and data lifecycle

Input limit 5 MiB; expanded Office archive 20 MiB/500 entries; 100 drafts;
200 included instances; 5 MiB expanded canonical card output; ten open jobs per
creator/room. PDF limit 100 pages and bounded object traversal. Parsing has two
process slots, 8-second wall deadline and 5-second CPU budget. Linux uses a
768 MiB address-space limit. macOS does not implement that limit: its child uses
a 10 ms RSS watchdog (not a hard instantaneous memory ceiling), plus the same
input/expanded-data limits and forced process kill/reap at the wall deadline.

ZIP traversal/symlinks/encryption/duplicate entries, formulas/macros/active
attachments/external relationships/XML DTD/entities and PDF actions/embedded
files/external URI actions are rejected. Child environment excludes application
secrets; stderr and parser logging are suppressed. HTML is parsed as inert text
and known semantic blocks; script/style/iframe/object content is not executed.
No raw source, filename or parser exception is logged or returned to another actor.

`app.import_jobs` is a backend-only table with RLS enabled and all Data API rights
revoked from public/anon/authenticated. Every API/action checks active registered
GM authority, room/campaign and creator identity, including another GM in the
same room. Confirm creates cards, independently regenerated nested IDs, tokens,
receipt/event and source deletion in one transaction. A late invalid reference
rolls back the entire batch. Imported exported record IDs are never reused.

Source bytes are nulled after confirm/cancel, and after 24-hour expiry by a
60-second API lifecycle cleanup task and access-time cleanup. API must be running
for periodic cleanup; startup catches up. This is logical database deletion, not
a promise to erase PostgreSQL WAL/backups. Draft JSON remains private preparation
history. Re-upload only updates open drafts by stable key; completed cards are
never silently overwritten.

## Evidence — local only, 2026-10-12

- `tests/card_import/test_parse.py`: deterministic JSON/v0, generated forms,
  correct original sheet/row for unknown fields, future-version rejection,
  marked Unicode PDF and PDF actions, dangerous ZIP/XML parts, sanitized actual
  Vampires/Old Russia semantic fixtures. Actual numbered source documents were
  also parsed read-only: 22 Old Russia and 6 Vampires; index.html is not a card.
- `test_limits.py`: oversized/compressed/corrupt/unmarked input, real child
  timeout/cleanup, no source marker in logs, static no-AI/network-client scan.
- `test_jobs.py`: public HTTP + existing command service, edit/exclude/count,
  atomic optional tokens, repeat receipt, concurrent duplicate upload, optimistic
  versions, private jobs, player/other-GM/cross-room denial, filtered realtime,
  rollback after first card, cancel and expiry source cleanup.
- `ImportPanel.test.tsx`: native draft editor/count/exclude/token + save-before-
  shared-command flow. Existing lost-ack/realtime tests remain unchanged and green.
- Full `make verify VENV=/private/tmp/dnd-vtt-ticket01-venv` with both local test
  URLs: **115 backend + 34 frontend**, coverage **88.93%** (baseline 94 + 33).
  Lint/mypy/TypeScript/build/traceability passed; existing large-chunk warning remains.
- New migration was created by project Supabase CLI 2.111.0, rehearsed in
  BEGIN/ROLLBACK with RLS/revoke assertions, then applied only to the local test
  DB. All five pgTAP files passed in a newly created disposable local database:
  **70/70** (61 baseline + 9 import), each test rolled back, then database dropped.
  No shared-db reset. Reproducer: `/private/tmp/dnd-vtt-ticket05-sql-tests.py`.
- Supabase CLI advisors ran with explicit DB URL at **127.0.0.1:55432**, never
  linked/hosted, `sslmode=disable` for loopback test PostgreSQL. Before running,
  official CLI v2.111.0 `advisors.go` RunLocal/queryLints was inspected: embedded
  SQL over the supplied direct connection inside a rollback transaction; linked
  API path is separate. Result **51 INFO, 0 WARN, 0 ERROR**. T05 INFO items:
  two composite FK covering indexes, one unused index, intentional RLS/no-policy
  backend-only table. This is not a hosted exposure audit or production gate.
  Evidence: `/private/tmp/dnd-vtt-ticket05-advisors.json`.
- Real Chromium, real SceneExperience/HTTP/JWT and guest cookie/PG/Redis:
  both template downloads and uploads, edit/exclude/count, saved reload, three
  unique confirmed cards and three unique linked tokens, repeat-choice, cancel,
  guest button absent + API403. Desktop 1440 and tablet 1024 screenshots checked;
  local contrast corrected, no horizontal overflow/blank view/covering overlay,
  no unexpected browser console/page errors. Browser evidence is under
  `/private/tmp/dnd-vtt-ticket05-*`; no runtime/debug routes ship in product.
- Matching runtime copy: `/private/tmp/dnd-vtt-ticket05-runtime-check`;
  URL `http://127.0.0.1:5195/realtime-runtime.html` (guest `?role=0`). Bundled
  LibreOffice rendered the actual downloaded DOCX/XLSX locally with private
  temporary profiles; generated documents contain no formulas.

## Dependencies and remaining operational concerns

Only six new pins: openpyxl 3.1.5, python-docx 1.2.0, pypdf 6.20.0,
defusedxml 0.7.1, et-xmlfile 2.0.0, lxml **6.1.0**. The initially considered
lxml 6.0.2 was replaced before acceptance for GHSA-vfmq-68hx-4jfw/CVE-2026-41066;
explicit XML/XXE guards remain. Parent independently audited all six installed
new packages: zero known advisories. The wider pre-existing environment still
has 19 advisories across pip/pyjwt/urllib3; those unrelated packages were not
upgraded in this slice. No hosted rollout, deployment, push or commit performed.

CLI local-only implementation reference:
[Supabase CLI v2.111.0 advisors](https://github.com/supabase/cli/blob/v2.111.0/apps/cli-go/internal/db/advisors/advisors.go).

## F5 confirmed-import compensation

`import.confirm` is a gameplay command in the existing room transaction. Its
latest unconsumed forward event can be compensated using `action.undo`; only
the card/token IDs created by that command move to campaign trash. Current
object versions and outside live token references must still permit removal.
The original job remains confirmed, with unchanged card IDs, version and
receipt. Raw source bytes and unknown fragments stay erased. Original confirm
replay returns its receipt; a fresh confirm cannot create another batch.
Evidence: `tests/card_import/test_undo_confirm.py`, including count two with
and without tokens and preservation of an unrelated existing card.

## F9 — selected local Old Russia canonical bridge (D21)

The explicit build command and dependencies are documented in
`templates/cards/README.md`. `scripts/old_russia_export.py --cards-root PATH`
accepts `--output-dir PATH` and/or `--apply`. It is a bounded data reader, never
an HTML/JavaScript executor. Unknown overview fields, duplicate keys, active
literal expressions, unknown rich semantic classes and invalid typed values
are rejected. Single files are CardData v1; batch is `{schema_version:1,cards}`.
The existing public parse/review/edit/confirm contracts remain unchanged.

The available unique corpus is exactly 22: five player characters, nine NPCs,
eight mobs. Five root hero HTML originals are duplicates, not extra entities.
The checked-in compact real fixture preserves the overview source data and
semantic hero body markup without CSS or scripts. Typed resources, skills,
inventory and abilities retain rich hero state and text; labeled fields and
notes retain the remaining source semantics. Geometry/quantity/rules are never
inferred from prose, and source HTML is never stored as an opaque card field.

`--apply` owns exactly builder + both indexes + 22 generated pages + one local
asset. Browser downloads require no network or Python; generation uses the
existing Node runtime. The asset's local installer restores exports after the
old builder runs. A preflight hook rejects every symlink leaf/ancestor in the
complete owned write set and changed source fingerprints before the builder's
first write, preserving existing exports on failure, until the explicit bridge
is rerun. Original root hero files and unrelated corpus files are outside
this write set. Apply is byte-idempotent; the caller retains backups and exact
before/after hashes before applying to real user files.

The open generated page overlays only its current HP/proficiency/uses; visible
overview cards overlay their own current HP. Other pages and filtered-out cards
retain baseline data. Invalid DOM state stops export visibly rather than
silently defaulting/clamping. No arbitrary localStorage, auth or script values
are copied. Both indexes and all 22 generated pages expose single/batch JSON.

Permanent evidence: `tests/card_import/test_old_russia_export.py` verifies the
real 22-card typed round trip and stable IDs/bytes, apply + regeneration + original
preservation, actual client click/download with 0 HP/proficiency/spent uses and
visible invalid-state rejection, plus rejection of an unmapped semantic block
and an active JS expression. Actual Chrome download/native 22-card confirmation
is a separate runtime acceptance check, not inferred from those unit tests.
The earlier dated note about six Vampires originals is historical and has not
been independently reconfirmed: no unavailable Vampires originals are claimed
as migrated or accepted by this slice. Hosted/WAN/physical devices and real game
sessions remain outside this local corpus proof.
