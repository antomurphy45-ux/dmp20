# Phase 32.18 QA

## Implemented
- Persistent `staff_training_records` database table.
- GET/POST/PUT/DELETE training APIs scoped to the logged-in company and staff member.
- Date validation and expiry-before-completion protection.
- Staff-tab Training section and per-person Training button.
- Training record count displayed beside each staff member.
- Edit/delete confirmation and button explanations.
- Existing staff/project/programme data preserved.

## Test result
`pytest -q tests/test_phase32_18_staff_training.py tests/test_phase32_16_staff_board.py tests/test_phase32_17_programme_editing.py tests/test_phase32_15_backup_restore.py tests/test_phase32_9_persistence.py tests/test_security_user_serialization.py tests/test_production_readiness.py`

**16 passed in 2.96s**

No full historical suite is claimed here.
