# Construction Control — Phase 32.15

## Local master ↔ Render backup/restore

Phase 32.15 adds an administrator-only full backup/restore workflow so a tested LOCAL database can be backed up and restored into the Render persistent database without manually copying SQLite files.

### Settings → Backup & restore

- **Download Full Backup** creates a ZIP containing a consistent SQLite database snapshot and uploaded files.
- **Restore Full Backup** accepts that ZIP and performs a full destination replacement.
- The server automatically creates a **pre-restore backup** in its persistent `backups` directory before replacement.
- Active login sessions are deliberately excluded from backups; after restore, sign in again.
- Restores are restricted to Company Administrators and the backup must contain the current company ID.
- The destination database is integrity-checked before replacement.
- Unsafe ZIP paths are rejected.

### Recommended workflow

1. Work on LOCAL and make/test edits.
2. Open Settings → Backup & restore.
3. Download Full Backup.
4. Keep the ZIP as a dated master backup.
5. Deploy the same application code to Render.
6. On Render, open Settings → Backup & restore.
7. Restore the selected LOCAL backup.
8. Sign in again.

This is a **full replacement**, not a merge. Do not restore an old backup over newer live data unless that is intentional.

## DUB84

DUB10, DUB50 and DUB84 remain seeded. DUB84 contains 264 programme activities.
