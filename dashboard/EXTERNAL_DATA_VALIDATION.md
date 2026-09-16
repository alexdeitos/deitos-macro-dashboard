# Validação das fontes externas

O projeto usa três fontes principais no `MarketCollector`:

- AwesomeAPI — USD/BRL.
- Banco Central — SGS série 1178 (Selic anualizada base 252) + PTAX Olinda.
- Investing.com — instrumentos de mercado.

Também existem coletores independentes para calendário Investing, calendário Trading Economics e FRED.

## BCB / SGS 1178

A rota antiga `/dados/ultimos/5` foi removida do coletor. Desde 26/03/2025 o Portal de Dados Abertos do BCB informa que consultas JSON/CSV de séries históricas diárias passaram a exigir filtros e limita o período das consultas. O coletor agora solicita somente uma janela recente de até 10 dias.

Se a API SGS retornar 5xx/indisponibilidade, o código tenta o recurso JSON oficial correspondente à série 1178 no Portal de Dados Abertos. A falha da Selic não impede a PTAX de continuar sendo coletada.

## Diagnóstico

Execute dentro do container Django:

```bash
docker compose exec web python manage.py check_external_sources
```

Para testar sem FRED:

```bash
docker compose exec web python manage.py check_external_sources --no-fred
```

O comando testa as fontes de forma independente e imprime `OK`/`FALHA`, latência, quantidade de cotações e erros.
