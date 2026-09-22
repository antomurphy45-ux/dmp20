# Phase 32.13 QA — DUB84 Render seed fix

Date: 21 September 2026

## Root cause found
The Render Dockerfile copied the application files but did **not** copy `data/dub84_programme.json` into the Docker image. The DUB84 seeding routine intentionally exits when that source file is absent. Therefore DUB84 could be present in the ZIP/repository but never created in the Render database.

## Fix
The Dockerfile now explicitly copies:
`data/dub84_programme.json` -> `/app/data/dub84_programme.json`.

No existing project data is deleted or replaced. DUB84 seeding remains idempotent and only creates the project/programme when missing; existing DUB84 tasks are not overwritten when activities already exist.

## Validation
- Fresh SQLite init with the packaged DUB84 JSON: PASS
- Projects created: DUB10, DUB50, DUB84, P1: PASS
- DUB84 programme tasks: 264: PASS
- DUB84 plan: 1: PASS
- `pytest -q tests/test_phase32_10_dub84.py tests/test_phase32_2_dub_projects.py tests/test_phase32_8_assignment_to_daily_control.py`: 6 passed
- `python -m py_compile app.py`: PASS
- Render Dockerfile contains DUB84 JSON COPY instruction: PASS
- ZIP integrity: verified after packaging

A full historical pytest suite is not claimed as passing.
A real Docker image build was not run because Docker is not available in the validation environment.
