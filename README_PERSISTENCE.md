# Construction Control — Data Persistence

## Phase 32.18 Render no-disk mode

The application can run using the existing SQLite database on Render without requiring a Render persistent disk. The live Render database path remains:

`/var/render_seed.db`

This mode is intended to keep the current approximately 565 KB database usable without requiring a paid persistent disk.

### Important limitation

Render service storage is ephemeral when no persistent disk is attached. The database can therefore be lost when Render replaces or recreates the service. This build does **not** pretend that ephemeral storage is permanent.

Use **Settings → Backup & Restore → Download Full Backup** before deploying changes or performing service maintenance. The restore function can restore the complete SQLite database and uploads.

### Local

`START_LOCAL.bat` uses:

`render_seed.db`

That file is retained between local restarts.

### Health check

`/healthz` returns HTTP 200 when the application and database are usable. If `/var/data` is not a mounted persistent filesystem, the response includes a warning rather than blocking the application.

No existing database is replaced by startup seeding; the existing DUB10, DUB50, DUB84, staff and training data are preserved when the database is present.
