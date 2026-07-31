# Vercel consumindo o JSON do projeto local

A edição Vercel usa o projeto local como fonte principal quando estas variáveis estão definidas:

```env
USE_REMOTE_MARKET_JSON=True
REMOTE_MARKET_JSON_URL=https://SEU-TUNEL.trycloudflare.com/api/public-market-snapshot/
REMOTE_MARKET_JSON_TOKEN=SEU_TOKEN
REMOTE_MARKET_MAX_AGE_SECONDS=900
INVESTING_ENABLED=False
```

## Funcionamento

1. O projeto local coleta Investing, BCB, AwesomeAPI e demais fontes.
2. O Cloudflare Tunnel publica apenas o endpoint JSON.
3. A Vercel consulta o endpoint usando `X-Market-Token`.
4. O snapshot é salvo no SQLite temporário da instância e exibido no dashboard.
5. O campo `collected_at` original é preservado.

Ao iniciar uma instância sem dados, `/api/dashboard/` tenta importar automaticamente o primeiro snapshot remoto. O botão **Atualizar fontes agora** faz uma nova importação.

## Variáveis na Vercel

Cadastre em Production, Preview e Development e depois faça Redeploy.

```env
USE_REMOTE_MARKET_JSON=True
REMOTE_MARKET_JSON_URL=https://SEU-ENDERECO/api/public-market-snapshot/
REMOTE_MARKET_JSON_TOKEN=SEU_TOKEN
REMOTE_MARKET_MAX_AGE_SECONDS=900
INVESTING_ENABLED=False
NEWS_ENABLED=False
ECONOMIC_CALENDAR_ENABLED=False
```

Se estiver usando `/api/raw/` sem token, deixe `REMOTE_MARKET_JSON_TOKEN` vazio. Para produção, use o endpoint protegido.

## Quick Tunnel

A URL `trycloudflare.com` muda quando o processo reinicia. Depois de gerar uma nova URL, atualize `REMOTE_MARKET_JSON_URL` na Vercel e faça Redeploy.

## Dados antigos

Se o snapshot local tiver mais que `REMOTE_MARKET_MAX_AGE_SECONDS`, a Vercel rejeita a importação para não exibir cotação antiga como atual. Use `0` para desativar essa validação.
