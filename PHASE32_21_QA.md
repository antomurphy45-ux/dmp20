# Phase 32.21 QA — Programme local tabs + clean buttons

## Changes
- Removed all visible circled-`i` icons from buttons, including the dashboard RAG button and programme action buttons.
- Kept the existing button explanations as normal hover tooltips using `title` / `data-help`; no visible icon is added.
- Programme view actions now open in a tabbed panel directly underneath the programme toolbar.
- Added a **Programme** tab so the user can return directly to the Gantt/programme view.
- Added local tabs for Resources, Look-ahead, Baseline vs Current, Live Progress, Update Programme, Calendar and Control Centre.
- Kept Import Excel and Export Excel as direct actions because they open a validation/download workflow rather than a persistent programme view.
- Root and `static/` JavaScript/CSS copies were synchronised.

## Validation
- `node --check app.js` — PASS
- `node --check static/app.js` — PASS
- `python -m py_compile app.py` — PASS
- `pytest -q tests/test_phase32_21_programme_tabs.py tests/test_phase32_19_ui_contract.py tests/test_phase32_19_programme_button_execution.py tests/test_phase32_20_pm_cockpit.py` — **8 passed**
- Confirmed no `ⓘ` glyph remains in `app.js`, `static/app.js`, `app.css` or `static/app.css`.
- Confirmed root/static JS and CSS copies are identical.
- Local `/healthz` runtime check returned HTTP 200.

## Browser note
A direct Chromium UI smoke test was attempted, but the execution environment blocked local HTTP navigation with `ERR_BLOCKED_BY_ADMINISTRATOR`. The programme tab behaviour was therefore validated through the JavaScript/UI contract tests and the existing programme button execution tests; no claim of physical browser clicking is made from that blocked run.
