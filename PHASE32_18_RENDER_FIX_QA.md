# Phase 32.18 Render No-Disk Fix QA

## Issue found
The blank Render page was caused by a JavaScript runtime exception during script evaluation. The `modal()` function was followed by `enhanceButtonHints(m)` outside the function, where `m` did not exist. That stopped `app.js` before `start()` could render the login screen.

## Fixes
- Moved `enhanceButtonHints(m)` inside `modal()` after the modal is appended.
- Applied the fix to both `app.js` and `static/app.js`.
- Removed the persistent `disk:` block from `render.yaml` for the no-disk Render package.
- Kept `/var/data/construction_control.db` as the runtime DB path.
- Kept the 565,248-byte bundled baseline DB and non-overwrite bootstrap.
- `/healthz` remains HTTP 200 with an ephemeral-storage warning when no disk is mounted.

## Validation
- `node --check app.js` — PASS
- `node --check static/app.js` — PASS
- `python -m py_compile app.py` — PASS
- Phase 32.18 staff/training tests — PASS
- Phase 32.17 programme editing tests — PASS
- Phase 32.15 backup/restore tests — PASS
- Phase 32.9 persistence tests — PASS
- Selected pytest result: **6 passed**
- Baseline database size: **565,248 bytes**
- Baseline contains 5 projects including DUB10, DUB50 and DUB84.
