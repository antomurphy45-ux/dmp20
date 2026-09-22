# Phase 32.25

## Dashboard boot fix

Render reported:
`dashboardProjectCards is not defined`

The dashboard renderer uses `dashboardProjectCards(projects)` to render the project overview cards. The function was accidentally missing from the Phase 32.24 frontend. It has been restored in both root and static copies of `app.js`.

This phase is a corrective regression fix only; no intended dashboard functionality was removed.
