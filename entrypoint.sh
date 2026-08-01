#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
import os
import time
import psycopg

host = os.getenv("DB_HOST", "db")
port = int(os.getenv("DB_PORT", "5432"))
dbname = os.getenv("DB_NAME", "macro_db")
user = os.getenv("DB_USER", "macro_user")
password = os.getenv("DB_PASSWORD", "")

for attempt in range(1, 61):
    try:
        with psycopg.connect(host=host, port=port, dbname=dbname, user=user, password=password, connect_timeout=3):
            print("PostgreSQL disponível.")
            break
    except Exception as exc:
        if attempt == 60:
            raise SystemExit(f"PostgreSQL indisponível após 60 tentativas: {exc}")
        print(f"Aguardando PostgreSQL ({attempt}/60)...")
        time.sleep(2)
PY

exec "$@"
