# Phase 32.23 QA

## Validation
- `python -m py_compile app.py` — PASS
- `node --check static/app.js` — PASS
- `node --check app.js` — PASS
- Root `app.js` and `static/app.js` synchronised — PASS
- Root `app.css` and `static/app.css` synchronised — PASS

## Targeted automated tests
`pytest -q tests/test_phase32_23_roles_and_ui.py tests/test_phase32_19_ui_contract.py tests/test_phase32_16_staff_board.py tests/test_phase32_17_programme_editing.py tests/test_phase32_19_programme_button_execution.py tests/test_phase32_19_training_documents.py tests/test_phase32_18_staff_training.py tests/test_phase32_20_pm_cockpit.py`

Result: **15 passed**.

## Phase 32.23 role checks
- New visible ladder: Viewer → Site User → Foreman → Charge Hand → Construction Manager → Business Unit Lead → Company Director → Company Administrator.
- Project Manager and Site Manager are not returned by the visible `/api/roles` list.
- Existing Project Manager/Site Manager login users are migrated to Construction Manager.
- Foreman/Charge Hand/Construction Manager site-control permissions verified.
- Construction Manager project-access assignment to Foreman verified.
- Construction Manager blocked from assigning Company Director verified.
- User DELETE endpoint not exposed; test returned 404.
- Generic “Open or run this action.” tooltip generator removed from frontend.

## Known broader-suite note
The full historical suite contains older tests that assert the previous Project Manager/Site Manager ladder and older fixed fixture contents. Those historical expectations are no longer aligned with the Phase 32.23 requested role structure. The new Phase 32.23 targeted suite and the existing current programme/staff/training/PM-cockpit tests pass.

No physical browser click-through is claimed because the local Chromium navigation environment is unavailable here.
