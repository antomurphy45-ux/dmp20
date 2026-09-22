# Phase 32.6 QA — Professional Theme Rollback

Date: 20 September 2026

## Purpose
Rollback the Phase 32.5 behaviour that caused dashboard/status cards and other semantic UI elements to inherit the single user-selected accent colour.

## Changes verified
- Settings accent no longer aliases `--cc-blue`.
- Settings accent no longer aliases the semantic `--blue` variable.
- Dashboard semantic colours remain independent.
- RFI/risk/action/snag/approval colours remain distinct.
- Project KPI colours remain distinct.
- DUB10/DUB50 data and staff/assignment/settings functionality retained.
- Root/static CSS synchronised.
- Root/static JS synchronised.

## Tests
- Python compile: PASS
- Node JavaScript syntax: PASS
- Phase 32.5 theme contract: PASS
- Semantic palette contract: PASS
- Staff/settings API workflow with live local server: PASS
- ZIP integrity: PASS

A physical authenticated Chromium click-through is not claimed for the full application. The local browser environment can run Chromium, but the authenticated workflow is validated through the live HTTP/API tests and static UI contracts.

Docker image build was not executed because Docker is not installed in this environment. Render build-context requirements were retained from Phase 32.5.
