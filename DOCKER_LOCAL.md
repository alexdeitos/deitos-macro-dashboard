# Macro Dashboard local — Docker, PostgreSQL, Redis, Celery e Cloudflare

## Subir tudo

```bash
chmod +x docker-up.sh show-tunnel-url.sh
```

Use, na verdade:

```bash
./docker-up.sh
```

O script constrói e inicia:

- PostgreSQL 17 com volume persistente;
- Redis com AOF e volume persistente;
- Django/Gunicorn;
- Celery Worker;
- Celery Beat;
- Cloudflare Quick Tunnel.

A URL `trycloudflare.com` será impressa no terminal. Ela muda quando o container do túnel é recriado.

## Coleta automática

O mercado, notícias e calendário são atualizados a cada 300 segundos, conforme o `.env`:

```env
MARKET_REFRESH_SECONDS=300
NEWS_REFRESH_SECONDS=300
ECONOMIC_CALENDAR_REFRESH_SECONDS=300
```

Logs:

```bash
docker compose logs -f celery-beat celery-worker
```

## Mostrar novamente a URL

```bash
./show-tunnel-url.sh
```

## Comandos úteis

```bash
docker compose ps
docker compose logs -f web
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py collect_market_data
docker compose down
```

`docker compose down` mantém os dados. Não use `docker compose down -v` a menos que queira apagar PostgreSQL, Redis e mídia.

## Vercel

Na branch Vercel, mantenha o projeto atual. Atualize somente:

```env
USE_REMOTE_MARKET_JSON=True
REMOTE_MARKET_JSON_URL=https://URL-IMPRESSA.trycloudflare.com/api/public-market-snapshot/
REMOTE_MARKET_JSON_TOKEN=mesmo valor de PUBLIC_MARKET_API_TOKEN do local
INVESTING_ENABLED=False
```
