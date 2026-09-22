# Construction Control — Phase 32.13

## DUB84 Render deployment fix

Phase 32.13 fixes the reason DUB84 did not appear after Render deployment.

The Render Dockerfile now includes the DUB84 programme source file in the image. On startup the existing idempotent seed creates DUB84 and its 264 programme activities if they are missing, without overwriting existing live progress.

Deploy this package to the existing `daily-program-management` Render service. Do not delete the persistent `/var/data` disk/database.
