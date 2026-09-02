from __future__ import annotations

from statistics import mean
from typing import Any

from .types import Quote


def _latest_map(quotes: list[Quote]) -> dict[str, Quote]:
    result: dict[str, Quote] = {}
    for quote in quotes:
        current = result.get(quote.symbol)
        if current is None or quote.observed_at >= current.observed_at:
            result[quote.symbol] = quote
    return result


def _clip(value: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _signal(change: float, *, scale: float, orientation: int = 1) -> float:
    return _clip(change / scale) * orientation


def _label(score: float | None) -> str:
    if score is None:
        return "dados insuficientes"
    if score >= 35:
        return "viés comprador forte"
    if score >= 15:
        return "viés comprador"
    if score <= -35:
        return "viés vendedor forte"
    if score <= -15:
        return "viés vendedor"
    return "aguardar confirmação"


def _action(market: str, score: float | None, readiness: str) -> str:
    if score is None or readiness == "insuficiente":
        return "Não operar na abertura apenas com o painel; faltam sinais suficientes."
    if abs(score) < 15:
        return "Aguardar 5–15 minutos e operar somente após rompimento com confirmação de fluxo/VWAP."
    side = "compra" if score > 0 else "venda"
    invalidation = "perda" if score > 0 else "recuperação"
    reference = "máxima" if score > 0 else "mínima"
    return (
        f"Preferência condicional por {side}, sem entrada a mercado. Aguardar confirmação no preço, "
        f"rompimento da {reference} inicial e invalidar na {invalidation} da VWAP/estrutura de abertura."
    )


def _confidence(components: list[dict[str, Any]]) -> dict[str, Any]:
    if not components:
        return {"label": "insuficiente", "coverage_percent": 0.0, "agreement_percent": None, "sample_size": 0}
    available_weight = sum(item["weight"] for item in components)
    coverage = min(100.0, available_weight * 100.0)
    weighted_positive = sum(item["weight"] for item in components if item["contribution"] > 0)
    weighted_negative = sum(item["weight"] for item in components if item["contribution"] < 0)
    directional = weighted_positive + weighted_negative
    agreement = None if directional == 0 else max(weighted_positive, weighted_negative) / directional * 100
    if coverage >= 75 and agreement is not None and agreement >= 70:
        label = "alta"
    elif coverage >= 55 and agreement is not None and agreement >= 58:
        label = "moderada"
    elif coverage >= 35:
        label = "baixa"
    else:
        label = "insuficiente"
    return {
        "label": label,
        "coverage_percent": round(coverage, 1),
        "agreement_percent": round(agreement, 1) if agreement is not None else None,
        "sample_size": len(components),
    }


def _build_side(
    quote_map: dict[str, Quote],
    definitions: list[tuple[str, float, float, int, str]],
    extra_components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    components: list[dict[str, Any]] = []
    for symbol, weight, scale, orientation, label in definitions:
        quote = quote_map.get(symbol)
        if quote is None or quote.change_percent is None:
            continue
        normalized = _signal(quote.change_percent, scale=scale, orientation=orientation)
        components.append({
            "symbol": symbol,
            "label": label,
            "raw_change_percent": round(quote.change_percent, 4),
            "orientation": orientation,
            "normalized_signal": round(normalized, 4),
            "weight": weight,
            "contribution": round(normalized * weight * 100, 3),
            "source": quote.source,
        })
    components.extend(extra_components or [])
    total_weight = sum(item["weight"] for item in components)
    score = None
    if total_weight > 0:
        score = sum(item["normalized_signal"] * item["weight"] for item in components) / total_weight * 100
    confidence = _confidence(components)
    return {
        "score": round(score, 1) if score is not None else None,
        "bias": _label(score),
        "confidence": confidence,
        "components": components,
    }


def build_opening_analysis(quotes: list[Quote], parity: dict[str, Any]) -> dict[str, Any]:
    quote_map = _latest_map(quotes)
    adr_changes = [
        quote.change_percent for quote in quotes
        if quote.category == "adr" and quote.change_percent is not None and quote.value not in (None, 0)
    ]
    adr_mean = mean(adr_changes) if adr_changes else None

    win_extra: list[dict[str, Any]] = []
    wdo_extra: list[dict[str, Any]] = []
    if adr_mean is not None:
        normalized = _signal(adr_mean, scale=3.0)
        win_extra.append({
            "symbol": "ADRS",
            "label": "ADRs brasileiras",
            "raw_change_percent": round(adr_mean, 4),
            "orientation": 1,
            "normalized_signal": round(normalized, 4),
            "weight": 0.18,
            "contribution": round(normalized * 0.18 * 100, 3),
            "source": "investing",
            "sample_size": len(adr_changes),
        })
        wdo_extra.append({
            "symbol": "ADRS",
            "label": "ADRs brasileiras (inverso para dólar)",
            "raw_change_percent": round(adr_mean, 4),
            "orientation": -1,
            "normalized_signal": round(-normalized, 4),
            "weight": 0.12,
            "contribution": round(-normalized * 0.12 * 100, 3),
            "source": "investing",
            "sample_size": len(adr_changes),
        })

    win = _build_side(quote_map, [
        ("EWZ", 0.20, 3.0, 1, "EWZ"),
        ("IBOV", 0.10, 3.0, 1, "Ibovespa/última sessão"),
        # Entre as bolsas dos EUA, o Dow Jones recebe a maior ponderação.
        # O S&P 500 permanece como confirmação secundária, não como driver principal.
        ("DJI", 0.16, 1.5, 1, "Dow Jones"),
        ("SP500", 0.06, 1.5, 1, "S&P 500 (confirmação)"),
        ("NASDAQ", 0.05, 2.0, 1, "Nasdaq"),
        ("EEM", 0.09, 1.5, 1, "Emergentes (EEM)"),
        ("DXY", 0.08, 0.8, -1, "DXY"),
        ("VIX", 0.07, 10.0, -1, "VIX"),
        ("IRON_ORE", 0.06, 2.0, 1, "Minério de ferro"),
        ("BRENT", 0.04, 4.0, 1, "Petróleo Brent"),
    ], win_extra)

    wdo = _build_side(quote_map, [
        ("DXY", 0.24, 0.8, 1, "DXY"),
        ("VIX", 0.13, 10.0, 1, "VIX"),
        ("EEM", 0.10, 1.5, -1, "Emergentes (EEM)"),
        ("EWZ", 0.14, 3.0, -1, "EWZ"),
        ("DJI", 0.06, 1.5, -1, "Dow Jones"),
        ("SP500", 0.03, 1.5, -1, "S&P 500 (confirmação)"),
        ("NASDAQ", 0.04, 2.0, -1, "Nasdaq"),
        ("IRON_ORE", 0.04, 2.0, -1, "Minério de ferro"),
        ("BRENT", 0.03, 4.0, -1, "Petróleo Brent"),
    ], wdo_extra)

    deviation = parity.get("future_minus_theoretical_percent")
    parity_signal = None
    if isinstance(deviation, (int, float)):
        parity_signal = _clip(deviation / 0.35)
        wdo["components"].append({
            "symbol": "PARITY",
            "label": "Futuro versus paridade teórica",
            "raw_change_percent": round(deviation, 4),
            "orientation": 1,
            "normalized_signal": round(parity_signal, 4),
            "weight": 0.10,
            "contribution": round(parity_signal * 10, 3),
            "source": "cálculo com dados reais",
        })
        total_weight = sum(item["weight"] for item in wdo["components"])
        score = sum(item["normalized_signal"] * item["weight"] for item in wdo["components"]) / total_weight * 100
        wdo["score"] = round(score, 1)
        wdo["bias"] = _label(score)
        wdo["confidence"] = _confidence(wdo["components"])

    win["action_plan"] = _action("WIN", win["score"], win["confidence"]["label"])
    wdo["action_plan"] = _action("WDO", wdo["score"], wdo["confidence"]["label"])

    return {
        "win": win,
        "wdo": wdo,
        "disclaimer": (
            "O score é um índice direcional determinístico de -100 a +100, não uma probabilidade estatística. "
            "Ele usa somente dados disponíveis no snapshot e deve ser confirmado pelo preço, volume e VWAP após a abertura."
        ),
        "methodology": {
            "score_range": [-100, 100],
            "buy_threshold": 15,
            "strong_buy_threshold": 35,
            "sell_threshold": -15,
            "strong_sell_threshold": -35,
            "normalization": "Cada variação é limitada por uma escala própria antes da ponderação, evitando que o VIX domine a média.",
        },
    }
