# Cálculo macro adicional de abertura

O dashboard mantém integralmente a análise ponderada existente de WIN e WDO e adiciona, acima dela, um segundo card independente.

## Fórmula

```text
resultado = (- variação do VIX) + variação do minério de ferro + variação do petróleo WTI
```

Mapeamento dos símbolos coletados:

- `VIX`: invertido, pois alta da volatilidade contribui negativamente.
- `IRON_ORE`: representa o minério de ferro usado como FEF no card de referência.
- `WTI`: representa o petróleo WTI usado como CL1 no card de referência.

O cálculo somente é mostrado quando os três percentuais reais estão disponíveis. Não existe fallback por valor fixo e o Brent não substitui silenciosamente o WTI.

## Faixas

- `abs(resultado) < 1,5`: lateral.
- `1,5 <= abs(resultado) <= 2,5`: abertura fraca.
- `2,5 < abs(resultado) <= 4,5`: abertura moderada.
- `abs(resultado) > 4,5`: abertura forte.

Resultado positivo indica viés comprador; resultado negativo indica viés vendedor. A classificação é direcional e não representa probabilidade estatística de acerto.

## Contexto overnight

O card exibe separadamente S&P 500, Dow Jones, Nasdaq, DXY e EWZ. Esses itens ajudam a validar divergências, mas não entram na soma de três componentes.

## Agenda econômica

Notícias de impacto 3 estrelas não são presumidas. A agenda aparece como não configurada até que uma fonte específica seja integrada e validada.

## Ponderação das bolsas americanas na abertura do WIN

Para a estimativa da abertura do mini índice, o **Dow Jones (DJI) passou a ser o principal driver entre os índices americanos**. A composição usada no ajuste da abertura é 70% Dow Jones, 20% S&P 500 e 10% Nasdaq; quando um componente não está disponível, os pesos disponíveis são renormalizados.

No score direcional do WIN/WDO, o Dow Jones também recebe peso maior que o S&P 500. O S&P 500 não foi eliminado: permanece como confirmação secundária.
