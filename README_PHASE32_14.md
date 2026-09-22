# Construction Control — Phase 32.14

DUB84 Render build-context fix.

The DUB84 programme JSON is stored at the repository root so a normal GitHub -> Render Docker build cannot lose it because the `data/` directory is absent or ignored.

- `dub84_programme.json` is root-level.
- `app.py` reads the root-level JSON.
- `Dockerfile` copies the root-level JSON.
- DUB84 seeding is idempotent and preserves live progress.
- DUB10/DUB50 and existing database data are preserved.
