# Phase 32.22 QA

## Change
Reworked the Programme > Calendar view into a monthly calendar board based on the supplied reference image.

## UI
- Sunday-to-Saturday month grid.
- ISO week-number column on the left.
- Month/year header with previous/next navigation.
- Programme activities appear as compact clickable tabs inside each date.
- Activity tabs show activity name and percentage complete.
- Critical, starting, ongoing, held-up and finished activities have distinct visual treatment.
- Calendar exceptions remain visible inside the relevant date.
- Clicking a date opens its activities and calendar exceptions and allows a new calendar exception to be saved.
- Clicking an activity tab opens the existing Edit Activity screen.
- Month view is responsive with horizontal scrolling on narrow screens.
- No visible circled-i icons have been reintroduced.

## Validation
- `node --check app.js` — PASS
- `python -m py_compile app.py` — PASS
- `pytest -q tests/test_phase32_22_calendar_display.py tests/test_phase32_21_programme_tabs.py tests/test_phase32_19_programme_button_execution.py tests/test_phase32_20_pm_cockpit.py` — PASS (6 tests)
- Root and `static/` JavaScript/CSS copies verified identical.

## Browser limitation
A physical Chromium UI smoke test was not claimed because this execution environment does not permit local browser navigation. The calendar rendering logic and UI contract were validated statically and through the existing targeted test suite.
