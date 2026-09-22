# Construction Control — Phase 32.18 — Clean Render Repository

## Deploy

1. Create a new empty GitHub repository.
2. Upload **everything in this folder to the repository root**.
3. In Render create a new Web Service from that repository.
4. Runtime: Docker.
5. No persistent disk is required for this build.
6. Deploy.

## Important database fix

The Render seed database is deliberately stored at the repository root as:

`render_seed.db`

The Dockerfile explicitly copies it into the image. This avoids the previous failure where Render could not find `data/construction_control.db` in the GitHub build context.

At startup, if `/var/data/construction_control.db` does not exist, `app.py` copies `render_seed.db` there. An existing runtime database is never overwritten.

## First checks

Open `/healthz` after deployment. Expected:

`{"status":"ok"}`

Then open the main service URL. The Construction Control login page should appear.

Demo login:

- Email: `owner@demo.local`
- Password: `DemoPass!123`

## No-disk warning

This version intentionally does not require a Render persistent disk. Render filesystem data can be lost after a service replacement/redeploy. Use Settings → Backup & Restore → Download Full Backup before important changes or redeployments.
