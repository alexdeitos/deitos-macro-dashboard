#!/usr/bin/env bash
set -euo pipefail

MAX_WAIT_SECONDS="${MAX_WAIT_SECONDS:-120}"

echo "Subindo PostgreSQL, Redis, Django, Celery e Cloudflare Tunnel..."
docker compose up -d --build

echo
docker compose ps

echo
echo "Aguardando a URL pública do Quick Tunnel..."
start=$(date +%s)
url=""
while [[ -z "$url" ]]; do
  url="$(docker compose logs --no-color cloudflared 2>/dev/null | grep -Eo 'https://[A-Za-z0-9-]+\.trycloudflare\.com' | tail -n 1 || true)"
  if (( $(date +%s) - start >= MAX_WAIT_SECONDS )); then
    echo "A URL não apareceu em ${MAX_WAIT_SECONDS}s. Veja: docker compose logs -f cloudflared" >&2
    exit 1
  fi
  sleep 2
done

cat <<MSG

============================================================
Dashboard local:  http://127.0.0.1:8000
Quick Tunnel:     ${url}
JSON público:     ${url}/api/raw/
JSON protegido:   ${url}/api/public-market-snapshot/

Na Vercel, configure:
REMOTE_MARKET_JSON_URL=${url}/api/public-market-snapshot/
============================================================

Acompanhar coleta automática:
  docker compose logs -f celery-beat celery-worker
MSG
