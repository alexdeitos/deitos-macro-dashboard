# Motor de análise de abertura

A seção **Análise de abertura — WIN e WDO** usa exclusivamente o snapshot mais recente coletado pelas fontes configuradas.

## Como ler

- Score acima de +15: viés comprador condicional.
- Score abaixo de -15: viés vendedor condicional.
- Entre -15 e +15: aguardar confirmação.
- Score acima de +35 ou abaixo de -35: viés forte, ainda sujeito à confirmação do preço.

O score não é uma probabilidade estatística. Para produzir probabilidades reais, o sistema precisaria armazenar o resultado posterior de cada abertura e validar o modelo fora da amostra.

## Confirmação operacional

O painel recomenda esperar a formação inicial do preço e usar VWAP, volume e máxima/mínima da abertura como confirmação e invalidação. Ele não envia ordens e não substitui gerenciamento de risco.

## Limpeza do histórico antigo

Se o banco contiver snapshots gerados por uma versão anterior com erros de parsing, execute uma vez:

```bash
docker compose exec web python manage.py clear_market_history --confirm
```

Depois faça uma nova coleta pelo botão ou execute:

```bash
docker compose exec web python manage.py collect_market_data
```

## Correção de sinais do Investing

A versão atual separa o valor exibido pela fonte da orientação usada nos scores. IBOV, EWZ, S&P 500, Nasdaq, Brent e minério nunca têm o sinal invertido pelo motor. Somente DXY e VIX recebem orientação inversa dentro dos cálculos em que isso é explicitamente documentado.

O parser também trata os parênteses do Investing como formatação visual. Assim, `(+2,97%)` não é mais confundido com notação contábil negativa.

Para corrigir dados históricos já salvos:

```bash
docker compose exec web python manage.py repair_market_history --dry-run
docker compose exec web python manage.py repair_market_history
```
