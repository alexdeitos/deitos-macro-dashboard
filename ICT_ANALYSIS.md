# ICT Analysis — WINFUT 5m

A aba **ICT Analysis** recebe o CSV exportado do Profit e constrói uma leitura objetiva de price action no gráfico de 5 minutos.

## Entrada esperada

CSV com:

- Ativo
- Data
- Hora
- Abertura
- Máximo
- Mínimo
- Fechamento

`Volume` e `Quantidade` podem existir e são preservados pelo arquivo de origem, mas não são necessários para a primeira camada do motor ICT.

## Objetos

### Liquidez
- Máxima e mínima do dia.
- PDH/PDL quando o arquivo contém o pregão anterior.
- Swing Highs / Swing Lows.
- Equal Highs / Equal Lows agrupados por tolerância de 2 ticks.

### FVG
Identificação de desequilíbrio de 3 candles:
- Bullish FVG: Low do terceiro candle acima do High do primeiro.
- Bearish FVG: High do terceiro candle abaixo do Low do primeiro.
- A zona é marcada como mitigada quando o preço posterior atravessa o extremo oposto da zona.

### Sweep
- Buy-side liquidity sweep: preço supera um swing high e fecha novamente abaixo dele.
- Sell-side liquidity sweep: preço perde um swing low e fecha novamente acima dele.

### MSS
Após um sweep recente, o motor procura fechamento além do swing oposto. Isso cria um evento de mudança de estrutura (MSS) para fins de classificação.

### Order Block
O motor procura, nos cinco candles anteriores ao MSS, o último candle contrário ao deslocamento:
- MSS bullish → último candle bearish.
- MSS bearish → último candle bullish.

A zona do OB é o range completo do candle identificado.

### Premium / Discount
Como referência transparente, a aba usa o 50% da máxima/mínima do próprio dia:
- acima de 50% = Premium;
- abaixo de 50% = Discount.

## Condição de possível setup

O sistema **não transforma FVG/OB isolado em entrada**.

Um possível setup precisa de:
1. POI não mitigado;
2. último MSS compatível com a direção do POI;
3. se o preço estiver dentro/próximo do POI: `POI ATIVADO — aguardar confirmação`;
4. se estiver distante: `AGUARDANDO RETORNO AO POI`.

A confirmação final não é automatizada como ordem. O objetivo é apresentar contexto e região para validação no gráfico.

## Escala

Algumas exportações do Profit aparecem com WIN em torno de `184,69`, enquanto a leitura operacional costuma ser `184.690`. O motor mantém os cálculos na escala original e, quando detecta preços abaixo de 1.000, exibe multiplicados por 1.000.

## Uso

1. Exporte o histórico de WINFUT em 5 minutos no Profit.
2. Abra `ICT Analysis`.
3. Selecione o CSV.
4. Clique em `Analisar ICT`.
5. Escolha outro dia no seletor para recalcular sem reenviar o arquivo.
