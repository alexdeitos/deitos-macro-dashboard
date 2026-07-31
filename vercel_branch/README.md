# Macro Dashboard — somente dados reais

Projeto Django + Celery + Redis + PostgreSQL gerado para coletar e exibir apenas valores retornados pelas fontes configuradas.

## Fontes

- AwesomeAPI: USD/BRL atual e sequência intradiária. A chave opcional `AWESOME_API_KEY` usa o header oficial `x-api-key`.
- Banco Central do Brasil: Selic anualizada base 252 (SGS 1178) e PTAX.
- Investing.com: dólar futuro B3, DXY, índices, VIX, commodities, ETFs, ADRs e títulos públicos.
- Investing RSS: manchetes de moedas, commodities, ações, indicadores, economia e política.

Uma falha de fonte produz `null`/`N/D` e fica registrada em `source_status`. Não há fallback numérico, séries aleatórias, delta fixo, probabilidade inventada ou PTAX projetada.

## Execução

```bash
cp .env.example .env
# Edite DJANGO_SECRET_KEY e DB_PASSWORD
docker compose up --build
```

Acesse `http://localhost:8000/`.

## Comandos úteis

```bash
docker compose exec web python manage.py collect_market_data
docker compose exec web python manage.py collect_market_news
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py check --deploy
docker compose logs -f web celery-worker celery-beat
```

## Observações

Scraping HTML é inerentemente mais frágil que API documentada. A página de validação mostra cada falha sem substituir o dado. Ajuste `MARKET_REFRESH_SECONDS` de forma responsável para não sobrecarregar os provedores.

## Análise de abertura WIN/WDO

O painel inclui um motor de leitura pré-abertura baseado somente nas cotações reais presentes em cada snapshot. Ele produz um **score direcional de -100 a +100**, separado para mini índice (WIN) e mini dólar (WDO).

O score não é probabilidade de acerto. Ele normaliza cada indicador por uma escala própria e aplica pesos documentados, reduzindo a distorção causada por ativos de volatilidade diferente, como VIX e DXY. A interface mostra cobertura dos sinais, concordância, principais contribuições e um plano condicional que exige confirmação por preço, volume e VWAP.

Faixas:

- `>= +35`: viés comprador forte
- `+15 a +34,9`: viés comprador
- `-14,9 a +14,9`: aguardar confirmação
- `-15 a -34,9`: viés vendedor
- `<= -35`: viés vendedor forte

O histórico dos gráficos é montado a partir dos snapshots efetivamente armazenados no PostgreSQL.

## Validação de sinais e escala do Investing

A coleta do Investing Brasil agora usa um parser específico para locale `pt-BR`:

- `177.866` é armazenado como `177866` pontos do Ibovespa;
- `5.133,33` é armazenado como `5133.33`;
- `(+2,97%)` permanece positivo;
- `(-2,97%)` permanece negativo.

O percentual raspado é comparado ao movimento implícito entre o preço atual e o fechamento anterior. O sistema só corrige automaticamente o sinal quando as magnitudes são equivalentes. Quando os campos de preço não são compatíveis entre si, o percentual da página é preservado e a divergência fica registrada em `raw.validation` e em `source_status.investing.metadata`.

Para reparar snapshots gravados pela versão anterior sem apagar usuários ou o histórico inteiro:

```bash
# Primeiro simule e veja quantos registros seriam alterados
docker compose exec web python manage.py repair_market_history --dry-run

# Depois aplique a correção
docker compose exec web python manage.py repair_market_history
```

Após reparar, faça uma nova coleta e atualize a página:

```bash
docker compose exec web python manage.py collect_market_data
```

## Card adicional de cálculo macro

O dashboard inclui um card independente acima da análise WIN/WDO com a fórmula `(-VIX) + minério (FEF) + WTI (CL1)`. Consulte `CALCULO_MACRO_ABERTURA.md` para metodologia, faixas e limitações.

## Proteção da coleta Investing

Esta versão inclui espaçamento aleatório, renovação de sessão, cache para páginas lentas e circuit breaker para HTTP 403/429. Consulte `CORRECAO_403_INVESTING.md` para configurações e validação.


## Radar de notícias lateral

O dashboard inclui uma coluna lateral esquerda com manchetes recebidas pelos feeds RSS oficiais da Investing. A coleta é independente da coleta de preços e roda, por padrão, a cada 5 minutos.

Recursos:

- remoção de duplicidades por identificador estável;
- filtros visuais para Todas, WIN, WDO e Macro;
- classificação local por relevância, sem usar IA paga;
- armazenamento apenas de título, link, horário, categoria e resumo curto;
- limpeza automática após o período configurado;
- atualização manual pelo botão circular da coluna lateral;
- falhas no RSS não interrompem as cotações nem os cálculos.

Consulte `NOTICIAS_RSS.md` para configuração e diagnóstico.


## Calendário e gráfico

- A lateral possui abas para notícias RSS e calendário econômico nativo coletado da Trading Economics.
- Abaixo da análise de abertura há um gráfico TradingView aberto em `BMFBOVESPA:WIN1!` no período de 5 minutos.
- O calendário fica no banco; o gráfico é um widget visual independente dos cálculos internos.

Detalhes: consulte `CALENDARIO_E_GRAFICO.md`.

## Calendário econômico da Trading Economics

A aba **Calendário** da lateral consulta a página pública da Trading Economics pelo backend, salva os eventos no PostgreSQL e mostra hora de Brasília, país, impacto, atual, consenso, anterior e previsão. Não há iframe.

Coleta manual:

```bash
docker compose exec web python manage.py collect_economic_calendar
```

API local:

```text
http://localhost:8000/api/calendar/?days=7&importance=1
```

Consulte `CALENDARIO_TRADING_ECONOMICS.md` para configurações e diagnóstico.

## Diário Trade

O menu **Diário Trade** permite registrar operações, prints, emoções, setups, notícias e aderência ao cálculo de abertura. A página inclui curva de capital, drawdown, Profit Factor, payoff e rankings por estratégia, horário, ativo, notícia e cenário de abertura. Consulte `DIARIO_TRADE.md` para os campos e cálculos.

## Paridade REAL / EUR-USD

O card superior **Paridade REAL / EUR-USD** usa exclusivamente as cotações reais do Investing:

```text
EUR/BRL ÷ EUR/USD
```

A razão elimina o euro e produz uma cotação cruzada em BRL por USD. O card permanece `N/D` se qualquer uma das duas pernas estiver ausente; não há fallback fixo.
