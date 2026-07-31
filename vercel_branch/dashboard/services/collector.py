from __future__ import annotations

import time
from typing import Any

from django.utils import timezone

from .analytics import build_market_analysis
from .parity import build_dollar_parity
from .opening import build_opening_analysis
from .macro_opening import build_macro_opening_analysis
from .sources import AwesomeApiSource, BancoCentralSource, InvestingSource
from .types import Quote, SourceResult
from .remote_market import fetch_remote_market_snapshot, remote_market_enabled


def build_real_eur_usd_parity(quotes: list[Quote]) -> Quote | None:
    """Calcula a cotação cruzada BRL por USD usando EUR/BRL ÷ EUR/USD.

    A divisão elimina o euro da razão:
        (BRL/EUR) / (USD/EUR) = BRL/USD
    O valor só é publicado quando as duas pernas reais estão disponíveis.
    """
    latest: dict[str, Quote] = {}
    for quote in quotes:
        if quote.symbol not in {"EUR_BRL", "EUR_USD"} or quote.value is None:
            continue
        current = latest.get(quote.symbol)
        if current is None or quote.observed_at >= current.observed_at:
            latest[quote.symbol] = quote

    eur_brl = latest.get("EUR_BRL")
    eur_usd = latest.get("EUR_USD")
    if eur_brl is None or eur_usd is None or not eur_usd.value:
        return None

    value = eur_brl.value / eur_usd.value
    change_percent = None
    if eur_brl.change_percent is not None and eur_usd.change_percent is not None:
        denominator = 1 + (eur_usd.change_percent / 100)
        if denominator:
            change_percent = (
                ((1 + (eur_brl.change_percent / 100)) / denominator) - 1
            ) * 100

    return Quote(
        symbol="REAL_EUR_USD_PARITY",
        name="Paridade REAL / EUR-USD",
        category="calculated_currency",
        source="cálculo EUR/BRL ÷ EUR/USD",
        observed_at=max(eur_brl.observed_at, eur_usd.observed_at),
        value=value,
        change_percent=change_percent,
        currency="BRL por USD",
        source_url=None,
        raw={
            "formula": "EUR_BRL / EUR_USD",
            "eur_brl": eur_brl.as_dict(),
            "eur_usd": eur_usd.as_dict(),
        },
    )


class CollectionUnavailable(RuntimeError):
    pass


class MarketCollector:
    def __init__(self) -> None:
        self.sources = [AwesomeApiSource(), BancoCentralSource(), InvestingSource()]

    def collect(self) -> dict[str, Any]:
        if remote_market_enabled():
            return fetch_remote_market_snapshot()

        started = time.monotonic()
        collected_at = timezone.now()
        results: list[SourceResult] = [source.fetch() for source in self.sources]

        quotes: list[Quote] = []
        groups: dict[str, list[dict[str, Any]]] = {}
        for result in results:
            quotes.extend(result.quotes)
            for group_name, rows in result.groups.items():
                groups.setdefault(group_name, []).extend(rows)

        if not quotes:
            errors = " | ".join(f"{result.name}: {result.error}" for result in results)
            raise CollectionUnavailable(f"Nenhuma fonte retornou cotações. {errors}")

        calculated_parity = build_real_eur_usd_parity(quotes)
        if calculated_parity is not None:
            quotes.append(calculated_parity)

        quote_dicts = [quote.as_dict() for quote in quotes]
        quote_map: dict[str, dict[str, Any]] = {}
        for quote in quote_dicts:
            symbol = quote["symbol"]
            current = quote_map.get(symbol)
            if current is None or quote["observed_at"] >= current["observed_at"]:
                quote_map[symbol] = quote

        source_status = {result.name: result.status_dict() for result in results}
        successful_sources = sum(1 for result in results if result.ok)
        complete_sources = sum(1 for result in results if result.complete)
        duration_ms = int((time.monotonic() - started) * 1000)

        parity = build_dollar_parity(quotes, today=timezone.localdate())
        macro_opening = build_macro_opening_analysis(quotes)
        opening_analysis = build_opening_analysis(quotes, parity)

        payload = {
            "schema_version": 5,
            "collected_at": collected_at.isoformat(),
            "duration_ms": duration_ms,
            "is_complete": complete_sources == len(results),
            "successful_sources": successful_sources,
            "complete_sources": complete_sources,
            "total_sources": len(results),
            "source_status": source_status,
            "quotes": quote_map,
            "quote_list": quote_dicts,
            "groups": groups,
            "analysis": build_market_analysis(quotes),
            "dollar_parity": parity,
            "macro_opening": macro_opening,
            "opening_analysis": opening_analysis,
            "data_policy": (
                "Valores ausentes permanecem nulos. Não existem preços de referência, séries aleatórias, "
                "probabilidades artificiais ou substituições silenciosas. Percentuais do Investing são validados contra "
                "preço atual e fechamento anterior quando ambos existem. Os dois cálculos de abertura são direcionais, "
                "não probabilísticos; o cálculo macro é a soma explícita de VIX invertido, minério e WTI. "
                "A Paridade REAL / EUR-USD é calculada somente com EUR/BRL e EUR/USD reais da mesma coleta."
            ),
        }
        return payload
