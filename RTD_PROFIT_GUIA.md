# RTD Profit → Excel → Django — guia de diagnóstico

## O problema encontrado no seu arquivo

O projeto anterior estava lendo o arquivo `.xlsm` com `openpyxl` dentro do Linux/Docker.
Isso lê somente o **cache salvo no arquivo**, não o estado RTD que está na memória do Excel.
Além disso, o arquivo `COTACOES.xlsm` enviado nesta conversa não apresentou conteúdo
legível pelo indexador; a validação binária mostrou que ele contém fórmulas RTD e que,
nas células testadas, o valor cacheado estava como `#N/A`.

O log do container mostra que o Celery está sendo executado corretamente a cada minuto e
está lendo 280 linhas do arquivo, mas sempre com o mesmo `file_mtime`. O mesmo log também
mostra o erro real do Daytrade: `KeyError: 'stock_pressure'`. fileciteturn2file0L229-L244

## Arquitetura corrigida

Profit
→ RTDTrading.RTDServer
→ Excel/CONFIG_CAPTURA (estado vivo)
→ `tools/profit_excel_bridge.py` no Windows
→ `POST /api/capturas/ingest/`
→ PostgreSQL
→ Radar / Daytrade

A tarefa Celery continua rodando a cada 60s como fallback. Ela não substitui mais uma
captura COM fresca pela cópia salva do workbook.

## Como fazer o Profit voltar a alimentar o Excel

A Nelogica documenta que a função deve usar a assinatura:
`=RTD("RTDTrading.RTDServer";;"Ativo";"Atributo")`.
Também informa que somente uma exportação em tempo real pode ser usada por vez. citeturn970878search1turn970878search2

No Excel:
- Arquivo → Opções → Suplementos → **Itens Desabilitados** → ative `rtdtrading.rtdserver` se ele estiver lá.
- Depois **Suplementos COM** → Ir → deixe o suplemento do Profit ativo.
- Em **Conteúdo Externo**, habilite todas as conexões de dados e a atualização automática de links.
- Com o Profit aberto, faça novamente a exportação RTD/DDE e teste:
  `=RTD("RTDTrading.RTDServer";;"AALR3_B_0";"ULT")`.

A documentação oficial da Nelogica orienta inclusive verificar/reativar o RTD nos Itens
Desabilitados e, quando o componente não apresenta local/caminho, refazer a instalação
do Excel/integração. citeturn970878search0

## Se o RTD continua #N/A

Execute no Windows:

`tools\check_rtd.ps1`

Se `Type.GetTypeFromProgID("RTDTrading.RTDServer")` não encontrar o componente, o
problema está no registro/instalação do componente Excel/Profit, não no Django.

## Como ligar a ponte

Deixe:
- Profit aberto;
- Excel aberto;
- `COTACOES.xlsm` aberto;
- aba `CONFIG_CAPTURA` aberta ou no mesmo workbook.

Depois execute:

`tools\start_profit_bridge.bat`

A ponte se conecta à instância existente do Excel e lê o valor **em memória**, portanto
não depende de salvar o arquivo a cada minuto.

## Diagnóstico

Ponte online:

`GET http://127.0.0.1:8000/api/capturas/status/`

O retorno deverá mostrar `ONLINE`, horário da última captura e quantidade de ativos.

Caso apareça `SEM_PONTE`, o Windows bridge não está rodando.

Caso apareça `ONLINE`, mas os ativos estejam faltando, verifique no console da ponte
quantas células RTD estão retornando erro.

## Observação

Não é tecnicamente possível fazer o Docker/Linux "ativar" o RTD COM do Excel. O RTD é uma
integração do Windows/Excel/Profit. A ponte Windows foi adicionada justamente para
separar essa camada da aplicação Django.
