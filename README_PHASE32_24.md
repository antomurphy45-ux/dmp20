# Phase 32.24 — Dashboard Boot Fix

Fixes the Render startup error shown after login: `DASH_MODULES is not defined`.

The dashboard module list is restored in the shared frontend and the root/static JavaScript copies are kept synchronised.
