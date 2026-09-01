# Project Atlas Deployment

Public entry points:

- `/`: Project Atlas explorer
- `/admin.html`: preserved portfolio CMS
- `/api/atlas/bootstrap`: sanitized Atlas bootstrap payload
- `/api/health`: process health

## 1. Environment

Create `.env` from `.env.example` and set:

- `SESSION_SECRET`
- `GOOGLE_CLIENT_ID`
- `ADMIN_EMAILS`
- `PORT` / `HOST`
- `ATLAS_BUNDLE_DIR` (optional absolute path to a validated public bundle)

Google OAuth configuration must allow:

- JavaScript origin: `https://your-domain`
- Redirect-less Google Identity popup usage on the same origin

## 2. Local Run

```bash
cd /home/dowon/securedir/git/codex/portfolio-homepage
npm install
node server.js
```

The default bundle is `public-bundle/` under the service root. Set
`ATLAS_BUNDLE_DIR` only when the worker promotes the bundle elsewhere. Never point
it at the workspace, a project repository, session storage, or project memory.

```bash
ATLAS_BUNDLE_DIR=/absolute/path/to/public-bundle PORT=4173 node server.js
curl -sS http://127.0.0.1:4173/api/health
curl -sS http://127.0.0.1:4173/api/atlas/bootstrap
```

Before a deploy, validate and test the exact bundle and source state:

```bash
.venv/bin/python scripts/project_atlas.py validate --fixture /absolute/path/to/public-bundle
.venv/bin/python -m pytest tests/worker -q
npm test
npm run test:ui
node --check server.js
node --check admin.js
```

## 3. systemd

```bash
sudo cp deploy/systemd/portfolio-homepage.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now portfolio-homepage
sudo systemctl status portfolio-homepage
```

## 4. External Access

Recommended production shape:

1. Run `server.js` on `127.0.0.1:4173` or `0.0.0.0:4173`
2. Put Nginx or Caddy in front with HTTPS
3. Point your domain DNS to the server

The process remains single-process and file-backed. `public-bundle/` is read-only
at runtime; CMS writes remain in `PORTFOLIO_DATA_DIR` (default `data/`). Keep both
paths on persistent storage when deploying with Railway or another ephemeral
container platform.

## 5. Project Atlas Publisher Timer

The user timer runs the locked daily publisher. It scans both direct children of `projects/` and direct children of `projects/finish/`, hashes each project folder, rebuilds a complete candidate, validates it, promotes it atomically, and stages only `public-bundle/`. A new folder is detected on the next run; it is published only after it has a reviewed public profile and Project Atlas article. Pre-existing staged work defers publication.

Check the repository-owned unit definitions without installing them:

```bash
bash scripts/install_project_atlas_timer.sh --check
```

Install or remove the two user units only after local tests, branch integration, remote push, and Railway parity have been approved:

```bash
bash scripts/install_project_atlas_timer.sh
bash scripts/install_project_atlas_timer.sh --remove
```

The installer manages only `project-atlas.service` and `project-atlas.timer` under the user systemd directory. It does not modify the system-wide service. The Windows fallback installs the same daily shell runner in Task Scheduler.
