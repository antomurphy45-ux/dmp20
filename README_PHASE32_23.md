# Phase 32.23 — Roles, Permissions & UI Cleanup

Implemented requested changes:

- Removed the generic **“Open or run this action.”** hover-tooltip generator from the frontend.
- Users and Staff have **Add/Edit only**; there is no delete control for users or master staff.
- Access ladder is now:
  1. Viewer
  2. Site User
  3. Foreman
  4. Charge Hand
  5. Construction Manager
  6. Business Unit Lead
  7. Company Director
  8. Company Administrator
- Retired Project Manager, Site Manager and combined Foreman / Charge Hand access roles are hidden from the Access Ladder and new-user role picker. Existing login users on retired roles are migrated to Construction Manager.
- Foreman, Charge Hand and Construction Manager receive the site-control/create/edit/export permissions required for programme/site control; Construction Manager also receives approval permissions.
- Business Unit Lead and Company Director receive management/approval permissions.
- Construction Manager can manage project access for Foreman, Charge Hand, Site User and Viewer users, limited to projects the Construction Manager controls.
- Business Unit Lead can manage Construction Manager and lower roles; Company Director can manage roles below Director; Company Administrator retains full administration.
- No user/staff deletion function was added.
