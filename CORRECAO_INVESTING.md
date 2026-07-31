# Correção do sinal e da escala do Investing

## Problema encontrado

O parser genérico interpretava qualquer número entre parênteses como negativo. O Investing Brasil costuma exibir percentuais assim:

- `(+2,97%)`
- `(-0,42%)`

Por isso, uma alta como `(+2,97%)` era transformada em `-2,97%`.

Também havia um segundo problema: no locale pt-BR, `177.866` representa 177.866 pontos, mas o parser automático armazenava `177.866` como número decimal, fazendo o cartão do Ibovespa aparecer como `177,87`.

## Correções implementadas

1. `parse_percent()` remove parênteses visuais e preserva o sinal explícito.
2. `parse_number_pt_br()` trata ponto como milhar e vírgula como decimal para páginas do Investing Brasil.
3. O percentual é validado contra preço atual e fechamento anterior.
4. O sinal só é corrigido automaticamente quando as magnitudes coincidem.
5. Divergências ficam registradas em `quote.raw.validation`.
6. Foi adicionado o comando `repair_market_history` para reparar snapshots antigos e recalcular os scores.

## Aplicação no projeto existente

```bash
docker compose up -d --build

docker compose exec web python manage.py repair_market_history --dry-run
docker compose exec web python manage.py repair_market_history

docker compose exec web python manage.py collect_market_data
docker compose exec web python manage.py collectstatic --noinput

docker compose restart web celery-worker celery-beat
```

Depois, confira o JSON bruto. Para o exemplo analisado, o esperado é algo próximo de:

```json
"IBOV": {
  "value": 177866.0,
  "change_percent": 2.97,
  "previous_close": 172742.0
}
```

O valor exato do percentual pode variar algumas casas decimais quando for recalculado pelos preços.
