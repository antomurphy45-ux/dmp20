# Phase 32.8 QA — Staff Assignment → Daily Site Control

## Fix
Project staff assignments are now the source of truth for the Daily Site Control attendance list. The daily endpoint no longer hides an actively assigned person because the master staff record has `active=0`, and the frontend now filters on the explicit `staff_active` field instead of the non-existent assignment `active` field. Assignment role is displayed in Daily Site Control.

## Verification
- Python compile: PASS
- JavaScript syntax: PASS
- Assignment appears in Daily Site Control when active for selected date: PASS
- Future assignment excluded before start date: PASS
- Existing Morning/Daily Site Control workflow tests: PASS
- 12 selected tests: PASS
- Root/static JS synchronisation: PASS
- Root/static CSS synchronisation: PASS
- Root/static HTML synchronisation: PASS
- Render Docker build-context source dependency remains unchanged from Phase 32.7: `static/` is created by the Dockerfile rather than required in Git build context.

## Browser limitation
A full authenticated Chromium click-through could not be executed in this environment, so no physical browser click-through is claimed.
