# Branch local

Esta edição coleta diretamente AwesomeAPI, BCB, Investing, notícias e calendário.

## Início

```bash
conda activate python
pip install -r requirements.txt
./start-local.sh
```

## Endpoint para a Vercel

```bash
curl -H "X-Market-Token: $PUBLIC_MARKET_API_TOKEN" \
  http://127.0.0.1:8000/api/public-market-snapshot/
```

Em outro terminal:

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```
