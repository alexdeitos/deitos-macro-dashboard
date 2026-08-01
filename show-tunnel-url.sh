#!/usr/bin/env bash
set -euo pipefail
url="$(docker compose logs --no-color cloudflared 2>/dev/null | grep -Eo 'https://[A-Za-z0-9-]+\.trycloudflare\.com' | tail -n 1 || true)"
if [[ -z "$url" ]]; then
  echo "URL ainda não encontrada. Execute: docker compose logs -f cloudflared" >&2
  exit 1
fi
printf '%s\n%s\n%s\n' "$url" "${url}/api/raw/" "${url}/api/public-market-snapshot/"
