# Construction Control — Phase 32.9

## Important data persistence change

This version treats database persistence as a deployment requirement rather than an assumption.

### Local

Use `START_LOCAL.bat`. It stores the database at:

`data/construction_control.db`

and uploads at:

`data/uploads`

### Render

The Render package is configured for the current service name:

`daily-program-management`

It requires a paid Render web service with a persistent disk mounted at:

`/var/data`

The SQLite database is:

`/var/data/construction_control.db`

If the persistent disk is not mounted, the application health endpoint returns HTTP 503 instead of allowing a deployment to appear healthy while storing data on an ephemeral filesystem.

### Existing data

The application does not delete user-created projects/users during normal startup. The demo seed is idempotent and only inserts missing records.

If a previous Render deployment stored data on an ephemeral filesystem, that data may already be gone after a redeploy/restart. This version prevents that failure going forward; it cannot recover data that no longer exists.
