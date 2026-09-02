from __future__ import annotations

from statistics import mean
from typing import Any

from .types import Quote

DEADBAND_PERCENT = 0.10


def _quote_map(quotes: list[Quote]) -> dict[str, Quote]:
    result: dict[str, Quote] = {}
    for quote in quotes:
        current = result.get(quote.symbol)
        if current is None or quote.observed_at >= current.observed_at:
            result[quote.symbol] = quote
    return result


def _direction(value: float | None) -> str:
    if value is None:
        return "indisponível"
    if value > DEADBAND_PERCENT:
        return "otimista"
    if value < -DEADBAND_PERCENT:
        return "pessimista"
    return "neutro"


def _confidence(values: list[float], composite: float) -> dict[str, Any]:
    if not values:
        return {"label": "indisponível", "agreement_percent": None, "sample_size": 0}
    if abs(composite) <= DEADBAND_PERCENT:
        agreeing = sum(abs(value) <= DEADBAND_PERCENT for value in values)
    else:
        expected_positive = composite > 0
        agreeing = sum((value > 0) == expected_positive for value in values if value != 0)
    agreement = (agreeing / len(values)) * 100
    if len(values) >= 6 and agreement >= 70:
        label = "alta"
    elif len(values) >= 4 and agreement >= 55:
        label = "moderada"
    else:
        label = "baixa"
    return {"label": label, "agreement_percent": round(agreement, 1), "sample_size": len(values)}


def build_market_analysis(quotes: list[Quote]) -> dict[str, Any]:
    quote_by_symbol = _quote_map(quotes)

    # Contexto global: Dow Jones passa a ser o principal índice acionário
    # americano; S&P 500 permanece como confirmação secundária.
    global_definitions = [
        ("DJI", 1, "Dow Jones (principal)", 0.30),
        ("SP500", 1, "S&P 500 (secundário)", 0.15),
        ("NASDAQ", 1, "Nasdaq", 0.15),
        ("EEM", 1, "Emergentes (EEM)", 0.15),
        ("DXY", -1, "DXY invertido", 0.125),
        ("VIX", -1, "VIX invertido", 0.125),
    ]
    global_components: list[dict[str, Any]] = []
    global_values: list[float] = []
    weighted_sum = 0.0
    available_weight = 0.0
    for symbol, orientation, label, weight in global_definitions:
        quote = quote_by_symbol.get(symbol)
        if quote is None or quote.change_percent is None:
            continue
        adjusted = quote.change_percent * orientation
        global_values.append(adjusted)
        weighted_sum += adjusted * weight
        available_weight += weight
        global_components.append(
            {
                "symbol": symbol,
                "label": label,
                "raw_change_percent": quote.change_percent,
                "orientation": orientation,
                "weight": weight,
                "adjusted_change_percent": adjusted,
                "weighted_contribution": adjusted * weight,
                "source": quote.source,
            }
        )

    global_composite = (weighted_sum / available_weight) if available_weight else None

    adr_changes = [
        quote.change_percent
        for quote in quotes
        if quote.category == "adr" and quote.change_percent is not None
    ]
    adr_equal_weight = mean(adr_changes) if adr_changes else None

    brazil_definitions = [
        ("IBOV", 1, "Ibovespa"),
        ("EWZ", 1, "EWZ"),
        ("IRON_ORE", 1, "Minério de ferro"),
        ("BRENT", 1, "Petróleo Brent"),
        ("DXY", -1, "DXY invertido"),
    ]
    brazil_components: list[dict[str, Any]] = []
    brazil_values: list[float] = []
    for symbol, orientation, label in brazil_definitions:
        quote = quote_by_symbol.get(symbol)
        if quote is None or quote.change_percent is None:
            continue
        adjusted = quote.change_percent * orientation
        brazil_values.append(adjusted)
        brazil_components.append(
            {
                "symbol": symbol,
                "label": label,
                "raw_change_percent": quote.change_percent,
                "orientation": orientation,
                "adjusted_change_percent": adjusted,
                "source": quote.source,
            }
        )
    if adr_equal_weight is not None:
        brazil_values.append(adr_equal_weight)
        brazil_components.append(
            {
                "symbol": "ADRS_EQUAL_WEIGHT",
                "label": "ADRs brasileiras (média simples)",
                "raw_change_percent": adr_equal_weight,
                "orientation": 1,
                "adjusted_change_percent": adr_equal_weight,
                "source": "investing",
                "sample_size": len(adr_changes),
            }
        )

    brazil_composite = mean(brazil_values) if brazil_values else None

    return {
        "global": {
            "composite_change_percent": round(global_composite, 4) if global_composite is not None else None,
            "direction": _direction(global_composite),
            "confidence": _confidence(global_values, global_composite or 0.0),
            "components": global_components,
        },
        "brazil": {
            "composite_change_percent": round(brazil_composite, 4) if brazil_composite is not None else None,
            "direction": _direction(brazil_composite),
            "confidence": _confidence(brazil_values, brazil_composite or 0.0),
            "components": brazil_components,
            "adr_equal_weight_change_percent": round(adr_equal_weight, 4) if adr_equal_weight is not None else None,
            "adr_sample_size": len(adr_changes),
        },
        "methodology": {
            "description": (
                "Média simples apenas dos sinais realmente disponíveis. DXY e VIX entram com sinal invertido. "
                "Nenhum dado ausente é substituído por valor de referência."
            ),
            "deadband_percent": DEADBAND_PERCENT,
        },
    }
