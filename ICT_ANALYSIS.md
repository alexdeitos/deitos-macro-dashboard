# ICT Analysis — WINFUT 5m

A aba **ICT Analysis** lê candles de 5 minutos exportados do Profit e transforma o histórico em um mapa de price delivery com foco em **liquidez → sweep → displacement → MSS/BOS → POI → retorno**.

## Entrada

O CSV do Profit deve conter:

- `Ativo`
- `Data`
- `Hora`
- `Abertura`
- `Máximo`
- `Mínimo`
- `Fechamento`

`Volume` e `Quantidade` são opcionais.

A aba tem duas formas de carregar o arquivo:

1. **Carregar data/**: usa automaticamente o CSV mais recente da pasta `data/`, priorizando arquivos cujo nome contenha `WIN`.
2. **Upload manual**: seleciona diretamente um CSV exportado do Profit.

## Hierarquia da análise

O motor não considera qualquer FVG/OB como oportunidade equivalente. Ele procura uma sequência estrutural:

```text
Liquidez / pool
        ↓
      Sweep
        ↓
   Displacement
        ↓
      MSS/BOS
        ↓
 FVG / Order Block
        ↓
 retorno à região
        ↓
 confirmação de preço
```

Um retorno à zona não vira ordem automática.

## Swings

Swing High e Swing Low são confirmados com 2 candles de cada lado. Essa estrutura é usada para localizar níveis que podem servir como liquidez interna.

## Liquidez

O mapa trabalha com:

- Equal Highs e Equal Lows agrupados por até 2 ticks;
- máxima e mínima da sessão selecionada;
- PDH e PDL quando existe pelo menos um pregão anterior dentro do CSV;
- classificação interna/externa;
- distância do preço atual;
- força relativa baseada no tipo de pool e número de toques.

Os níveis são **possíveis pools de liquidez**, não prova de ordens stop escondidas.

## Sweep

Um sweep é marcado quando o preço atravessa uma pool de liquidez e o candle fecha novamente para dentro do nível:

- BSL acima do nível e fechamento abaixo → sweep de buy-side;
- SSL abaixo do nível e fechamento acima → sweep de sell-side.

O motor evita contar repetidamente o mesmo pool.

## Displacement

Um candle é tratado como displacement quando seu range é pelo menos 1,35x a média recente e o corpo representa pelo menos 55% do range.

O displacement é usado como filtro para reduzir FVGs pequenos/isolados e para ligar estrutura a zonas relevantes.

## MSS e BOS

Depois de um sweep recente, o motor procura fechamento além do swing oposto:

- quebra contrária ao viés estrutural vigente → **MSS**;
- quebra na mesma direção do viés vigente → **BOS**.

Assim o painel diferencia mudança de estrutura de continuação.

## Fair Value Gap

FVG é detectado pelo padrão de três candles:

- bullish: `Low[3] > High[1]`;
- bearish: `High[3] < Low[1]`.

Os FVGs passam por um filtro de relevância. São priorizados quando ligados a displacement, sweep ou MSS, ou quando o gap tem tamanho material frente ao range médio.

Estados:

- `OPEN`: ainda não tocado;
- `PARTIAL`: houve retorno/interseção, mas o gap não foi completamente preenchido;
- `FILLED`: o extremo oposto do gap foi atravessado.

## Order Block

Para reduzir falsos OBs, o motor procura o **último candle contrário imediatamente antes de MSS ou de um BOS com displacement**.

Estados:

- `OPEN`: não mitigado;
- `PARTIAL/FILLED`: o preço voltou à zona;
- `INVALIDATED`: houve fechamento além do limite do OB.

Apenas OBs ligados a eventos estruturais entram na lista principal.

## Premium / Discount

A sessão selecionada é dividida pelo 50% entre máxima e mínima:

- acima de 50% → `PREMIUM`;
- abaixo de 50% → `DISCOUNT`;
- próximo do centro → `EQUILIBRIUM`.

O filtro P/D é usado como confluência, sem criar entrada por si só.

## POIs prioritários

A lista principal é ordenada pela combinação de:

- Fresh/Open;
- relação com sweep;
- relação com MSS;
- displacement;
- alinhamento Premium/Discount;
- recência;
- distância ao preço.

Isso faz com que o gráfico destaque **poucas regiões relevantes**, em vez de preencher toda a tendência com FVGs antigos.

## Possíveis cenários

Um cenário condicional exige:

- POI ativo;
- viés estrutural compatível;
- pelo menos duas confluências;
- retorno próximo ou dentro da zona para ativação.

Quando ainda está distante:

`AGUARDANDO RETORNO AO POI`

Quando entra na região:

`POI ATIVADO — aguardar confirmação`

O painel ainda informa invalidação e a primeira liquidez disponível no sentido do cenário como referência de contexto. Isso não constitui execução automática nem garantia de resultado.

## Gráfico

O mapa mostra:

- candles reais de 5 minutos;
- FVGs e OBs prioritários projetados para a direita;
- liquidez selecionada;
- PDH/PDL quando disponíveis;
- máxima/mínima do dia;
- EQ 50%;
- sweep;
- MSS/BOS;
- swings opcionais.

Há controles para exibir/ocultar zonas mitigadas, swings e liquidez.

## Escala do WIN

Alguns CSVs podem trazer `184.690`, enquanto outros sistemas trabalham com `184,690` pontos. O parser normaliza arquivos que chegam em escala decimal para a escala operacional de pontos, evitando a distorção da leitura no gráfico.

## Uso diário

1. Exporte o WINFUT em 5 minutos no Profit.
2. Salve o CSV em `data/` ou use o upload manual.
3. Abra **ICT Analysis**.
4. O botão **Carregar data/** pode ler automaticamente o CSV mais recente.
5. Escolha a data quando o arquivo tiver mais de um pregão.
6. Leia primeiro o bloco de contexto e a sequência `Sweep → MSS/BOS → POI`.
7. Use o gráfico para validar visualmente o contexto antes de qualquer execução.
