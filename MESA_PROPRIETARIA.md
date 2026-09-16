# Análise de Mesa Proprietária

A aba **Mesa Proprietária** permite cadastrar os parâmetros de uma conta/plano e avaliar relatórios de performance do Profit sem perder o histórico.

## Parâmetros

- Nome da conta
- Mesa (MIDE por padrão)
- Plano
- Valor do plano
- Tamanho/saldo inicial
- Perda máxima
- Meta/take necessário para aprovação
- Máximo de contratos por dia

Os valores são configuráveis; o sistema não presume regras oficiais que não tenham sido informadas pelo usuário.

## Estados

- **Em avaliação:** resultado ainda não atingiu a meta e não atingiu o limite de perda.
- **Meta atingida:** resultado acumulado alcançou a meta configurada.
- **Eliminada:** resultado acumulado atingiu ou ultrapassou a perda máxima configurada.
- **Dados insuficientes:** não há operações para avaliar.

## Controles de performance

O relatório é analisado por resultado acumulado, win rate, profit factor, pior dia, maior perda individual e maior número de contratos observado em um dia.

Além das regras configuradas pelo usuário, o painel apresenta dois controles internos de prudência: perda individual acima de 10% do limite total e pior dia acima de 25% do limite total. Eles são **alertas de gestão**, não regras da MIDE.

Cada importação gera uma nova avaliação no banco, permitindo selecionar novamente a conta e importar outro relatório sem apagar avaliações anteriores.
