# Deployment Guide

## Server Prerequisites

### Python (existing)
- Python 3.11+ with virtualenv
- Gunicorn via systemd (`summit-web.service`)
- Nginx reverse proxy with Cloudflare

### Node.js (new — required for React frontend build)

Install Node.js 20 LTS on the production server (one-time setup):

```bash
# Install Node.js 20 LTS via NodeSource
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Verify installation
node --version   # v20.x.x
npm --version    # 10.x.x
```

Node.js is only needed at build time — the frontend compiles to static files served by Nginx.

## Deployment Flow

1. GitHub Actions SSH into the Linode server
2. `git pull origin main`
3. Python: `pip install -r requirements.txt` (in venv)
4. Frontend: `cd frontend && npm ci && npm run build` → produces `dist/`
5. `systemctl restart summit-web`

## Nginx Configuration

Use `nginx/summit-web-react.conf` for the React SPA setup:
- `/assets/` → serves `frontend/dist/assets/` (immutable cache)
- `/api/`, `/discord`, `/google`, `/logout`, `/auth` → proxy to Gunicorn
- `/static/`, `/avatar-images/` → served directly by Nginx
- `/` catch-all → `frontend/dist/index.html` (React Router)

```bash
sudo cp web-app/nginx/summit-web-react.conf /etc/nginx/sites-available/summit-web.conf
sudo nginx -t && sudo systemctl reload nginx
```

## Environment Variables

Set `FRONTEND_URL` for OAuth callback redirects. Add to the systemd service or `.env` file:

```bash
FRONTEND_URL=https://sorcererssummit.com
```

## systemd Service

The existing `summit-web.service` file works unchanged — it runs Gunicorn which serves the Flask API. Nginx handles serving the React static files directly.
