# Phase 32.7 QA — Professional Company Colour Scheme

## Purpose
Correct the Phase 32.5/32.6 theming behaviour so company customisation affects only the application shell, not operational/status colours or every button.

## Implemented
- Settings exposes only Header colour and Sidebar colour.
- Header colour is applied to the page-header accent and active-navigation indicator.
- Sidebar colour is applied to the navigation shell.
- Ordinary buttons retain the professional navy control colour.
- Dashboard/project semantic colours remain fixed: blue, green, amber, red, purple and teal.
- Page background, card colour, text colour and display density are no longer user-customisable.
- Root/static JS, CSS and HTML are synchronised.

## Validation
- Theme contract tests: 3/3 PASS.
- Staff/settings integration regression: 9/9 PASS.
- Python compile: PASS.
- JavaScript syntax: PASS.
- Root/static asset synchronisation: PASS.
- Render Docker build-context inspection: PASS; Docker itself was not installed in this environment, so no local Docker image build is claimed.

## Full-suite note
A full historical pytest run was started. It is not reported as a full pass because an existing Phase 10 workflow test failed with HTTP 403 during its approval assertion, unrelated to this visual theming change, and the complete run was not allowed to finish within the execution limit.
