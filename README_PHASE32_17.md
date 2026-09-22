# Phase 32.17 — Easier Programme Editing

This phase improves programme usability without changing the existing DUB10, DUB50 or DUB84 programme data.

## Programme editing
- Each activity now has clear **Edit**, **Move** and **Delete** actions.
- Edit supports name, dates, parent/section, status, progress, planned manpower, predecessor/dependency, lag, actual dates, notes and milestone.
- Move is a focused edit for relocating an activity by dates and/or programme links.
- Delete asks for confirmation before permanently removing an activity.
- Existing API delete support is retained and audited.
- Parent activity references are validated; an activity cannot be its own parent.

## Button explanations
- Buttons receive a small information marker and a contextual explanation on hover/focus.
- Native `title` text is also supplied as a fallback.
- Programme screens include a short editing guide explaining Edit / Move / Delete.

## Compatibility
- DUB10, DUB50 and DUB84 remain intact.
- DUB84 remains at 264 programme activities.
- Existing backup/restore functionality remains included.
- Staff-board changes from Phase 32.16 remain included.

## Validation
- Phase 32.17 UI/backend contract tests: PASS
- Programme CRUD/planning regression tests: PASS
- Phase 32.16 staff-board tests: PASS
- Phase 32.15 backup/restore tests: PASS
- DUB84 tests: PASS
- Assignment/daily-control tests: PASS
- Theme tests: PASS
- Combined selected tests: 18 passed
- Python compile: PASS
- JavaScript syntax check: PASS
- root/static asset sync: PASS

The full historical test suite is not claimed as passing.
