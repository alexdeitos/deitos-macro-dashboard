# Análise EUA / FED integrada

O módulo **Análise EUA** transforma o `grafico.py` enviado em dados dinâmicos do Django.

## Séries

Base do script original:
- DGS10 — Treasury 10Y
- DGS2 — Treasury 2Y
- DFF — Fed Funds
- T10YIE — Breakeven 10Y
- UNRATE — desemprego
- PAYEMS — payrolls
- CPIAUCSL — CPI
- DEXUSEU — EUR/USD
- WTISPLC — WTI
- GFDEBTN — dívida federal

Extensões:
- PCEPI — PCE
- WALCL — ativos totais do Federal Reserve
- RRPONTSYD — ON RRP

## Gráficos

A página `/eua/` usa Plotly com zoom, hover e interação. São apresentados:

1. 2Y / 10Y / Fed Funds.
2. Spread 10Y−2Y.
3. CPI YoY / PCE YoY / Breakeven.
4. Desemprego / Payrolls.
5. Ativos totais do Fed.
6. ON RRP.

## Leitura operacional

O módulo calcula uma pontuação macro explicável a partir de:
- sinal da curva 10Y−2Y;
- diferença 2Y vs Fed Funds;
- CPI YoY;
- PCE YoY;
- desemprego;
- Breakeven 10Y como alerta.

O resultado é apresentado como contexto para o WDO. Não é uma recomendação automática nem uma probabilidade de preço.

## FRED

Configure no `.env`:

```env
FRED_API_KEY=SEU_TOKEN
FRED_CACHE_TTL=900
FRED_HISTORY_YEARS=3
```

A API do FRED exige uma chave por aplicação. O projeto não grava a chave no código-fonte.
