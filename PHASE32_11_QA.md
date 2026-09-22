# Phase 32.11 QA

## Tests performed
- Python compile: PASS
- DUB84 seed test: PASS
- DUB84: 264 tasks verified
- DUB84 dates: no task has finish before start
- DUB84 source manloader: 60 days verified against task manpower
- Idempotent startup: PASS
- Existing-database access repair: PASS; a newly added C1 user receives access to DUB10, DUB50 and DUB84 after startup

## Important limitation
This package has not been deployed into the user's Render account from this environment. The live Render service must be redeployed with this package.

## Persistence
The package retains the Phase 32.9 persistent-storage guard. Render must have the persistent disk mounted at `/var/data`; otherwise the application intentionally returns a storage warning instead of pretending data will persist.
