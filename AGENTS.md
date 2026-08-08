# DnD VTT Development Contract

Use `$development-os` for every feature, fix, refactor, migration,
release-preparation, or implementation-planning task.

Repository truth lives in:

1. this file;
2. `.ai-studio/project.yaml`;
3. manifests, source, tests, CI, and runbooks;
4. `docs/specs/` and `docs/adr/`.

The product is a greenfield, Owlbear Rodeo 2.0-inspired, map-first VTT. Do not
restore the legacy monolith or its competing event/state/save systems. The
legacy snapshot is preserved by the `legacy-4940146` tag.

FastAPI is the sole gameplay authority. Durable state belongs in Supabase
Postgres; Redis is ephemeral. React may use Supabase Auth and approved Storage
flows, but it must not mutate gameplay tables through the Data API.

Validate `.ai-studio/project.yaml` before complex work and validate
requirement-to-evidence traceability for complex specifications. Do not push,
merge, deploy, change secrets, or mutate external systems without explicit
authority.
