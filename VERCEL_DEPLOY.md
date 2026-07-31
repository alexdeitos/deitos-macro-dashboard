# Deploy no Vercel — Django com SQLite temporário

Esta edição usa SQLite em `/tmp/macro_dashboard.sqlite3`. Ela não precisa de Neon,
PostgreSQL ou outro banco externo.

## Comportamento esperado

- O banco é criado automaticamente pelas migrações no primeiro cold start.
- Os dados podem permanecer durante execuções quentes da mesma instância.
- Os dados podem desaparecer após cold start, troca de instância, escalonamento ou novo deploy.
- Duas instâncias simultâneas podem ter bancos diferentes.
- Não use esta edição para histórico confiável, usuários permanentes ou dados críticos.

## 1. Envie o projeto para o GitHub

```bash
git init
git add .
git commit -m "Deploy Vercel SQLite temporario"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/macro-dashboard.git
git push -u origin main
```

## 2. Importe na Vercel

1. Abra a Vercel.
2. Clique em **Add New > Project**.
3. Importe o repositório.
4. Deixe a raiz do projeto como Root Directory.
5. Faça o primeiro deploy.

O `vercel.json` já direciona todas as rotas para `api/index.py` e executa
`collectstatic` no build.

## 3. Variáveis de ambiente

Em **Settings > Environment Variables**, cadastre:

```env
DJANGO_SECRET_KEY=uma-chave-segura
DEBUG=False
ALLOWED_HOSTS=.vercel.app
CSRF_TRUSTED_ORIGINS=https://SEU-PROJETO.vercel.app
SQLITE_PATH=/tmp/macro_dashboard.sqlite3
INVESTING_ENABLED=True
NEWS_ENABLED=True
ECONOMIC_CALENDAR_ENABLED=True
```

Para gerar uma chave:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Depois faça **Redeploy**.

## 4. Teste

Abra:

```text
https://SEU-PROJETO.vercel.app/
```

Clique em **Atualizar fontes agora**. A primeira abertura pode demorar mais porque
as migrações do SQLite são executadas no cold start.

## 5. Limitações práticas

- Não existe histórico garantido entre instâncias.
- O admin e usuários criados podem desaparecer junto com o SQLite.
- Evite múltiplos cliques simultâneos, pois SQLite aceita poucas escritas concorrentes.
- Arquivos em `/tmp` também são temporários.
- Scraping do Investing pode ser bloqueado por IP, proteção anti-bot ou limite de tempo.

## 6. Paridade REAL / EUR-USD

O card calcula:

```text
EUR/BRL ÷ EUR/USD
```

Ele só mostra valor quando as duas cotações foram coletadas. Caso contrário, mostra
`N/D`, sem fallback artificial.
