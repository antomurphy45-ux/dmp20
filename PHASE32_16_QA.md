# Phase 32.16 QA

## Completed
- Extracted staff names, labour levels, source groups, badge markers and colour mapping from the supplied screenshots.
- Added 30 active C1 staff records.
- Existing generic/demo staff were deactivated rather than deleted, preserving historical references.
- Added staff metadata fields: labour_level, badge_type, source_group, display_color.
- Staff & Assignments now displays the labour-level colour marker, level, badge and source group.
- Add/Edit Staff supports labour level, badge and source group.
- Project assignment roles remain the established vocabulary.
- DUB10/DUB50 retained.
- DUB84 retained with 264 activities.

## Validation
- Python compile: PASS
- JavaScript syntax check: PASS
- Fresh database seed: 30 active image staff, DUB84 present, 264 DUB84 activities: PASS
- Phase 32.16 staff-board test: PASS
- Selected regression tests: 9 passed
- Root/static app assets synchronised: PASS

## Source limitation
The supplied screenshots do not state a labour level for Colm Keighery, so the app stores `Unspecified` rather than guessing.

No project dates or assignments were inferred from the screenshots.
