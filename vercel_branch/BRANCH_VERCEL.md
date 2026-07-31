# Branch Vercel

Esta edição não consulta o Investing diretamente. Ela importa o snapshot protegido publicado pela edição local.

Variáveis essenciais na Vercel:

- `USE_REMOTE_MARKET_JSON=True`
- `REMOTE_MARKET_JSON_URL=https://SEU-TUNEL.trycloudflare.com/api/public-market-snapshot/`
- `REMOTE_MARKET_JSON_TOKEN` igual ao `PUBLIC_MARKET_API_TOKEN` da edição local
- `INVESTING_ENABLED=False`

Depois de alterar a URL do Quick Tunnel, atualize a variável na Vercel e faça Redeploy.
