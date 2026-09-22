# Phase 32.24 QA — Render Dashboard Boot Fix

## Issue
Render login was displaying `DASH_MODULES is not defined` immediately after sign-in. The dashboard render function referenced `DASH_MODULES` without a declaration in the Phase 32.23 frontend.

## Fix
- Restored the shared `DASH_MODULES` declaration in `app.js`.
- Kept `static/app.js` byte-for-byte synchronised with the root frontend.
- Added a regression test confirming the declaration exists before the dashboard issue-card render and that the two frontend copies match.

## Validation
- `node --check app.js` — PASS
- `node --check static/app.js` — PASS
- Targeted Phase 32.20–32.24 UI/PM/programme/role tests — **9 passed**
- `/healthz` local runtime smoke test — PASS
- `/api/login` local runtime smoke test — PASS
- `/api/dashboard` local runtime smoke test — PASS

## Limitation
No physical Chromium click-through was claimed because the execution environment does not permit local browser navigation.
