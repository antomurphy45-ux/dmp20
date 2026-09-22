# Phase 32.9 QA — Persistent Data Protection

Date: 2026-09-21

## Problem addressed
User-created projects and users were disappearing after the application was restarted/redeployed. The code was inspected rather than assuming the seed routine was deleting records.

## Root cause / risk identified
The application uses SQLite. Data survives a process restart only when the same SQLite file is reused. On Render, the database must live under a persistent disk mount. Render documents that service filesystems are ephemeral by default and that only data under an attached persistent disk mount survives deploys/restarts.

The live service name is `daily-program-management`, while the previous Blueprint was named `construction-control`. Phase 32.9 aligns the Blueprint name with the live service and explicitly defines the persistent disk and database environment variables.

The seed routine is idempotent: it inserts missing demo data but does not delete arbitrary user-created projects/users. A dedicated persistence test confirmed that a user-created project and user survive `init_db()`/process restart against the same database file.

## Changes
- Canonical local SQLite path is now `data/construction_control.db`.
- Legacy root `construction_control.db` is migrated once to the canonical local path if present.
- Local uploads default to `data/uploads`.
- SQLite uses a connection timeout, busy timeout, WAL journal mode where supported, and `synchronous=NORMAL` for single-instance resilience.
- Added `/api/storage/status` for Company Administrators.
- `/healthz` now actually routes through the API handler and reports storage status.
- Render deployment requires `/var/data` to be a mounted persistent disk; otherwise `/healthz` returns HTTP 503 with `storage_not_persistent` instead of silently running on ephemeral storage.
- Render Blueprint is named `daily-program-management` and defines a 1 GB `/var/data` persistent disk on the Starter plan.
- Render environment variables explicitly point SQLite and uploads at `/var/data`.

## Tests
- Phase 32.9 persistence test: **PASS**
  - Create project via API
  - Create user via API
  - Stop server
  - Reinitialise same database
  - Verify project remains
  - Verify user remains
- Existing selected regression/integration tests: **21 passed, 0 failed**
- Python compile: **PASS**
- Persistent-storage health guard without mounted disk: **PASS** (HTTP 503)
- Persistent-storage health guard with mounted-disk condition: **PASS** (HTTP 200)
- Root/static asset synchronisation: unchanged and verified by existing regression coverage
- ZIP integrity: verified after packaging

## Not claimed
A full historical pytest run was not completed within the execution limit; therefore this phase is not represented as a full historical-suite pass. Docker itself is not installed in the validation environment, so no local Docker image build is claimed.

## Render requirement
The Render service must actually have the persistent disk attached at `/var/data`. Code and `render.yaml` cannot make an already-existing Render service persistent unless the disk is provisioned/attached. If data was already lost from an ephemeral instance before a disk was attached, the application cannot reconstruct that data from the current database.
