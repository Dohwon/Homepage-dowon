# Portfolio Homepage Deployment

## 1. Environment

Create `.env` from `.env.example` and set:

- `SESSION_SECRET`
- `GOOGLE_CLIENT_ID`
- `ADMIN_EMAILS`
- `PORT` / `HOST`

Google OAuth configuration must allow:

- JavaScript origin: `https://your-domain`
- Redirect-less Google Identity popup usage on the same origin

## 2. Local Run

```bash
cd /home/dowon/securedir/git/codex/portfolio-homepage
node server.js
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

This app is single-process and file-backed, so it is suitable for a personal site or low-traffic portfolio.
