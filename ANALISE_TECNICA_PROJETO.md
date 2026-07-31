# Análise técnica do Macro Dashboard

## Resultado

O erro HTTP 403 não era um bloqueio permanente do IP: uma chamada isolada retornou HTTP 200. O padrão do projeto, porém, favorecia um bloqueio temporário por automação.

## Principais achados

1. **Rajada de requisições**: 15 páginas em poucos segundos, repetidas a cada 120 segundos.
2. **Fingerprint inconsistente**: `impersonate="chrome"` junto de `User-Agent` fixo de Chrome 124.
3. **Fallback contraproducente**: após 403, a URL era repetida imediatamente com `requests`.
4. **Ausência de circuit breaker**: o lote continuava mesmo após bloqueio claro do domínio.
5. **Coleta lenta sem cache**: ADRs e títulos eram consultados com a mesma frequência dos preços intradiários.
6. **Diagnóstico limitado**: o log não preservava status, `CF-RAY`, retries, cache hits ou abertura do circuito.
7. **Configuração insegura**: `ALLOWED_HOSTS=["*"]` ignorava o valor correto já presente no `.env`.
8. **Dependência ampla demais**: `curl-cffi>=0.11,<1` permitia atualizações maiores sem validação. O limite foi reduzido para `<0.17`.

## Validação executada

- Compilação de todos os módulos Python: aprovada.
- Testes originais do projeto: aprovados.
- Novos testes do cliente Investing: aprovados.
- Total: 23 testes aprovados.

A validação externa ao vivo não foi executada no ambiente de revisão porque ele não possui resolução DNS pública. O teste feito no container do projeto pelo usuário retornou HTTP 200 e comprova que o endpoint está acessível a partir do ambiente real.
