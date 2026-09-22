# Phase 32.11 — DUB84 Render Visibility Repair

## Purpose
DUB84 was included in the Phase 32.10 source package, but a live Render deployment could still hide it from users whose project-access rows were not present on the persistent database.

## Repair
On every startup, the application now:
- seeds DUB84 from `data/dub84_programme.json` if the project/programme is missing;
- preserves existing DUB84 tasks and live progress once tasks exist;
- repairs project-access rows for all active users in company C1 for DUB10, DUB50 and DUB84;
- does not alter access for user-created projects.

This specifically repairs an already-existing persistent Render database after deployment.

## DUB84 source
- 264 imported activities
- 01/09/2026 to 25/11/2026
- peak planned manpower 34
- 60 source manloader days
- source workbook retained separately from the app database workflow

## Deployment
Deploy this package to the existing Render service `daily-program-management` using the included `render.yaml` and keep the persistent disk mounted at `/var/data`.
