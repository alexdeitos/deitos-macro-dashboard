# Ponte Excel/Profit RTD -> Django

## Por que esta ponte existe?

O `COTACOES*.xlsm` contém fórmulas `RTDTrading.RTDServer`. O valor vivo do RTD
existe na memória do Excel/Windows e **não precisa ser salvo no arquivo**.
Um container Linux/Docker não consegue enxergar o estado COM do Excel.

Por isso o fluxo correto é:

Profit → RTD → Excel (Windows) → ponte COM → HTTP → Django → PostgreSQL → Daytrade

O Django mantém a leitura do arquivo como fallback, mas a fonte ao vivo passa a
ser a ponte Windows.

## Instalação

1. Deixe Profit e Excel abertos.
2. Abra `CONFIG_CAPTURA` no workbook.
3. Confirme que os valores RTD aparecem nas colunas B:E.
4. Coloque `COTACOES.xlsm` ao lado desta pasta `tools` ou informe o caminho:
   `profit_excel_bridge.py "C:\caminho\COTACOES.xlsm"`
5. Execute `start_profit_bridge.bat`.

A ponte envia 1 snapshot por minuto para:
`http://127.0.0.1:8000/api/capturas/ingest/`

Ajuste `BRIDGE_INTERVAL_SECONDS` para outra frequência somente quando necessário.

## Diagnóstico

A linha `SEM DADOS LIVE` significa que o Excel ainda não entregou valores
numéricos. Isso normalmente aponta para o RTD do Excel/Profit, não para o
Django.

O projeto também informa no log o número de células RTD que retornam erro.

## RTD

No Excel:
Arquivo → Opções → Suplementos.

Primeiro verifique **Itens Desabilitados**. Se `rtdtrading.rtdserver` aparecer,
ative-o. Depois, em **Suplementos COM**, confirme que o componente do Profit está
ativo.

Na guia **Conteúdo Externo**, habilite:
- todas as conexões de dados;
- atualização automática de links.

Com o Profit aberto, use a função de exportação RTD/DDE do próprio Profit pelo
menos uma vez e faça um teste simples em uma célula:
`=RTD("RTDTrading.RTDServer";;"AALR3_B_0";"ULT")`

Se o campo `Local`/caminho do suplemento RTD estiver vazio ou o componente não
aparecer, a instalação/integração Excel/Profit precisa ser reparada/reinstalada.
