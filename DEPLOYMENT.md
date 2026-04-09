# VPS Deployment Guide

## What was added

- `Dockerfile` for the FastAPI app
- `docker-compose.yml` for container runtime on VPS
- `.dockerignore` for smaller and safer image builds
- `.env.example` template for runtime configuration
- `deploy/vps/deploy.sh` deployment script
- `.github/workflows/deploy-vps.yml` CI/CD workflow

## 1) Prepare your VPS (one-time)

Install Docker and Docker Compose plugin on your VPS, then run:

```bash
sudo mkdir -p /opt/nse-smart-investor-api
sudo chown -R $USER:$USER /opt/nse-smart-investor-api
cd /opt/nse-smart-investor-api
```

Create app environment file:

```bash
cp .env.example .env
```

Edit `.env` and set real values, especially:

- `DATABASE_URL`
- `SECRET_KEY`
- `AT_USERNAME`
- `AT_API_KEY`
- `AT_SENDER_ID`

## 2) Configure GitHub repository secrets

Add these secrets in GitHub repo settings:

- `VPS_HOST` (e.g. `203.0.113.10`) tick
- `VPS_USER` (SSH user) tick
- `VPS_SSH_KEY` (private key content) tick
- `VPS_PORT` (optional, defaults to `22`) tick
- `VPS_APP_DIR` (e.g. `/opt/nse-smart-investor-api`) tick 
- `GHCR_USERNAME` (GitHub username or machine user with package read access) tick
- `GHCR_TOKEN` (classic PAT with at least `read:packages`)

## 3) Push to deploy

Every push to `master` triggers:

1. Build Docker image
2. Push image to GitHub Container Registry (`ghcr.io`)
3. Copy deployment files to VPS
4. Pull latest image and restart via Docker Compose

## 4) Manual verification on VPS

```bash
cd /opt/nse-smart-investor-api
docker compose ps
docker compose logs -f --tail=100
curl http://127.0.0.1:8000/health
```
