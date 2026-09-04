# Análise do modelo de Dólar / PTAX

## O que foi encontrado nas planilhas

### `Calculo Abertura do Dollar e PTAX.xlsx`
O modelo principal da aba `Aber.Dollar` usa a estrutura:

- abertura proxy do futuro a partir do fechamento do futuro e de uma taxa/variação de carregamento;
- preço justo/carry a partir de uma taxa brasileira e do prazo;
- máxima e mínima como abertura ajustada por uma faixa fixa em pontos;
- quatro referências PTAX em 10h, 11h, 12h e 13h.

### `Calculo-PTAX.xlsx`
A pasta reúne quatro abas relevantes. `ESTUDO_PTAX` implementa a lógica de simetria:

`PTAX_alvo = média das quatro consultas`

e, com algumas consultas conhecidas, calcula a média necessária das consultas restantes para atingir um alvo. As fórmulas de referência são da forma:

`alvo * 4 - soma_das_consultas_conhecidas`

normalizada pela quantidade de consultas ainda não preenchidas.

A aba `Abertura Dólar` reutiliza a lógica de abertura, carry, máxima/mínima e integração com cotações RTD do Profit.

## Problemas identificados

1. Há células com `#VALUE!` e `#DIV/0!` em `ESTUDO_PTAX` quando as consultas ainda não estão preenchidas.
2. A dependência de `RTD("rtdtrading.rtdserver",...)` torna a lógica pouco portável para web.
3. O modelo antigo mistura escala de preço (pontos) e cotação (BRL/USD) sem explicitar sempre a conversão x1.000.
4. A PTAX oficial do BCB e a prévia do processo de fixing não estavam isoladas como entidades distintas no projeto web.
5. A paridade teórica atual do projeto usa Treasury 1Y, mas a tela anterior não apresentava ao trader a cadeia completa `spot -> justo -> prêmio/desconto -> decisão`.

## O que foi incorporado ao Django

- novo serviço puro: `dashboard/services/dollar_analysis.py`;
- nova página: `/dolar/`;
- API: `/api/dollar-analysis/`;
- coleta BCB enriquecida com `previous_ptax_midpoint` e `today_bulletins`;
- calculadora local para quatro prévias PTAX;
- cálculo de média restante necessária para atingir PTAX alvo;
- forward teórico por diferencial composto de taxa BR e Treasury 1Y;
- prêmio/desconto do WDO em pontos e percentual;
- mapa de níveis com abertura proxy, justo, PTAX e faixa;
- insights automáticos com DXY/VIX/EWZ/Dow/score WDO;
- protocolo de confirmação por preço, volume, VWAP e estrutura;
- testes unitários específicos do módulo.

## Metodologia de PTAX

O Banco Central informa quatro consultas diárias, com início aleatório dentro das janelas de 10h00–10h10, 11h00–11h10, 12h00–12h10 e 13h00–13h10, cada consulta com duração de dois minutos. A PTAX de fechamento é formada pelas médias das taxas apuradas nas consultas. A tela web mantém esse conceito, mas trabalha somente com os valores de prévia que efetivamente estiverem disponíveis.

Fonte: BCB, Resolução BCB nº 45/2020.

## Contrato WDO

O WDO é cotado em BRL por USD 1.000 e seu tick mínimo é de BRL 0,5 por USD 1.000. O vencimento segue o primeiro dia de sessão de negociação do mês de vencimento, sujeito às condições específicas do contrato.

Fonte: B3, especificação do Contrato Futuro Mini de Taxa de Câmbio de Reais por Dólar Comercial.

## Uso para daytrade

O módulo não produz probabilidade de acerto. A leitura recomendada é hierárquica:

1. preço justo e PTAX;
2. prêmio/desconto do WDO;
3. DXY, VIX, EWZ, Dow Jones e score direcional;
4. comportamento do preço na abertura;
5. volume/VWAP/estrutura como confirmação;
6. invalidação explícita antes de entrar.

Prêmio/desconto, PTAX e macro são contexto; não devem ser tratados como gatilho isolado.
