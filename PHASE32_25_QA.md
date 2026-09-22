# Construction Control — Phase 32.25 QA

## Fix
Resolved the next Render dashboard boot error:
`dashboardProjectCards is not defined`

The dashboard renderer calls `dashboardProjectCards(projects)`, but the function was missing from the Phase 32.24 frontend. The function has been restored before dashboard rendering in both:
- `app.js`
- `static/app.js`

## Validation
- Python syntax: PASS
- JavaScript syntax (`app.js`): PASS
- JavaScript syntax (`static/app.js`): PASS
- Root/static JS synchronisation: PASS
- Root/static CSS synchronisation: PASS
- Phase 32.24 dashboard boot regression test: PASS
- Phase 32.25 dashboard card regression test: PASS
- Phase 32.23 roles/UI regression tests: PASS
- Phase 32.22 calendar regression tests: PASS
- Phase 32.21 programme tab regression tests: PASS
- Phase 32.20 PM cockpit regression tests: PASS
- Phase 32.19 UI contract regression tests: PASS
- Targeted tests: **12 passed**
- Local runtime `/healthz`: PASS
- Local runtime `/`: PASS

A full historical pytest run is not claimed.

## Packaging
LOCAL and RENDER packages are built from the same tested source tree.
