# Phase 32.10 — DUB84 Infil Programme

This phase adds the supplied `DUB 84 Infil Programme draft.xlsx` as a third live project while preserving DUB10 and DUB50.

## Project added
- Project ID: `DUB84`
- Name: `DUB84 — Infil Programme`
- Programme: `DUB84 — Infil Programme Master Programme`
- Programme status: Live / baseline set
- Planned project window: 01 Sep 2026 to 25 Nov 2026
- Peak planned manpower from the workbook Manloader: 34
- Programme activities imported: 264
- Source workbook retained under `source/`

## Workbook mapping
The supplied workbook has two sheets:
- `Sheet1`: programme, phases, DH/panel structure, activities, dates, planned manpower and panel markers.
- `Manloader`: daily planned manpower from 01 Sep 2026 through 23 Nov 2026.

The app stores the programme in the existing `projects`, `plans` and `plan_tasks` model. Parent/child relationships were created for DH, phases, panels and their detailed activities. The phase/initial-works planned-men values reproduce the workbook's daily Manloader values exactly across all 60 source days.

## Source handling
The workbook contains several cached parent dates that are invalid (finish before start) and broken `#REF!` formulas in the panel overview columns. The invalid panel parent finishes are represented using the latest child activity finish so the web programme remains valid; the original cached values are preserved in task notes. Panel overview rows are not duplicated as separate activities; their target dates/notes/resource markers are attached to the matching detailed panel activity.

No actual progress has been fabricated. Imported activities start at 0% / Starting so live site updates can be entered through the existing workflow.

## Persistence
The Phase 32.9 persistent-storage fix remains in place. Render deployment must use the configured persistent disk at `/var/data`; the Render blueprint is aligned to the live service name `daily-program-management`.
