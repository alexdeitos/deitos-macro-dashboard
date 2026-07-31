# Calendário econômico — Trading Economics

O calendário lateral não usa mais iframe. O backend consulta a página pública:

`https://tradingeconomics.com/calendar`

A coleta é feita por `curl_cffi` com fingerprint de navegador e fallback para `requests` apenas em falhas de transporte. Existe somente uma requisição por ciclo.

## Dados armazenados

- data e hora do evento;
- país e código;
- evento e referência;
- importância de 1 a 3;
- atual;
- anterior e revisado;
- consenso;
- previsão da Trading Economics;
- link do indicador.

O HTML público normalmente apresenta horários em UTC. O coletor converte para `America/Sao_Paulo`. Isso pode ser alterado por `ECONOMIC_CALENDAR_SOURCE_TIMEZONE`.

## Países iniciais

- BR — Brasil;
- US — Estados Unidos;
- CN — China;
- EA — Zona do Euro.

Altere `ECONOMIC_CALENDAR_COUNTRIES` no `.env` para mudar a seleção.

## Atualização

O Celery Beat executa `dashboard.tasks.collect_economic_calendar` a cada 300 segundos. A interface consulta a API local a cada minuto, sem acessar diretamente a Trading Economics.

Comando manual:

```bash
docker compose exec web python manage.py collect_economic_calendar
```

API local:

```text
/api/calendar/?days=7&importance=1
/api/calendar/?days=3&country=US&importance=3
```

## Proteções

- duas tentativas com backoff;
- circuit breaker após 403, 429 ou desafio antibot;
- retenção da última agenda válida quando a nova coleta falha;
- limite de uma chamada à página por ciclo;
- limpeza dos eventos antigos;
- deduplicação por evento.

## Configurações

```env
ECONOMIC_CALENDAR_ENABLED=True
ECONOMIC_CALENDAR_REFRESH_SECONDS=300
ECONOMIC_CALENDAR_RETENTION_DAYS=14
ECONOMIC_CALENDAR_HTTP_TIMEOUT_SECONDS=25
ECONOMIC_CALENDAR_HTTP_ATTEMPTS=2
ECONOMIC_CALENDAR_CIRCUIT_SECONDS=300
ECONOMIC_CALENDAR_MIN_HTML_BYTES=5000
ECONOMIC_CALENDAR_SOURCE_TIMEZONE=UTC
ECONOMIC_CALENDAR_COUNTRIES=BR,US,CN,EA
```

## Observação

A estrutura HTML do site pode mudar. Os testes cobrem os seletores atualmente usados, mas uma alteração de layout da Trading Economics pode exigir ajuste em `dashboard/services/economic_calendar.py`. Para uso comercial crítico, a opção mais estável é contratar a API oficial e configurar uma chave.
