# Phase 32.20 QA — PM Daily Cockpit / RAG Reasons / External Approvals

## Implemented
- Project RAG badge is clickable and shows a brief live reason.
- Dashboard includes a PM Daily Brief focused on today's actions: chasing, external approvals, manpower checks, and tasks starting today.
- External Approval Watch List added for client/consultant/external responses.
- External approvals support Waiting, Approved, Rejected and Cancelled.
- External approval records support response date and response/decision note.
- Existing document upload storage can attach a response document to an external approval record.
- Existing visual style is retained; additions use the current professional/pastel status palette.

## Targeted tests
- Phase 32.20 PM/RAG source and UI contract: PASS
- Phase 32.19 programme button execution: PASS
- Phase 32.19 training document upload: PASS
- Phase 32.18 staff training: PASS
- Phase 32.16 staff register: PASS
- Combined targeted result: 8 passed

## Runtime API execution
- /healthz: PASS (HTTP 200)
- Login: PASS
- /api/dashboard with as_of=2026-09-22: PASS
- RAG reason returned for live seeded projects: PASS
- External approval create: PASS
- External approval list: PASS
- External approval status update to Approved: PASS
- Document upload against external approval: PASS

## Full-suite status
`pytest -q` was started but exceeded the 180-second execution limit in this environment. It is therefore NOT claimed as a full-suite pass.

## Deployment note
The package remains configured for the existing no-persistent-disk Render approach using the root-level `render_seed.db`. Uploaded documents/database changes remain ephemeral on Render without a persistent disk; use Full Backup before redeploy/restart when data must be preserved.
