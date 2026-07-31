# Diário Trade

A página `/diario/` transforma o Macro Dashboard em um diário operacional com análise quantitativa baseada nas operações registradas.

## Registro da operação

Cada trade pode armazenar:

- conta operacional e capital inicial;
- data, horário de entrada e saída;
- WIN, WDO, contratos cheios, ações ou outro ativo;
- compra/venda, setup, contratos, entrada, saída e saídas parciais;
- stop planejado, MAE, MFE, custos e resultado manual opcional;
- print por upload ou URL;
- leitura técnica, notas de execução, emoções, disciplina, qualidade e erros;
- existência de notícia, impacto percebido e evento da Trading Economics ligado;
- score/viés do cálculo de abertura e avaliação se o cálculo bateu;
- snapshot de mercado mais próximo da entrada.

O sistema calcula automaticamente pontos, resultado bruto, custos, líquido, contratos abertos, risco financeiro e relação risco/retorno. Valores por ponto padrão:

- WIN: R$ 0,20 por ponto por contrato;
- WDO: R$ 10,00 por ponto por contrato;
- IND: R$ 1,00 por ponto por contrato;
- DOL: R$ 50,00 por ponto por contrato.

O valor pode ser ajustado no cadastro para ativos diferentes.

## Diário do dia

A navegação por data mostra resultado líquido, pontos, quantidade de trades, taxa de acerto e aderência ao plano. É possível registrar plano de abertura, leitura pré-mercado, revisão do dia e dias em que foi decidido não operar.

## Análise de performance

O painel calcula:

- capital atual, retorno, lucro líquido e drawdown;
- win rate, Profit Factor, payoff e média por operação;
- média de ganho/perda, sequências de wins/losses e dias positivos;
- melhor e pior operação;
- operação com maior ganho em pontos;
- melhor horário e melhor setup;
- rankings por setup, horário, dia da semana, ativo e direção;
- comparação de trades com/sem notícia;
- comparação pelo impacto percebido da notícia;
- comparação quando o cálculo de abertura bateu ou não;
- comparação entre operações dentro e fora do plano;
- curva de capital e drawdown.

## Capital

Cada conta possui capital inicial e histórico de aportes, retiradas e ajustes. O capital atual é calculado por:

`capital inicial + movimentações + resultado líquido dos trades`

## Prints

Os prints são gravados no volume Docker `trade_media`. Esse volume não é removido em um `docker compose down` normal. Não execute `docker compose down -v` caso queira preservar banco, Redis e imagens.

## Instalação

```bash
docker compose down
docker compose up -d --build
```

A migração do diário é aplicada automaticamente pelo serviço web.
