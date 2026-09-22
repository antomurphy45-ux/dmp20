# Phase 32.15 QA

## Implemented

- Administrator-only full database backup endpoint.
- SQLite backup API used to produce a consistent snapshot rather than copying a live WAL file directly.
- Active sessions excluded from backups.
- Uploaded files included in backup ZIPs.
- Backup manifest and integrity validation.
- Safe ZIP path validation.
- Company ID validation on restore.
- Automatic pre-restore server backup.
- Full destination database replacement followed by upload restoration.
- Settings UI for download/restore.
- Storage status displayed in Settings.
- Local canonical database remains `data/construction_control.db`.
- Render remains configured for `/var/data/construction_control.db` and persistent disk.
- DUB10/DUB50/DUB84 retained; DUB84 has 264 activities.

## Tests actually run

Selected Phase 32 regression/integration suite: **26 passed**.

Included:
- backup/restore round-trip
- persistence across restart
- DUB84 seed and 264 activities
- theme contract
- daily operating sequence
- DUB project coverage
- assignment → daily control integration
- function contract
- security user serialization
- production readiness

Python compilation: PASS.

## Not claimed

The full historical pytest suite has not been claimed as passing. Docker was not available in the validation environment, so an actual Docker image build was not claimed locally.
