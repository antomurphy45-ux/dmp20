# Construction Control — Phase 32.2

## Daily operating sequence

1. Log in and open **Morning Brief**.
2. Confirm the people assigned to the selected project are on site.
3. Update today's active tasks quickly using **Starting**, **Ongoing**, **Held Up**, or **Finished**, plus percentage complete.
4. Held-up work records a reason and notes.
5. Check **Starting tomorrow** before leaving the morning workflow.
6. Use **Close Out** at the end of the day to retain final notes and outstanding actions.

## Staff and resource planning

Staff are entered once and assigned to projects with a role, start/finish date and assignment status. Project manpower and attendance use those assignments; the same information is not manually re-entered in another staff list.

Allowed seeded labour roles:
- Construction Manager
- Foreman
- Charge Hand
- Electrician
- 4th Year
- 3rd Year
- 2nd Year
- 1st Year
- GO

## DUB10 and DUB50

Both projects are included and populated in this package. Each has:
- 36-week demonstration programme
- 15 SOW-based programme activities
- 9 project staff assignments
- task/staff links for representative activities
- project-level manpower baseline
- management dashboard visibility

The programme follows the supplied SOW sequence from mobilisation through enabling works, MV/LV, mechanical systems, fit-out/containment, fire, BMS/security, IT cabling, commissioning, IST, training/handover and practical completion.

## Packages

`START_LOCAL.bat` stores the laptop database and uploads under `data/`.

Render uses `/var/data` for persistent data. The Render Dockerfile creates the runtime `static/` directory from the root assets, so a GitHub checkout does not need to contain a separate `static` folder.

Both packages are generated from the same application source.

## Phase 32.3 Function/CRUD Repair
The Phase 32.2 package was function-tested and compatibility defects were repaired in Phase 32.3. See `PHASE32_3_QA.md`. Full regression is 140/140 passing.
