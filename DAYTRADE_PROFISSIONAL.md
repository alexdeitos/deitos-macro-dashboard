# Daytrade profissional

A rota raiz (`/`) abre o painel Daytrade. O dashboard existente continua em `/dashboard/`.

## Camadas

- Pressão ponderada das ações do Ibovespa: 35%
- Ambiente global: 25%, com Dow Jones como principal driver externo
- Juros B3: 20%
- Amplitude/breadth: 10%
- Agenda macro 3 estrelas: 10%

## Gate operacional

- Captura Excel/Profit com mais de 3 minutos: AGUARDAR.
- Divulgação Investing.com 3 estrelas iminente: AGUARDAR.
- Evento 3 estrelas próximo: CAUTELA.
- Sem bloqueio: o score é contexto; a entrada depende de estrutura, VWAP, fluxo e invalidação.

## Investing.com

A coleta do Daytrade filtra apenas Brasil, EUA e China, importância 3 e a data atual. Para eventos divulgados, o painel mostra anterior, consenso/previsão, atual, surpresa e uma leitura contextual por tipo de indicador. Dados ainda não publicados não são tratados como resultado realizado.
