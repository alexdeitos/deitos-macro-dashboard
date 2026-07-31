# Radar de notícias via RSS da Investing

## O que foi incluído

A página principal agora é dividida em duas áreas:

- coluna esquerda: Radar de notícias;
- área direita: dashboard de mercado já existente.

Em telas com menos de 980 px, o radar passa automaticamente para cima do conteúdo.

## Feeds utilizados

- Moedas e câmbio: `news_1.rss`
- Commodities: `news_11.rss`
- Mercado de ações: `news_25.rss`
- Indicadores econômicos: `news_95.rss`
- Economia: `news_14.rss`
- Política: `news_289.rss`

Os feeds são coletados separadamente das páginas HTML de preços. Por isso, um bloqueio ou erro no RSS não invalida o snapshot de mercado.

## Configurações

```env
NEWS_ENABLED=True
NEWS_REFRESH_SECONDS=300
NEWS_RETENTION_DAYS=7
NEWS_DISPLAY_HOURS=72
NEWS_MIN_RELEVANCE=20
NEWS_HTTP_TIMEOUT_SECONDS=15
NEWS_CACHE_METADATA_SECONDS=86400
```

`NEWS_MIN_RELEVANCE` controla o que aparece na lateral. Reduza para 10 para exibir mais manchetes ou aumente para 30 para deixar o radar mais seletivo.

## Primeira coleta manual

```bash
docker compose exec web python manage.py collect_market_news
```

Acompanhe o agendador e o worker:

```bash
docker compose logs -f celery-beat celery-worker
```

## Endpoints

```text
GET  /api/news/?limit=80
POST /api/news/refresh/
```

Filtros opcionais da API:

```text
/api/news/?market=WIN
/api/news/?market=WDO
/api/news/?market=MACRO
/api/news/?category=commodities
```

## Critério de relevância

A classificação é feita localmente por categoria e palavras-chave. Ela identifica relação provável com WIN, WDO e macroeconomia, mas não define direção de compra ou venda. O número exibido ao lado da manchete é relevância contextual, não probabilidade de acerto.
