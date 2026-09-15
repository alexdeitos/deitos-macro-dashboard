# Validação de Operações

A aba **Validação Operações** importa o CSV de performance do Profit, calcula os principais indicadores e permite revisar cada trade.

Fluxo:
1. Importar `relatorio performance.csv`.
2. Selecionar um trade.
3. Registrar justificativa, nota 0–10 e observação do setup.
4. Salvar a validação.
5. Clicar em **Salvar no Diário** para criar o trade correspondente no Diário de Trade.

A direção é inferida pelo campo `Lado` do Profit (`C` = compra, `V` = venda). Os preços e o resultado vêm diretamente do relatório importado. O envio ao Diário grava o resultado reportado no campo financeiro do trade, sem tentar recalcular o valor do relatório.

## Radar + Excel

A sincronização ao vivo lê a aba `CONFIG_CAPTURA` a cada 60 segundos pelo Celery Beat. O caminho padrão é o arquivo `COTACOES*.xlsm` mais recente em `/app/data`; isto evita depender de um nome fixo. O volume montado em Docker é `./data:/app/data:ro`, então o arquivo no host deve ser o mesmo arquivo que o Excel/Profit está atualizando.
