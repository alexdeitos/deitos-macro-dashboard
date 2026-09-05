from __future__ import annotations

from statistics import mean
from typing import Any

from .types import Quote


# Modelo multifatorial específico para o índice brasileiro.
# O Dow Jones é o maior driver acionário americano; S&P permanece como confirmação.
# Os pesos são transparentes e somam 100%. Não há preenchimento de dados ausentes.
INDEX_FACTORS: tuple[tuple[str, str, float, int], ...] = (
    ("DJI", "Dow Jones — driver principal", 0.25, 1),
    ("SP500", "S&P 500 — confirmação", 0.12, 1),
    ("NASDAQ", "Nasdaq", 0.05, 1),
    ("EEM", "Emergentes (EEM)", 0.08, 1),
    ("EWZ", "EWZ", 0.15, 1),
    ("VIX", "VIX invertido", 0.10, -1),
    ("DXY", "DXY invertido", 0.08, -1),
    ("IRON_ORE", "Minério de ferro", 0.08, 1),
    ("BRENT", "Brent", 0.04, 1),
)

ADR_WEIGHT = 0.05


def _latest_map(quotes: list[Quote]) -> dict[str, Quote]:
    result: dict[str, Quote] = {}
    for quote in quotes:
        current = result.get(quote.symbol)
        if current is None or quote.observed_at >= current.observed_at:
            result[quote.symbol] = quote
    return result


def _classify(expected_percent: float | None, deviation_points: float | None) -> tuple[str, str]:
    if expected_percent is None:
        return "dados insuficientes", "Aguardar cobertura mínima dos fatores do modelo."

    if abs(expected_percent) < 0.15:
        bias = "abertura neutra/lateral"
    elif expected_percent > 0:
        bias = "abertura potencialmente positiva"
    else:
        bias = "abertura potencialmente negativa"

    if deviation_points is not None and abs(deviation_points) >= 250:
        if deviation_points > 0:
            bias += " · WIN acima do fair value"
        else:
            bias += " · WIN abaixo do fair value"

    if abs(expected_percent) >= 0.80:
        strength = "forte"
    elif abs(expected_percent) >= 0.40:
        strength = "moderada"
    elif abs(expected_percent) >= 0.15:
        strength = "fraca"
    else:
        strength = "lateral"

    return bias, strength


def build_index_opening_analysis(quotes: list[Quote]) -> dict[str, Any]:
    """Estima a abertura do índice futuro a partir do conjunto de fatores overnight.

    A base é o fechamento anterior do IBOV futuro quando disponível. O retorno
    estimado é a soma ponderada das variações percentuais realmente observadas.
    Dados ausentes reduzem a cobertura e não são substituídos.

    Esta é uma camada analítica transparente, não uma regressão histórica
    calibrada nem uma probabilidade de acerto.
    """
    quote_map = _latest_map(quotes)
    ibov = quote_map.get("IBOV")

    base_points = None
    base_source = None
    observed_points = None
    if ibov is not None:
        observed_points = ibov.value
        if ibov.previous_close not in (None, 0):
            base_points = float(ibov.previous_close)
            base_source = "fechamento anterior do IBOV futuro"
        elif ibov.value not in (None, 0):
            base_points = float(ibov.value)
            base_source = "última cotação do IBOV futuro (fallback operacional)"

    components: list[dict[str, Any]] = []
    missing: list[str] = []
    weighted_return = 0.0
    available_weight = 0.0

    for symbol, label, weight, orientation in INDEX_FACTORS:
        quote = quote_map.get(symbol)
        if quote is None or quote.change_percent is None:
            missing.append(label)
            continue

        raw = float(quote.change_percent)
        adjusted = raw * orientation
        weighted = adjusted * weight
        weighted_return += weighted
        available_weight += weight

        components.append(
            {
                "symbol": symbol,
                "label": label,
                "raw_change_percent": round(raw, 4),
                "orientation": orientation,
                "weight": round(weight, 4),
                "weighted_contribution_percent": round(weighted, 4),
                "source": quote.source,
                "observed_at": quote.observed_at.isoformat(),
            }
        )

    # ADRs brasileiras: média das ADRs efetivamente coletadas.
    adr_values = [
        float(q.change_percent)
        for q in quotes
        if q.category == "adr" and q.change_percent is not None
    ]
    if adr_values:
        adr_mean = mean(adr_values)
        weighted = adr_mean * ADR_WEIGHT
        weighted_return += weighted
        available_weight += ADR_WEIGHT
        components.append(
            {
                "symbol": "ADRS",
                "label": "ADRs brasileiras — média",
                "raw_change_percent": round(adr_mean, 4),
                "orientation": 1,
                "weight": ADR_WEIGHT,
                "weighted_contribution_percent": round(weighted, 4),
                "source": "investing",
                "sample_size": len(adr_values),
            }
        )
    else:
        missing.append("ADRs brasileiras")

    expected_percent = None
    fair_value = None
    opening_estimate = None
    deviation_points = None
    if available_weight > 0:
        # Renormaliza apenas entre fatores reais disponíveis.
        expected_percent = weighted_return / available_weight
        if base_points is not None:
            fair_value = base_points * (1.0 + expected_percent / 100.0)
            opening_estimate = fair_value
            if observed_points is not None:
                deviation_points = observed_points - fair_value

    bias, strength = _classify(expected_percent, deviation_points)

    directional_values = [
        item["weighted_contribution_percent"]
        for item in components
        if item["weighted_contribution_percent"] != 0
    ]
    positive = sum(v for v in directional_values if v > 0)
    negative = sum(abs(v) for v in directional_values if v < 0)
    agreement = (
        max(positive, negative) / (positive + negative) * 100
        if positive + negative
        else None
    )
    coverage = available_weight * 100.0
    if coverage >= 80 and agreement is not None and agreement >= 65:
        confidence_label = "alta"
    elif coverage >= 60 and agreement is not None and agreement >= 55:
        confidence_label = "moderada"
    elif coverage >= 35:
        confidence_label = "baixa"
    else:
        confidence_label = "insuficiente"

    return {
        "base_points": round(base_points, 2) if base_points is not None else None,
        "base_source": base_source,
        "observed_points": round(observed_points, 2) if observed_points is not None else None,
        "expected_change_percent": round(expected_percent, 4) if expected_percent is not None else None,
        "fair_value_points": round(fair_value, 2) if fair_value is not None else None,
        "opening_estimate_points": round(opening_estimate, 2) if opening_estimate is not None else None,
        "deviation_points": round(deviation_points, 2) if deviation_points is not None else None,
        "deviation_percent": (
            round((deviation_points / fair_value) * 100, 4)
            if deviation_points is not None and fair_value not in (None, 0)
            else None
        ),
        "bias": bias,
        "strength": strength,
        "confidence": {
            "label": confidence_label,
            "coverage_percent": round(min(100.0, coverage), 1),
            "agreement_percent": round(agreement, 1) if agreement is not None else None,
            "sample_size": len(components),
        },
        "components": components,
        "missing_components": missing,
        "weights": {
            "Dow Jones": 0.25,
            "S&P 500": 0.12,
            "Nasdaq": 0.05,
            "EEM": 0.08,
            "EWZ": 0.15,
            "VIX": 0.10,
            "DXY": 0.08,
            "Minério": 0.08,
            "Brent": 0.04,
            "ADRs brasileiras": ADR_WEIGHT,
        },
        "methodology": (
            "Retorno esperado = média ponderada dos fatores overnight realmente disponíveis. "
            "Dow Jones é o maior driver americano; S&P 500 é confirmação. "
            "A base do preço é o fechamento anterior do IBOV futuro. "
            "O fair value é uma estimativa multifatorial e não uma previsão estatística calibrada."
        ),
        "disclaimer": (
            "Modelo analítico de abertura. Não é probabilidade de acerto, não garante a abertura "
            "e não deve ser usado isoladamente para entrada. Confirmar preço, volume, VWAP e estrutura "
            "nos primeiros minutos do pregão."
        ),
    }
