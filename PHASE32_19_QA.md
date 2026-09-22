# Phase 32.19 QA

## Scope
- Programme activity actions moved onto the far-right end of each Gantt row.
- Removed the repeated Activities list below the Gantt, so normal programme editing stays on one screen.
- Gantt order is now: Activity -> Progress / Critical Path -> Scheduled -> Options.
- Options are Edit / Move / Delete with button explanations.
- Staff training records now support uploading, opening and deleting certificate/supporting documents (10 MB limit).
- Fixed Excel export failure when a programme name contains Unicode punctuation such as the DUB84 em dash.

## Button execution test
`tests/test_phase32_19_programme_button_execution.py` executes the backend actions represented by every programme button in the supplied screenshots:
- + Activity
- Edit
- Move
- Delete
- Set baseline
- Resources
- Look-ahead
- Baseline vs Current
- Live Progress
- Update Programme
- Calendar (add + delete exception)
- Control Centre
- Import Excel (round-trip validation using the exported workbook)
- Export Excel

Result: **1/1 passed**.

## Training document test
`tests/test_phase32_19_training_documents.py` verifies upload -> list -> download -> delete persistence.

Result: **1/1 passed**.

## UI contract test
`tests/test_phase32_19_ui_contract.py` verifies all screenshot button labels, the new one-row Gantt action layout and training document upload controls.

Result: **2/2 passed**.

## Related regression tests
- Phase 32.17 programme editing: 3/3 passed.
- Phase 32.18 training CRUD: 1/1 passed.
- Phase 32.15 backup/restore: 1/1 passed.

Combined targeted result: **9/9 passed**.

## Browser note
A Playwright browser-click run was attempted, but the execution environment blocks Chromium navigation with `ERR_BLOCKED_BY_ADMINISTRATOR`. Therefore the report does not claim a literal browser-click test was completed. The programme button handlers were executed through their actual HTTP/API routes, and the rendered JavaScript button contract was checked separately.
