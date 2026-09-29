ARQUIVO DE CAPTURA DO PROFIT

Coloque aqui o COTACOES.xlsm que o Excel/Profit atualiza dinamicamente.
O Django/Celery lê a aba CONFIG_CAPTURA a cada 60 segundos.

Para usar outro caminho sem alterar o .env, defina CAPTURE_XLSM_PATH no ambiente
antes de subir o docker compose.

Símbolos lidos diretamente pela aplicação para os cards principais:
- IBOV (aliases: IBOVESPA, IBOVFUT, IBOVESPAFUT)
- WINFUT (alias: WIN)
- SP500_FUT (aliases: SP500FUT, ES1!, ES)
