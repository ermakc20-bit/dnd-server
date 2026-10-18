# ADR-005 — Versioned cards and deterministic import

## Status

Accepted; implemented by VTT-003, 005 and 007.

## Decision

Card, ability, templates and transfer formats declare schema versions. Neutral
user-defined fields/resources remain supported; system packages supply validated
structure without replacing the common model. Each imported instance owns its
IDs and current resources. Ability geometry visualizes an area; automation is
null, range is guidance and game legality remains a human decision.

JSON/XLSX/DOCX/TXT/PDF/legacy HTML parsing is deterministic and bounded. Source
bytes first produce editable drafts and source-linked diagnostics. Only an
explicit acknowledged import.confirm creates cards/tokens through SceneService.
No model, AI SDK or external inference service participates.

## Consequences and evidence

Malformed/hostile documents fail safely, unknown schema versions are rejected,
and cancellation/expiry logically remove source bytes. File and process limits
are documented in VTT-005; logical removal does not promise WAL/backup erasure.
`tests/card_import`, `tests/system_packages`, card-instance resource tests and
native filled-template acceptance verify the decision. Full rules automation and
licensed commercial content remain outside this version.
