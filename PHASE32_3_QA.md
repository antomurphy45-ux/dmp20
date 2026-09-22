# Construction Control — Phase 32.3 Function/CRUD Repair QA

## Purpose
Repair the Phase 32.2 compatibility failures found during full function testing, especially Add/Edit task actions, legacy task APIs, duplicate JavaScript handlers, and modal closing.

## Changes
- Unified new task-control statuses: `Starting`, `Ongoing`, `Held Up`, `Finished`.
- Added backwards-compatible handling for legacy API values `Not Started` and `Started`.
- `/api/tasks` create/edit/import now persists `task_status` correctly.
- Daily Site Control infers progress status when a status is omitted by an older client.
- Task alerts and daily late-start logic now use the explicit task-control status.
- Programme task create/edit now persists task status consistently.
- Removed duplicate `modal`, project create/edit function definitions.
- Added safe `closeModal()` so buttons cannot fail when a modal is already absent.
- Root and `static/app.js` are synchronised.
- Render Dockerfile no longer requires a `static/` directory in the Git build context; it creates it from the root assets.
- Existing DUB10 and DUB50 seeded programme/staff/task data preserved.

## Test Results
- Full regression suite: **140 passed, 0 failed**.
- Python syntax: **PASS**.
- JavaScript syntax (`node --check`): **PASS**.
- Root/static JS synchronisation: **PASS**.
- Root/static HTML/CSS synchronisation: **PASS**.
- Inline application button-handler contract: **PASS**.
- Unsafe modal removal calls: **0 remaining**.
- Duplicate `modal()` definitions: **0**; one definition remains.
- DUB10 programme activities: **15**.
- DUB50 programme activities: **15**.
- DUB10 project staff assignments: **9**.
- DUB50 project staff assignments: **9**.
- Docker build-context simulation: **PASS**; Dockerfile no longer contains `COPY static` or `COPY uploads` dependencies.

## Docker limitation
Docker is not installed in the validation environment, so an actual Docker image build was **not** claimed. Render must perform the final container build.

## Browser limitation
The validation environment does not permit unrestricted local Chromium navigation, so physical clicking of every browser button was not claimed. Button coverage was validated through handler-resolution/static-contract tests and the complete HTTP/API workflow suite.
