# Build information

Version: Phase 32.18 Render / 565KB no-disk rebuild

Purpose: clean repository package for a fresh Render deployment.

Key fixes:
- Removed Render persistent-disk requirement.
- Fixed the Phase 32.17/32.18 JavaScript `enhanceButtonHints(m)` runtime error in `modal()`.
- Added client-side startup error reporting instead of a silent blank page.
- Added asset cache-busting query strings.
- Bundled the current SQLite database and DUB84 programme source.
- Render Docker image copies the bundled database on first runtime bootstrap only when the configured runtime DB is absent.
