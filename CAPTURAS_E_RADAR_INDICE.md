# Capturas Excel → Radar Direcional do Índice

## Fluxo

`Profit/RTD → aba HISTORICO do COTACOES.xlsm → POST/importação → CapturePoint → Radar do Índice`

A nova página é `/radar-indice/`. Ela combina:

- pressão ponderada das ações capturadas, usando a Carteira do Dia do Ibovespa publicada pela B3 quando disponível;
- drivers externos do coletor do próprio dashboard (DJI, S&P 500, Nasdaq, VIX, DXY, Brent, WTI, minério e EEM);
- Treasury 10Y via FRED, quando configurado, ou captura `US10Y`;
- juros B3 capturados em símbolos começando por `DI1`, `DAP`, `PRE` ou `DIF`;
- correlação de Pearson com amostra coincidente recente quando existe histórico suficiente.

## Importar o Excel

Na página **Radar Índice**, use **Importar COTACOES.xlsm**. O importador lê primeiro a aba `HISTORICO`, com as colunas `Data/Hora`, `Aba`, `Ativo`, `Último`, `Variação`, `Negócios` e `Volume`.

Também existe o comando:

```bash
python manage.py import_capture_workbook /caminho/COTACOES.xlsm
```

## Ingestão em tempo real

O endpoint `POST /api/capturas/ingest/` aceita:

```json
{
  "observed_at": "2026-09-13T14:12:01-03:00",
  "rows": [
    {"sheet":"Planilha1","symbol":"VALE3","value":100.1,"change_percent":1.2},
    {"sheet":"Planilha1","symbol":"PETR4","value":39.8,"change_percent":-0.7}
  ]
}
```

Isso permite ligar futuramente a macro/VBA do Excel diretamente ao Django sem alterar as credenciais do projeto.

## Interpretação

O score é **viés**, não probabilidade e não ordem automática. A direção final deve ser confirmada por estrutura de preço, VWAP, fluxo, liquidez e pelo seu gatilho operacional.

## Sincronização automática do Excel

O Radar Índice lê automaticamente a aba `CONFIG_CAPTURA` do `COTACOES.xlsm` a cada 60 segundos por uma tarefa Celery Beat. O diretório `./data` do projeto é montado como `/app/data` nos containers web, worker e beat.

O caminho padrão é `/app/data/COTACOES.xlsm`. Não é necessário alterar o `.env`; para usar outro arquivo, a variável `CAPTURE_XLSM_PATH` pode ser definida no ambiente antes de subir o Compose.

A captura automática grava uma fotografia por minuto e calcula a variação percentual de cada ação comparando o preço atual com a última captura. A opção manual `Importar COTACOES.xlsm` continua disponível.
