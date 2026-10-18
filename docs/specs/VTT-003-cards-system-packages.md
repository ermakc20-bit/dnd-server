# VTT-003 — Native cards and declarative system packages

## Goal

Give the GM a native Russian-language card constructor inside the existing map-first
room. Players receive a server-filtered view and may change only current resources
on assigned cards. HTML is a static export, never a second gameplay database.

## Requirements

- `FR-CARD-DATA`: versioned unique player-character, NPC, mob and object cards hold
  custom typed fields, resources, skills, inventory, abilities and visibility.
- `FR-CARD-PACKAGES`: neutral and Russian d20-like version-1 schemas are declarative;
  absent package fields remain absent and custom extensions are preserved.
- `FR-CARD-COMMANDS`: create, update, clone and resource changes use the accepted
  room command/receipt/version/event transaction; clones have independent resources.
- `FR-CARD-LIFECYCLE`: ordinary linked-token duplication creates a separate deep card copy;
  NPC/mob defaults are private; GM deletion uses reversible campaign trash with safe references.
- `FR-CARD-UI`: the map remains visible alongside searchable paged cards, a structured
  constructor, ownership selection and current-resource controls.
- `FR-CARD-EXPORT`: authorized canonical JSON round-trips and safe static HTML
  embeds the same versioned data without executable scripts or external assets.
- `NFR-CARD-ACCESS`: room/actor/owner policy, filtered fields and token references,
  closed Data API grants, RLS and foreign keys prevent cross-room access.
- `NFR-CARD-SAFETY`: automation stays null; no AI/LLM dependency or runtime call;
  stale drafts cannot replace newer acknowledged state unnoticed.

Autopilot mapping: R04/R08/R09/G04/G12/G13/G17/G18/G23/G27 map to the native
constructor, card schema and read/export flow; R12i to no AI; G07/G10 to stored
versioned ability metadata only; G22 to actor attribution and access control.
D14 adds lifecycle and compensating undo through the existing authority. Import parsing,
rule execution, realtime transport and hosted-provider acceptance keep their own contracts.

## Acceptance criteria

- [x] `AC-DATA` covers `FR-CARD-DATA`: four kinds, custom fields and blood resources
  persist; generated IDs, version and timestamps are returned from saved state.
- [x] `AC-PACKAGES` covers `FR-CARD-PACKAGES`: two known versioned packages, six
  attributes, defense, initiative, speed, saves, skills and HP; invalid reserved
  field types and unsupported versions are rejected without dropping extensions.
- [x] `AC-COMMANDS` covers `FR-CARD-COMMANDS`: duplicates preserve receipts and one
  event; resources/clones are independent; scene and card commands share versions.
- [x] `AC-UI` covers `FR-CARD-UI`: structured Russian forms, named player assignment,
  paged search (20 cards per page, maximum server page 50), resources and export.
- [x] `AC-EXPORT` covers `FR-CARD-EXPORT`: JSON validates as Card; HTML escapes all
  supplied text and embeds inert JSON under a restrictive CSP.
- [x] `AC-ACCESS` covers `NFR-CARD-ACCESS`: GM-only entries/notes never serialize to
  players; export requires GM permission and ownership; hidden card IDs are removed
  from token projections. Partial map-card links are rejected before SQL mutation.
- [x] `AC-SAFETY` covers `NFR-CARD-SAFETY`: automation values other than null are
  rejected; existing dependency versions are unchanged; stale editor data stays in
  the form and requires reopening current state.

- [x] `AC-LIFECYCLE` covers `FR-CARD-LIFECYCLE`: linked duplicate preserves a valid agreed
  owner, clears external_key and remints card/inventory/ability IDs in the token transaction.
  Receipt retry adds no copy. An explicitly public silhouette retains a null unauthorized
  card_id; omitted token visibility inherits its card. New native NPC/mob forms and server
  create/import default to gm_only while explicit GM visibility and existing rows persist.
  GM item.delete/card.delete retain tombstones; card_in_use rejects active representations.
  Active lists, resource/presentation origins and archive state exclude trash. Latest create,
  clone, linked creation, duplicate, update, resource and delete compensate with new versions.

## Evidence map

- `AC-DATA`: `tests/cards/test_cards.py::test_native_card_create_projection_and_canonical_event`.
- `AC-PACKAGES`: `tests/system_packages/test_schema.py` and
  `test_package_validation_keeps_extensions_and_rejects_rules` in the card suite.
- `AC-COMMANDS`: `test_card_update_resource_clone_permissions_and_one_version_stream`;
  existing `tests/scenes/test_commands.py` canonical event and idempotency regressions.
- `AC-UI`: `frontend/src/features/cards/CardFlow.test.tsx` plus the Cards tab integration
  in `frontend/src/features/scene/SceneExperience.test.tsx`; separate rendered check below.
- `AC-EXPORT`: `test_export_is_authorized_versioned_roundtrip_and_script_safe` and
  an actual downloaded player HTML opened through a plain loopback static server.
- `AC-ACCESS`: `test_token_card_link_is_authorized_and_hidden_ids_are_not_projected`,
  `test_map_cannot_acquire_card_link_through_partial_update`, resource permission tests
  and `supabase/tests/cards.sql` (15 assertions, fixtures rolled back).
- `AC-SAFETY`: package/card behavior tests, `frontend/src/features/cards/CardsPanel.test.tsx`,
  unchanged lockfiles and product-dependency inspection.

Rendered verification on 2026-10-11 used the actual SceneExperience, Pixi canvas,
card components and API on loopback with a disposable auth-provider fixture, real
registered JWT/guest-cookie resolvers and synthetic PostgreSQL rows. The GM created
a mob with a custom field, GM-only field, GM-only notes, blood and HP resources,
assigned it to the named guest, allowed export, created its token and cloned it.
The guest saw neither secret nor structure controls, changed blood 5 to 3 and HP
10 to 7; the unassigned clone stayed at blood 5 and HP 10 with disabled controls.
Player HTML contained only the permitted projection, canonical schema_version 1,
values 3/8 and 7/10, and zero executable scripts on a plain static server.
Desktop 1440x1100 and tablet 768x1024 were exercised. Harnesses and screenshots live
outside the repository. This is local runtime evidence, not hosted Auth/Storage,
realtime delivery, FPS, Safari/Firefox, phone preparation or public-release acceptance.

- `AC-LIFECYCLE`: tests/cards/test_blind_lifecycle_repair.py; tests/card_import/test_parse.py
  import privacy control; tests/campaign_transfer/test_transfer.py ZIP trash roundtrip;
  frontend/src/features/cards/CardLifecycle.test.tsx; supabase/tests/cards.sql (23 assertions).
  Native local GM/guest lifecycle uses the actual AppView and public authority with read-back;
  it does not establish hosted access or completed real games.

## Public interfaces

Existing `POST /api/v1/rooms/{room_id}/scene/commands` accepts:

- `card.create {card: CardData}`.
- `card.update {card_id: UUID, card: CardData}` (replace editable data, GM only).
- `card.clone {card_id: UUID, name?: string|null}` (new ID, new nested IDs, no owner,
  external key or player export permission; copied current values are independent).
- `card.resource {card_id: UUID, resource_key: string, current: number}`.
- `card.delete {card_id: UUID}` and `item.delete {item_id: UUID}` are GM-only and soft-delete.
  card_in_use requires deleting active linked tokens first; token deletion keeps its library card.
  One additive migration 20261015090000_card_token_soft_delete.sql provides deleted_at and
  deferred active-card reference guards; existing migrations and RLS grants stay unchanged.
- `action.undo {event_cursor}` compensates the latest supported card/resource/presentation
  or token action, including card changes before the first scene. Receipt/event history persists;
  stale entity state or unavailable owner/image/card/origin rejects restoration.

The existing `Command`/`CommandResult` envelope does not change. Canonical internal
card-event payload is `{card_id: string, card: Card}` read after persistence in the
same transaction. `event.scene_id` may be null before the first scene. Private event
payloads are not a player-facing contract; future fan-out must project per actor.
Token commands and canonical item events gain nullable `card_id`; the scene read
projection replaces unauthorized card references with null (batched authorization).

- `GET /api/v1/system-packages/{system_id}/{version}` returns schema_version,
  system_id, version, name, automation:null and defaults:{fields,resources,skills}.
- `GET /api/v1/rooms/{room_id}/cards?offset=0&limit=20&search=` returns
  `CardPage {cards: CardView[], offset, limit, has_more}`.
- `GET /api/v1/rooms/{room_id}/cards/{card_id}` returns `CardView`.
- `GET /api/v1/rooms/{room_id}/cards/{card_id}/export?format=json|html` returns
  an authorized attachment with no-store and nosniff headers.
- `get_schema(system_id: str, version: int=1) -> dict[str, Any]`;
  `validate_card(data: CardData) -> CardData`.

`CardData` includes schema_version:1, system_id/system_version, kind, name, subtitle,
external_key, image_asset_id, owner_participant_id, visibility, allow_player_export,
fields, resources, skills, inventory, abilities, notes and notes_visibility.
`Card` adds id/campaign_id/room_id/version/created_at/updated_at. `CardView` adds
can_edit_structure/can_edit_current/can_export; these flags are not exported.
Ability schema_version is 1; automation is only null. Geometry is validated metadata
for the subsequent geometry task, not an executable rule or preview implementation.

## Migration and rollback

`20261011185411_cards_system_packages.sql` was generated by the local CLI's
`supabase migration new cards_system_packages`. It creates app.cards with RLS,
revokes all public/anon/authenticated grants, constrains room/campaign/owner/image
relations, enforces a numeric schema_version 1 and adds the token-only card link.
FastAPI is the sole gameplay writer; no SECURITY DEFINER function was introduced.
Local SQL read-back verified RLS and grants; pgTAP ran in rollback transactions.
No hosted migration/advisor upload/reset was performed. Reverting deployed data
would require a separately authorized forward migration, never a database reset.

## F10 — native typed field fidelity (D22)

The existing card view renders nonempty skill proficiency/description, inventory
text icon/description, and ability action type and uses label/current/maximum.
Zero remaining uses is displayed as zero; an absent maximum is shown as infinity.
Absent optional metadata adds no placeholder rows. Icons and descriptions stay
React text, including text resembling HTML or URLs; no icon fetch is introduced.

The existing GM constructor and import-review constructor share CardEditor.
They edit/clear skill proficiency and description, item description/icon, ability
action type, and optional ability uses. Enabling a counter creates an explicit
manual resource with current zero and no maximum; disabling it sets uses to null.
An empty maximum remains null, while current zero remains numeric zero. Resource
keys, colors, visibility, sibling entries and nested IDs survive ordinary edits.
The same existing card.update/import draft-save paths persist the complete data.

No player counter action or automatic spend/rule execution is added. Existing
can_edit_structure, disabled editing, current-resource commands, geometry and
ability-launch gates retain their meaning. CardData/API/types/DDL/dependencies,
exports and the local Old Russia corpus remain unchanged.

Evidence for AC-UI/AC-ACCESS/AC-SAFETY:
`frontend/src/features/cards/CardFields.test.tsx` covers inert projected display,
zero values and unchanged player controls; complete GM update payloads with
sibling/ID/geometry preservation and optional maxima; and import draft editing,
optional counter addition/removal, clearing, disabled controls, saving and the
existing confirmation command. Native runtime acceptance and the full verification
suite remain separate checks of the frozen implementation.
