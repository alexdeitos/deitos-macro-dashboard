from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import isfinite
from typing import Any, Mapping

import holidays


PTAX_WINDOWS = (
    ("PTAX 1", "10:00–10:10"),
    ("PTAX 2", "11:00–11:10"),
    ("PTAX 3", "12:00–12:10"),
    ("PTAX 4", "13:00–13:10"),
)


@dataclass(frozen=True)
class DollarInputs:
    future_points: float | None = None
    spot_points: float | None = None
    previous_ptax: float | None = None
    ptax1: float | None = None
    ptax2: float | None = None
    ptax3: float | None = None
    ptax4: float | None = None
    target_ptax: float | None = None
    selic_percent: float | None = None
    us_1y_percent: float | None = None
    business_days: int | None = None
    overnight_percent: float | None = None
    range_points: float = 24.0
    frp0_points: float | None = None


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _ptax_points(value: float | None) -> float | None:
    return value * 1000 if value is not None else None


def _business_days(start: date, end: date) -> int:
    if end <= start:
        return 0
    calendar = holidays.Brazil(years=range(start.year, end.year + 1))
    current = start + timedelta(days=1)
    count = 0
    while current <= end:
        if current.weekday() < 5 and current not in calendar:
            count += 1
        current += timedelta(days=1)
    return count


def _front_contract_expiry(today: date) -> date:
    """Approximation aligned with B3's first-session-day convention.

    The project already used the first Brazilian business day for its parity model.
    The calculator keeps that convention so the manual and automatic panes reconcile.
    """
    calendar = holidays.Brazil(years=[today.year, today.year + 1])
    year = today.year
    month = today.month
    candidate = date(year, month, 1)
    while candidate.weekday() >= 5 or candidate in calendar:
        candidate += timedelta(days=1)
    if today <= candidate:
        return candidate
    year = today.year + (1 if today.month == 12 else 0)
    month = 1 if today.month == 12 else today.month + 1
    candidate = date(year, month, 1)
    calendar = holidays.Brazil(years=[year])
    while candidate.weekday() >= 5 or candidate in calendar:
        candidate += timedelta(days=1)
    return candidate


def _classification(score: float | None) -> tuple[str, str]:
    if score is None:
        return "indisponível", "Dados insuficientes"
    if score >= 35:
        return "comprador forte", "Viés comprador forte"
    if score >= 15:
        return "comprador", "Viés comprador"
    if score <= -35:
        return "vendedor forte", "Viés vendedor forte"
    if score <= -15:
        return "vendedor", "Viés vendedor"
    return "neutro", "Aguardar confirmação"


def calculate_dollar_analysis(inputs: DollarInputs) -> dict[str, Any]:
    fixings = [inputs.ptax1, inputs.ptax2, inputs.ptax3, inputs.ptax4]
    known = [value for value in fixings if value is not None]
    known_sum = sum(known) if known else 0.0
    count = len(known)
    remaining = 4 - count

    neutral_projection = None
    if known:
        # Sem uma hipótese de trajetória futura, a projeção neutra é carry-forward
        # da última prévia: transparente e reproduzível, mas NÃO uma probabilidade.
        neutral_projection = known[-1]
    elif inputs.previous_ptax is not None:
        neutral_projection = inputs.previous_ptax

    required_remaining_average = None
    target = inputs.target_ptax
    if target is not None and remaining > 0:
        required_remaining_average = (target * 4 - known_sum) / remaining

    fixing_rows: list[dict[str, Any]] = []
    base_ptax = inputs.previous_ptax
    for index, value in enumerate(fixings, start=1):
        if value is None:
            fixing_rows.append({
                "index": index,
                "label": f"PTAX {index}",
                "window": PTAX_WINDOWS[index - 1][1],
                "value": None,
                "vs_previous_points": None,
                "vs_target_points": (value - target) * 1000 if value is not None and target is not None else None,
            })
            continue
        fixing_rows.append({
            "index": index,
            "label": f"PTAX {index}",
            "window": PTAX_WINDOWS[index - 1][1],
            "value": round(value, 6),
            "vs_previous_points": round((value - base_ptax) * 1000, 2) if base_ptax is not None else None,
            "vs_target_points": round((value - target) * 1000, 2) if target is not None else None,
        })
        base_ptax = value

    spot = inputs.spot_points
    future = inputs.future_points
    observed_basis = future - spot if future is not None and spot is not None else None
    fair_forward = None
    fair_basis = None
    deviation = None
    deviation_percent = None
    if spot is not None and inputs.selic_percent is not None and inputs.us_1y_percent is not None and inputs.business_days is not None:
        br_rate = inputs.selic_percent / 100.0
        us_rate = inputs.us_1y_percent / 100.0
        period = max(inputs.business_days, 0) / 252.0
        if 1 + br_rate > 0 and 1 + us_rate > 0:
            fair_forward = spot * ((1 + br_rate) ** period) / ((1 + us_rate) ** period)
            fair_basis = fair_forward - spot
            if future is not None and fair_forward:
                deviation = future - fair_forward
                deviation_percent = deviation / fair_forward * 100

    opening_proxy = None
    if future is not None and inputs.overnight_percent is not None:
        opening_proxy = future * (1 + inputs.overnight_percent / 100.0)
    elif fair_forward is not None:
        opening_proxy = fair_forward

    central = opening_proxy or future or fair_forward
    range_points = max(inputs.range_points, 0.0)
    projected_high = central + range_points if central is not None else None
    projected_low = central - range_points if central is not None else None

    ptax_vs_previous_points = None
    ptax_vs_previous_pct = None
    if neutral_projection is not None and inputs.previous_ptax is not None:
        ptax_vs_previous_points = (neutral_projection - inputs.previous_ptax) * 1000
        if inputs.previous_ptax:
            ptax_vs_previous_pct = (neutral_projection / inputs.previous_ptax - 1) * 100

    future_vs_ptax_points = None
    if future is not None and neutral_projection is not None:
        future_vs_ptax_points = future - neutral_projection * 1000

    fair_stretch_label = "indisponível"
    if deviation is not None:
        if abs(deviation_percent or 0) >= 0.35:
            fair_stretch_label = "esticado"
        elif abs(deviation_percent or 0) >= 0.15:
            fair_stretch_label = "moderado"
        else:
            fair_stretch_label = "alinhado"

    ptax_state = "indisponível"
    if future_vs_ptax_points is not None:
        if future_vs_ptax_points >= 25:
            ptax_state = "futuro acima da PTAX"
        elif future_vs_ptax_points <= -25:
            ptax_state = "futuro abaixo da PTAX"
        else:
            ptax_state = "próximo da PTAX"

    levels = []
    level_base = future or central
    if level_base is not None:
        levels = [
            {"label": "Abertura proxy", "value": opening_proxy},
            {"label": "Preço justo", "value": fair_forward},
            {"label": "PTAX base", "value": _ptax_points(neutral_projection)},
            {"label": "PTAX alvo", "value": _ptax_points(target)},
            {"label": "Faixa máxima", "value": projected_high},
            {"label": "Faixa mínima", "value": projected_low},
        ]

    return {
        "inputs": {
            "future_points": future,
            "spot_points": spot,
            "previous_ptax": inputs.previous_ptax,
            "ptax_fixings": fixings,
            "target_ptax": target,
            "selic_percent": inputs.selic_percent,
            "us_1y_percent": inputs.us_1y_percent,
            "business_days": inputs.business_days,
            "overnight_percent": inputs.overnight_percent,
            "range_points": range_points,
            "frp0_points": inputs.frp0_points,
        },
        "ptax": {
            "known_count": count,
            "remaining_count": remaining,
            "known_average": round(sum(known) / count, 6) if known else None,
            "neutral_projection": round(neutral_projection, 6) if neutral_projection is not None else None,
            "required_remaining_average": round(required_remaining_average, 6) if required_remaining_average is not None else None,
            "vs_previous_points": round(ptax_vs_previous_points, 2) if ptax_vs_previous_points is not None else None,
            "vs_previous_percent": round(ptax_vs_previous_pct, 4) if ptax_vs_previous_pct is not None else None,
            "fixings": fixing_rows,
        },
        "forward": {
            "observed_basis_points": round(observed_basis, 2) if observed_basis is not None else None,
            "fair_forward_points": round(fair_forward, 2) if fair_forward is not None else None,
            "fair_basis_points": round(fair_basis, 2) if fair_basis is not None else None,
            "future_minus_fair_points": round(deviation, 2) if deviation is not None else None,
            "future_minus_fair_percent": round(deviation_percent, 4) if deviation_percent is not None else None,
            "fair_stretch": fair_stretch_label,
            "opening_proxy_points": round(opening_proxy, 2) if opening_proxy is not None else None,
        },
        "daytrade": {
            "ptax_state": ptax_state,
            "future_minus_ptax_points": round(future_vs_ptax_points, 2) if future_vs_ptax_points is not None else None,
            "levels": [
                {row["label"]: round(row["value"], 2) if row["value"] is not None else None}
                for row in levels
            ],
            "range_points": round(range_points, 2),
            "high_points": round(projected_high, 2) if projected_high is not None else None,
            "low_points": round(projected_low, 2) if projected_low is not None else None,
        },
        "notes": [
            "A projeção neutra da PTAX apenas carrega a última prévia conhecida; não é probabilidade nem consenso.",
            "O preço justo usa diferencial composto de taxa BR e Treasury 1Y quando essas entradas existem.",
            "A abertura proxy reproduz a lógica operacional de futuro ajustado por overnight; não representa leilão oficial da B3.",
            "Máxima/mínima são uma faixa parametrizada em pontos. Ajuste o campo conforme a volatilidade observada no dia.",
        ],
    }


def build_automatic_dollar_analysis(payload: Mapping[str, Any], *, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    quotes = payload.get("quotes", {}) if isinstance(payload, Mapping) else {}
    parity = payload.get("dollar_parity", {}) if isinstance(payload, Mapping) else {}
    opening = payload.get("opening_analysis", {}) if isinstance(payload, Mapping) else {}

    def qvalue(symbol: str) -> float | None:
        item = quotes.get(symbol)
        if not isinstance(item, Mapping):
            return None
        value = _finite(item.get("value"))
        if symbol in {"USD_BRL", "PTAX_USD_BRL"}:
            return value * 1000 if value is not None else None
        return value

    def qchange(symbol: str) -> float | None:
        item = quotes.get(symbol)
        if not isinstance(item, Mapping):
            return None
        return _finite(item.get("change_percent"))

    expiry = _front_contract_expiry(today)
    business_days = parity.get("business_days") if isinstance(parity, Mapping) else None
    if business_days is None:
        business_days = _business_days(today, expiry)

    ptax_quote = quotes.get("PTAX_USD_BRL") if isinstance(quotes, Mapping) else None
    ptax_raw = ptax_quote.get("raw", {}) if isinstance(ptax_quote, Mapping) else {}
    previous_ptax = _finite(ptax_raw.get("previous_ptax_midpoint")) if isinstance(ptax_raw, Mapping) else None
    today_bulletins = ptax_raw.get("today_bulletins", []) if isinstance(ptax_raw, Mapping) else []
    ptax_fixings = []
    if isinstance(today_bulletins, list):
        by_hour = {}
        for row in today_bulletins:
            if isinstance(row, Mapping) and row.get("hour") is not None:
                mid = _finite(row.get("midpoint"))
                if mid is not None:
                    by_hour[int(row["hour"])] = mid
        ptax_fixings = [by_hour.get(hour) for hour in (10, 11, 12, 13)]

    if previous_ptax is None and not any(value is not None for value in ptax_fixings):
        current_ptax = qvalue("PTAX_USD_BRL")
        previous_ptax = current_ptax / 1000 if current_ptax is not None else None

    inputs = DollarInputs(
        future_points=qvalue("DOL_FUT"),
        spot_points=qvalue("USD_BRL"),
        previous_ptax=previous_ptax,
        ptax1=ptax_fixings[0] if len(ptax_fixings) > 0 else None,
        ptax2=ptax_fixings[1] if len(ptax_fixings) > 1 else None,
        ptax3=ptax_fixings[2] if len(ptax_fixings) > 2 else None,
        ptax4=ptax_fixings[3] if len(ptax_fixings) > 3 else None,
        target_ptax=(qvalue("DOL_FUT") / 1000 if qvalue("DOL_FUT") is not None else None),
        selic_percent=_finite(parity.get("selic_252_percent")) if isinstance(parity, Mapping) else None,
        us_1y_percent=_finite(parity.get("us_1y_yield_percent")) if isinstance(parity, Mapping) else None,
        business_days=int(business_days) if business_days is not None else None,
        overnight_percent=None,
        range_points=24.0,
    )
    result = calculate_dollar_analysis(inputs)

    wdo_score = None
    wdo_bias = None
    wdo_confidence = None
    if isinstance(opening, Mapping):
        wdo = opening.get("wdo")
        if isinstance(wdo, Mapping):
            wdo_score = _finite(wdo.get("score"))
            wdo_bias = wdo.get("bias")
            confidence = wdo.get("confidence")
            if isinstance(confidence, Mapping):
                wdo_confidence = confidence

    macro_score = None
    macro_bias = None
    macro = payload.get("macro_opening", {}) if isinstance(payload, Mapping) else {}
    if isinstance(macro, Mapping):
        macro_score = _finite(macro.get("score"))
        macro_bias = macro.get("opening_bias")

    bullish: list[str] = []
    bearish: list[str] = []
    caution: list[str] = []

    dxy = qchange("DXY")
    vix = qchange("VIX")
    ewz = qchange("EWZ")
    dji = qchange("DJI")
    if dxy is not None:
        (bullish if dxy > 0 else bearish).append(f"DXY {dxy:+.2f}% favorece dólar" if dxy > 0 else f"DXY {dxy:+.2f}% reduz pressão compradora no dólar")
    if ewz is not None:
        (bearish if ewz > 0 else bullish).append(f"EWZ {ewz:+.2f}%" + (" favorece real" if ewz > 0 else " pressiona real"))
    if vix is not None:
        (bullish if vix > 0 else bearish).append(f"VIX {vix:+.2f}%" + (" aumenta aversão ao risco" if vix > 0 else " reduz aversão ao risco"))
    if dji is not None:
        (bearish if dji > 0 else bullish).append(f"Dow Jones {dji:+.2f}%" + (" favorece risco" if dji > 0 else " reduz apetite a risco"))

    deviation_points = result["forward"]["future_minus_fair_points"]
    if deviation_points is not None:
        if deviation_points > 25:
            caution.append("WDO está acima do justo teórico: evitar perseguir compra sem confirmação de fluxo.")
        elif deviation_points < -25:
            caution.append("WDO está abaixo do justo teórico: venda exige confirmação; há espaço para correção de prêmio/desconto.")
        else:
            caution.append("WDO está próximo do justo teórico: priorizar o contexto de fluxo e níveis de abertura.")

    if result["ptax"]["vs_previous_points"] is not None:
        ptax_move = result["ptax"]["vs_previous_points"]
        caution.append(f"PTAX neutra está {abs(ptax_move):.1f} pontos {'acima' if ptax_move > 0 else 'abaixo'} da referência anterior.")

    return {
        "automatic": result,
        "market": {
            "future_points": qvalue("DOL_FUT"),
            "spot_points": qvalue("USD_BRL"),
            "ptax_points": qvalue("PTAX_USD_BRL"),
            "ptax_previous": previous_ptax,
            "ptax_fixings": ptax_fixings,
            "dxy_percent": dxy,
            "vix_percent": vix,
            "ewz_percent": ewz,
            "dow_percent": dji,
            "wdo_score": wdo_score,
            "wdo_bias": wdo_bias,
            "wdo_confidence": wdo_confidence,
            "macro_score": macro_score,
            "macro_bias": macro_bias,
            "collected_at": payload.get("collected_at"),
        },
        "insights": {
            "bullish": bullish,
            "bearish": bearish,
            "caution": caution,
        },
        "decision_framework": [
            "1) Comece pelo preço justo e pela PTAX; 2) valide com DXY/VIX/EWZ e o score WDO; 3) use o preço/volume/VWAP para disparar a entrada; 4) invalide quando a estrutura contrariar o contexto.",
            "Prêmio/desconto do WDO é contexto, não gatilho isolado. Uma divergência pode permanecer enquanto o fluxo dominante continuar.",
            "Em torno das janelas da PTAX, trate acelerações como possível fluxo de fixing e espere confirmação antes de interpretar como nova tendência.",
        ],
        "sources": {
            "ptax_methodology": "Banco Central do Brasil — Resolução BCB nº 45/2020",
            "future_methodology": "B3 — Manual de Apreçamento de Contratos Futuros",
            "wdo_contract": "B3 — Contrato Futuro Mini de Taxa de Câmbio de Reais por Dólar Comercial",
        },
        "schema_version": 1,
        "expiry_date": expiry.isoformat(),
    }
