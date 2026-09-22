# Construction Control — Phase 32.4 QA

## Scope
Fixes specifically for reported Phase 32.3 issues:
- Staff Add/Edit buttons not working.
- Staff Assignments button not working.
- Assignment editing was not available in the UI.
- Access Ladder showing an incomplete role set.
- Staff register appearing empty/incomplete.
- Missing Settings tab for company customisation.

## Fixes
- Added the established labour-role list to the frontend so Staff Add/Edit/Assignment dialogs no longer fail on an undefined `ROLE_VALUES` reference.
- Added assignment edit UI and connected it to the existing PUT assignment endpoint.
- Assignment PUT now persists role, start date, finish date, status and notes.
- Assignment GET supports lookup by assignment ID.
- Added persistent company Settings storage/API for colours, density and default dashboard.
- Added Settings tab to the administrator navigation.
- Settings are applied through CSS variables on load and after save.
- Access Ladder is enforced/seeded on database startup so all 9 defined levels exist for every company.
- Added a standard staff restoration path which never deletes existing staff.
- Existing DUB10/DUB50 staff and assignments are preserved; seed logic is idempotent.
- Root and static JavaScript/CSS are synchronised.

## Verified tests
- Python compile: PASS
- JavaScript syntax: PASS
- Staff/assignment/settings/access-ladder integration tests: **9/9 PASS**
- DUB project tests included in selected run: PASS
- Daily operating sequence tests included in selected run: PASS
- Function-contract tests included in selected run: PASS
- Root/static app.js SHA-256 match: PASS
- Root/static app.css SHA-256 match: PASS
- Duplicate checks for newProject/saveProject/editProject/saveProjectEdit/modal/newStaff/saveStaff/editStaff/assignStaff/saveAssignment/settings/saveSettings: one definition each

## Browser limitation
A full physical Chromium click-through cannot be claimed in this environment because local browser navigation is blocked. The affected buttons were instead validated through their actual application functions and HTTP persistence workflows.

## Render
The Dockerfile does not require a repository `static/` directory; it creates `static/` from the root assets during image build. Docker itself is not installed in this environment, so an actual image build is not claimed here.
