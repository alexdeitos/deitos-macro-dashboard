# Alterações — 29/09/2026

## Ibovespa
- O card **Ibovespa** passa a tentar primeiro a célula exata `CONFIG_CAPTURA!B38` do workbook configurado em `data/COTACOES*.xlsm`.
- A leitura exige que a coluna A da mesma linha identifique `IBOV`; isso evita mostrar acidentalmente outro ativo caso a estrutura do Excel esteja diferente.
- Se `B38` não estiver disponível ou não corresponder a `IBOV`, permanece o fallback já existente da captura `CONFIG_CAPTURA`/ponte Excel.
- O card continua exibindo o Ibovespa com 3 casas decimais.

## Mesa Proprietária
- Ao importar o relatório do Profit, a avaliação agrupa o resultado líquido por dia.
- Calcula 50% do **Take/meta para aprovação** configurado na conta.
- Identifica todos os dias em que o gain líquido do dia ultrapassou esse limite.
- Para cada ocorrência mostra: data, gain do dia, limite de 50% e excedente.
- Também informa o excedente total que precisa ser distribuído/ganho em outro(s) dia(s), conforme a validação solicitada.
- A validação usa o mesmo resultado líquido após custos operacionais utilizado no cálculo da meta.
- A regra fica disponível no payload `metrics.fifty_percent_take_rule`, sem necessidade de nova migração de banco.

## Correção adicional
- Corrigida a numeração das linhas Excel em `capture_import.py`, que estava referenciando uma variável de linha não definida.

## Validação técnica
- Python: `compileall` concluído sem erros.
- JavaScript: `node --check` concluído sem erros.
- O ambiente deste pacote não possui Django instalado no host e não possui Docker disponível, portanto a suíte Django completa não pôde ser executada neste ambiente.
