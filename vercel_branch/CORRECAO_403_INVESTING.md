# Proteção contra HTTP 403 da Investing

## Diagnóstico do projeto original

A coleta executava 15 páginas da Investing em sequência, com apenas 0,15 segundo entre elas. O `curl_cffi` usava `impersonate="chrome"`, mas os headers sobrescreviam o `User-Agent` com Chrome 124. Assim, o fingerprint TLS/HTTP do navegador emulado podia ficar incoerente.

Quando surgia um HTTP 403, o código ainda repetia a mesma URL com `requests` e continuava acessando todas as páginas restantes. Isso aumentava a rajada justamente durante o bloqueio.

## Alterações aplicadas

- Novo cliente em `dashboard/services/investing_http.py`.
- O `curl_cffi` mantém os headers próprios do navegador emulado; não há `User-Agent` manual.
- Intervalo aleatório entre requisições, configurável por ambiente.
- Duas tentativas controladas, com backoff e renovação da sessão.
- Warm-up da sessão apenas após bloqueio, para recuperar cookies.
- Circuit breaker compartilhado no Redis: após 403/429 persistente, o lote para por cinco minutos.
- O fallback `requests` não é usado após 403/429 ou challenge; ele fica restrito a falhas de transporte.
- Cache de 10 minutos para a página de ADRs e 30 minutos para títulos.
- Diagnóstico HTTP incluído em `source_status.investing.metadata.http_diagnostics`.
- Testes automatizados para fingerprint, cache e circuit breaker.

## Configurações

```env
INVESTING_HTTP_ATTEMPTS=2
INVESTING_REQUEST_MIN_DELAY_SECONDS=1.2
INVESTING_REQUEST_MAX_DELAY_SECONDS=2.4
INVESTING_RETRY_BACKOFF_SECONDS=2.0
INVESTING_CIRCUIT_COOLDOWN_SECONDS=300
INVESTING_ADR_CACHE_SECONDS=600
INVESTING_BONDS_CACHE_SECONDS=1800
INVESTING_MIN_HTML_BYTES=1000
```

Se ainda ocorrer bloqueio frequente, altere gradualmente:

```env
MARKET_REFRESH_SECONDS=180
INVESTING_REQUEST_MIN_DELAY_SECONDS=2.0
INVESTING_REQUEST_MAX_DELAY_SECONDS=4.0
INVESTING_CIRCUIT_COOLDOWN_SECONDS=600
```

## Aplicação

```bash
docker compose down
docker compose build --no-cache web celery-worker celery-beat
docker compose up -d
docker compose logs -f celery-worker
```

Para forçar o encerramento de um circuit breaker antigo sem reiniciar o Redis:

```bash
docker compose exec redis redis-cli DEL market-dashboard:investing-http-circuit
```

Teste manual da coleta:

```bash
docker compose exec web python manage.py collect_market_data
```

No JSON bruto, confira:

```text
source_status -> investing -> metadata -> http_diagnostics
```

Exemplo saudável:

```json
{
  "network_requests": 12,
  "retries": 0,
  "cache_hits": 3,
  "blocked_responses": 0,
  "session_resets": 0,
  "fallback_requests": 0,
  "circuit_opened": false
}
```

## Limite da solução

Scraping nunca oferece a mesma estabilidade de uma API contratada. A proteção reduz bastante a probabilidade de bloqueio e impede que uma falha temporária vire uma rajada, mas não garante disponibilidade permanente da Investing. Para produção crítica, os ativos principais devem migrar gradualmente para fontes estruturadas, deixando a Investing apenas como contingência.
