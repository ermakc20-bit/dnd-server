# Legacy SQLite migration evidence

Status: source inspected read-only; target import is intentionally not executed.

## Source snapshot

The supplied `dnd-server.rar` contains `dnd-server/dnd_game.db`.

- Size: 77,824 bytes.
- SHA-256: `c0d6d02c200c108e851710f4ed88b866dbdc50399049355feab7999e9f6059e7`.
- `PRAGMA integrity_check`: `ok`.
- `PRAGMA foreign_key_check`: no violations.
- Rows: 2 users, 3 settings, 2 game tables, 1 game token; all other
  gameplay tables are empty.

No login, e-mail, password hash, or other personal value is copied into this
repository. Re-run the redacted inventory with:

```bash
python scripts/audit_legacy_sqlite.py /absolute/path/to/dnd_game.db
```

## Migration contract

1. Back up the original file and verify the SHA-256 before importing.
2. Create Supabase Auth identities from the two legacy accounts through the
   Admin API in a controlled operator run. Never move legacy password hashes
   into Supabase Auth.
3. Store the old numeric ID in `app.profiles.legacy_user_id`, mark
   `legacy_password_reset_required = true`, and send a recovery link.
4. Convert each legacy game table to one room and one scene. Preserve its map
   transform. Convert each legacy game token to a scene item with D&D v1 fields
   in `payload`.
5. Reconcile source and target counts and retain a redacted ID mapping outside
   version control.
6. Ask the owner to approve the reconciliation before switching traffic.

The importer cannot be safely run until the target Supabase project, recovery
mail route, and the legacy-user e-mail policy are approved. This is an external
write and remains outside the current local implementation authority.
