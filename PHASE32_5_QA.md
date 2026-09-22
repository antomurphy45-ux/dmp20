# Construction Control — Phase 32.5 QA

## Scope
Fix the reported Settings customisation failure visible in the live/local UI:
- The whole interface remained blue after changing Settings colours.
- Saving Settings did not update the in-memory settings object because the PUT response only returned `ok`.
- Several later CSS rules hard-coded the primary blue/sidebar colours, overriding the Settings CSS variables.

## Fixes
- Settings PUT now returns the saved settings row as `settings`.
- Frontend `saveSettings()` merges the submitted values and returned settings before re-rendering.
- Added immediate Settings preview with `oninput`/`onchange` handlers.
- Added `applyThemeValues()` so Settings updates the primary and legacy theme variables together.
- Primary buttons now follow `--accent`.
- Sidebar follows `--sidebar`.
- Page background follows `--page-bg`.
- Cards follow `--card-bg`.
- Main text follows `--text`.
- Dashboard/access-ladder primary blue aliases follow the selected accent.
- Root and static JS/CSS/HTML remain byte-identical.

## Verification
- Python compile: PASS
- JavaScript syntax: PASS
- Staff/assignment/settings integration test: **1/1 PASS**
- Theme contract/static test: **2/2 PASS**
- Combined affected test run: **3/3 PASS**
- Root/static JS synchronisation: PASS
- Root/static CSS synchronisation: PASS

## Full-suite status
A complete historical pytest run was started against a copy of the database but did not finish within the execution limit. It reached the middle of the suite with two pre-existing failures before timing out. Therefore **no full-suite pass is claimed for this phase**.

## Browser validation
A physical Chromium click-through of the authenticated Settings page is not claimed. The environment can run Chromium, but the authenticated local browser workflow is restricted. The Settings API, frontend theme contract, variable wiring and persistence were tested directly.

## Render
The Render Dockerfile continues to create `static/` from the root assets and does not require `COPY static`. Docker itself is not installed in this environment, so no local Docker image build is claimed.


## Phase 32.7 professional company theming correction
- Settings now expose only Header colour and Sidebar colour.
- Page background, card colour, text colour and density are no longer user-customisable.
- Ordinary buttons no longer inherit the company accent; semantic dashboard colours remain fixed.
- Company colour is applied to the page header accent and active navigation indicator only.
- Root/static JS and CSS remain synchronised.
