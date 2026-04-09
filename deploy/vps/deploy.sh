#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/nse-smart-investor-api}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

echo "[Deploy] Starting deployment in ${APP_DIR}"
mkdir -p "${APP_DIR}"
cd "${APP_DIR}"

if [ ! -f ".env" ]; then
  echo "[Deploy] ERROR: .env not found in ${APP_DIR}"
  echo "[Deploy] Create it first (you can copy from .env.example)."
  exit 1
fi

if [ -z "${APP_IMAGE:-}" ]; then
  echo "[Deploy] ERROR: APP_IMAGE is not set."
  exit 1
fi

if [ ! -f "${COMPOSE_FILE}" ]; then
  echo "[Deploy] ERROR: ${COMPOSE_FILE} not found in ${APP_DIR}"
  exit 1
fi

echo "[Deploy] Pulling latest image: ${APP_IMAGE}"
docker compose -f "${COMPOSE_FILE}" pull

echo "[Deploy] Recreating containers"
docker compose -f "${COMPOSE_FILE}" up -d --remove-orphans

echo "[Deploy] Cleaning dangling images"
docker image prune -f

echo "[Deploy] Done."
