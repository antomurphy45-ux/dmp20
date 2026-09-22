# Phase 32.18 — Staff Training Register

Adds a persistent training and competency register to the Staff tab.

## Training records
Each staff member can have multiple records containing:
- Training / course name
- Provider
- Completed date
- Expiry date (optional)
- Certificate / reference
- Status: Completed, Current, Expired or Pending
- Notes

Records can be added, edited and deleted from the **Training** button beside each staff member. The Staff tab also shows the number of training records held for each person.

The database table is created automatically on startup, including when an existing local or Render database is upgraded. Existing staff, projects, assignments, programme data and backup/restore functionality are preserved.

## Validation
- `tests/test_phase32_18_staff_training.py` — CRUD API test: PASS
- Staff board regression: PASS
- Programme editing regression: PASS
- Backup/restore regression: PASS
- Persistence regression: PASS
- Security serialization regression: PASS
- Production readiness regression: PASS

Selected suite: **16 passed**.


## Render no-disk compatibility update

This package is configured to run with the existing SQLite database without requiring a Render persistent disk. The approximately 565 KB database can be used at `/var/data/construction_control.db`. `/healthz` remains healthy on an ephemeral filesystem and reports a backup warning instead of returning `storage_not_persistent`.

**Operational requirement:** download a Full Backup before redeploying or restarting Render because the filesystem is ephemeral without a persistent disk.
