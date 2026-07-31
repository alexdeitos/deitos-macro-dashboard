from __future__ import annotations

from typing import Any

from .types import Quote


MACRO_COMPONENTS: tuple[tuple[str, str, int], ...] = (
    ("VIX", "VIX invertido", -1),
    ("IRON_ORE", "Minério de ferro (FEF)", 1),
    ("WTI", "Petróleo WTI (CL1)", 1),
)

OVERNIGHT_CONTEXT: tuple[tuple[str, str], ...] = (
    ("SP500", "S&P 500"),
    ("DJI", "Dow Jones"),
    ("NASDAQ", "Nasdaq"),
    ("DXY", "DXY"),
    ("EWZ", "EWZ"),
)


def _latest_map(quotes: list[Quote]) -> dict[str, Quote]:
    latest: dict[str, Quote] = {}
    for quote in quotes:
        current = latest.get(quote.symbol)
        if current is None or quote.observed_at >= current.observed_at:
            latest[quote.symbol] = quote
    return latest


def _classification(score: float | None) -> dict[str, str]:
    if score is None:
        return {
            "direction": "indisponível",
            "opening_bias": "dados insuficientes",
            "strength": "indisponível",
            "strategy": (
                "Não utilizar este cálculo até VIX, minério e petróleo WTI estarem disponíveis."
            ),
        }

    magnitude = abs(score)
    if magnitude < 1.5:
        return {
            "direction": "lateral",
            "opening_bias": "abertura lateral",
            "strength": "lateral",
            "strategy": (
                "Priorizar extremos da faixa inicial: compra em suporte e venda em resistência, "
                "sempre com confirmação de fluxo e alvos curtos."
            ),
        }

    if magnitude <= 2.5:
        strength = "fraca"
    elif magnitude <= 4.5:
        strength = "moderada"
    else:
        strength = "forte"

    if score > 0:
        return {
            "direction": "positiva",
            "opening_bias": "abertura compradora",
            "strength": strength,
            "strategy": (
                "Buscar regiões de suporte abaixo da abertura e confirmar compra por preço, volume e VWAP."
            ),
        }

    return {
        "direction": "negativa",
        "opening_bias": "abertura vendedora",
        "strength": strength,
        "strategy": (
            "Buscar regiões de resistência acima da abertura e confirmar venda por preço, volume e VWAP."
        ),
    }


def build_macro_opening_analysis(quotes: list[Quote]) -> dict[str, Any]:
    """Calcula o modelo visual VIX invertido + FEF + CL1.

    O resultado é a soma direta das variações percentuais observadas:

        (- VIX) + minério de ferro + petróleo WTI

    Não existe normalização, peso oculto, probabilidade ou valor substituto.
    A pontuação só é calculada quando os três componentes estão disponíveis.
    """

    quote_map = _latest_map(quotes)
    components: list[dict[str, Any]] = []
    missing: list[str] = []

    for symbol, label, orientation in MACRO_COMPONENTS:
        quote = quote_map.get(symbol)
        if quote is None or quote.change_percent is None:
            missing.append(label)
            continue

        contribution = float(quote.change_percent) * orientation
        components.append(
            {
                "symbol": symbol,
                "label": label,
                "raw_change_percent": round(float(quote.change_percent), 4),
                "orientation": orientation,
                "contribution": round(contribution, 4),
                "source": quote.source,
                "observed_at": quote.observed_at.isoformat(),
            }
        )

    score = None
    if not missing and len(components) == len(MACRO_COMPONENTS):
        score = round(sum(item["contribution"] for item in components), 2)

    classification = _classification(score)

    context: list[dict[str, Any]] = []
    for symbol, label in OVERNIGHT_CONTEXT:
        quote = quote_map.get(symbol)
        context.append(
            {
                "symbol": symbol,
                "label": label,
                "change_percent": (
                    round(float(quote.change_percent), 4)
                    if quote is not None and quote.change_percent is not None
                    else None
                ),
                "source": quote.source if quote is not None else None,
                "observed_at": quote.observed_at.isoformat() if quote is not None else None,
            }
        )

    return {
        "score": score,
        **classification,
        "components": components,
        "missing_components": missing,
        "context": context,
        "formula": "(- VIX) + minério de ferro (FEF) + petróleo WTI (CL1)",
        "bands": [
            {"minimum": 0.0, "maximum": 1.5, "label": "lateral", "maximum_inclusive": False},
            {"minimum": 1.5, "maximum": 2.5, "label": "fraca", "maximum_inclusive": True},
            {"minimum": 2.5, "maximum": 4.5, "label": "moderada", "maximum_inclusive": True},
            {"minimum": 4.5, "maximum": None, "label": "forte", "minimum_exclusive": True},
        ],
        "disclaimer": (
            "Soma determinística das variações reais de VIX invertido, minério e WTI. "
            "Não é probabilidade de acerto e não substitui confirmação por preço, fluxo, volume e VWAP."
        ),
        "economic_calendar": {
            "included_in_score": False,
            "status": "not_configured",
            "message": (
                "Calendário visual disponível na lateral; os eventos não entram automaticamente no score e nenhuma notícia é presumida."
            ),
        },
    }
