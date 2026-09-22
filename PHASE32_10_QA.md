# Phase 32.10 QA — DUB84

## Passed
- Python compile: PASS
- DUB84 seed/project creation: PASS
- DUB84 plan creation: PASS
- 264 DUB84 programme activities present: PASS
- No DUB84 task has finish date before start date: PASS
- 60 Manloader source days extracted: PASS
- Workbook Manloader matches app planned-men schedule for all 60 source dates: PASS
- DUB84 seed is idempotent: PASS
- DUB10/DUB50 preserved: PASS
- API project listing exposes DUB84: PASS
- API programme listing exposes `PLAN-DUB84`: PASS
- API task endpoint returns 264 DUB84 activities: PASS
- Phase 32.9 selected regression suite plus DUB84 tests: **22 passed**
- ZIP integrity checks: PASS

## Full historical suite
A full `pytest -q` run did not complete within the 180-second validation window. An early existing failure was observed in `tests/test_phase10.py` where the manager approval workflow returned HTTP 403 instead of the test's expected 200. This was not caused by the DUB84 import and is not claimed as fixed in this phase.

## Docker
No Docker image build is claimed unless Docker is available in the validation environment. The Render package retains the Phase 32.9 Dockerfile/render configuration and DUB84 seed source.
