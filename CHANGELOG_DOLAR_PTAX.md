# Alterações — Dólar / PTAX

## Nova página
- `/dolar/` — terminal dedicado ao WDO/PTAX.
- `/api/dollar-analysis/` — payload automático do módulo.

## Cálculos
- PTAX anterior + prévias 10h/11h/12h/13h.
- Projeção neutra da PTAX.
- Média restante necessária para atingir um alvo.
- Forward teórico por diferencial composto BR x Treasury 1Y.
- WDO versus justo em pontos e percentual.
- Proxy de abertura e faixa configurável.
- Leitura automática DXY/VIX/EWZ/Dow/score WDO.

## Coleta BCB
O payload da PTAX agora guarda, quando disponíveis, as prévias do dia e a referência PTAX anterior para alimentar o terminal web sem RTD do Profit.

## Segurança
O arquivo `.env` usado no ambiente original foi deliberadamente excluído do pacote. Use `.env.example` e informe suas próprias credenciais.
