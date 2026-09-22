# Phase 32.2 QA — Daily Operating Sequence + DUB10/DUB50 Population

## Implemented

- Morning Brief with assignment-driven attendance, active work updates, status/progress, held-up reason and notes, and tomorrow's starts.
- End-of-day Close Out that saves final notes without overwriting attendance or task updates.
- Staff/project assignments with dates, role and status. Only the established labour roles are used for seeded project staff: Construction Manager, Foreman, Charge Hand, Electrician, 4th Year, 3rd Year, 2nd Year, 1st Year and GO.
- Project dashboard health: green, amber or red, with management health now checking held-up/overdue work across the project's programmes so a problem cannot be hidden by programme selection.
- DUB10 and DUB50 are now seeded into the application itself, so fresh local installs and fresh/persistent Render databases receive both projects.
- DUB10 and DUB50 each contain a 36-week SOW-based delivery programme with 15 activities, 9 staff assignments and 9 task-staff assignments.
- DUB10 and DUB50 programme activities cover mobilisation, enabling/plinths, MV, LV/UPS/generators, chillers/CRAH, raised floor/containment, fire, BMS/security, copper/fibre, pre-commissioning, Levels 1–3, Level 4, Level 5 IST, handover and practical completion/snags.
- Local and Render configurations are generated from the same source tree.

## Validation actually completed

| Check | Result |
|---|---|
| Python compile | PASS |
| JavaScript syntax | PASS |
| Root/static JS synchronisation | PASS |
| Root/static CSS synchronisation | PASS |
| Phase 32.2 daily operating sequence tests | PASS — 3/3 |
| DUB10/DUB50 population tests | PASS — 2/2 |
| Selected dashboard/morning/branding/regression tests | PASS — 21/21 |
| Combined Phase 32.2 + DUB + selected regression set | PASS — 26/26 |
| Full historical regression suite | NOT COMPLETE/PASS — 120 passed, 15 failed. Failures are primarily legacy tests that still expect the old Not Started/Started status contract and tests that assume only P1 exists; the new DUB10/DUB50 seed intentionally changes those assumptions. These are not claimed as passed. |
| Docker image build | NOT RUN — Docker executable unavailable in this environment |
| Render build context | PASS by static inspection — Dockerfile does not COPY a missing static directory and builds it from root assets |

## DUB10/DUB50 data note

The two projects are intentionally populated as working demonstration/control data from the supplied SOW structure, rather than left as empty project shells. Dates are seeded as a 36-week demonstration programme so the daily workflow has usable programme data immediately. The seeded records are idempotent and do not overwrite user progress on subsequent application starts.
