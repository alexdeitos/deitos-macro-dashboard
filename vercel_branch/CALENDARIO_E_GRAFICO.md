# Calendário econômico e gráfico WINFUT

## Calendário

O calendário lateral é coletado no backend a partir da página pública da Trading Economics. Ele não usa iframe e continua visível mesmo quando a fonte externa fica temporariamente indisponível, pois a última agenda válida permanece no PostgreSQL.

Detalhes completos: `CALENDARIO_TRADING_ECONOMICS.md`.

## TradingView

O gráfico abaixo dos cálculos abre em:

- símbolo: `BMFBOVESPA:WIN1!`;
- período inicial: 5 minutos;
- fuso: `America/Sao_Paulo`;
- tema escuro;
- troca de símbolo liberada;
- lista rápida com WIN, WDO e IBOV.

O widget depende do acesso do navegador ao domínio da TradingView.
