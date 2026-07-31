from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import holidays

from .types import Quote


def _latest(quotes: list[Quote], symbol: str) -> Quote | None:
    candidates = [quote for quote in quotes if quote.symbol == symbol]
    return max(candidates, key=lambda quote: quote.observed_at) if candidates else None


def _first_business_day(year: int, month: int) -> date:
    calendar = holidays.Brazil(years=[year])
    current = date(year, month, 1)
    while current.weekday() >= 5 or current in calendar:
        current += timedelta(days=1)
    return current


def _front_contract_expiry(today: date) -> date:
    expiry = _first_business_day(today.year, today.month)
    if today > expiry:
        year = today.year + (1 if today.month == 12 else 0)
        month = 1 if today.month == 12 else today.month + 1
        expiry = _first_business_day(year, month)
    return expiry


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


def build_dollar_parity(quotes: list[Quote], *, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    spot_quote = _latest(quotes, "USD_BRL")
    future_quote = _latest(quotes, "DOL_FUT")
    selic_quote = _latest(quotes, "SELIC_252")
    us_rate_quote = _latest(quotes, "US_1Y_YIELD")
    ptax_quote = _latest(quotes, "PTAX_USD_BRL")

    spot_points = spot_quote.value * 1000 if spot_quote and spot_quote.value is not None else None
    future_points = future_quote.value if future_quote and future_quote.value is not None else None
    if future_points is not None and future_points < 100:
        future_points *= 1000

    expiry = _front_contract_expiry(today)
    business_days = _business_days(today, expiry)
    observed_basis = (
        future_points - spot_points
        if future_points is not None and spot_points is not None
        else None
    )

    missing_for_theoretical = []
    if spot_points is None:
        missing_for_theoretical.append("USD_BRL")
    if selic_quote is None or selic_quote.value is None:
        missing_for_theoretical.append("SELIC_252")
    if us_rate_quote is None or us_rate_quote.value is None:
        missing_for_theoretical.append("US_1Y_YIELD")

    theoretical_future = None
    theoretical_basis = None
    deviation_points = None
    deviation_percent = None
    if not missing_for_theoretical:
        br_rate = selic_quote.value / 100
        us_rate = us_rate_quote.value / 100
        period = business_days / 252
        theoretical_future = spot_points * ((1 + br_rate) ** period) / ((1 + us_rate) ** period)
        theoretical_basis = theoretical_future - spot_points
        if future_points is not None:
            deviation_points = future_points - theoretical_future
            deviation_percent = (deviation_points / theoretical_future) * 100

    return {
        "spot_points": round(spot_points, 4) if spot_points is not None else None,
        "future_points": round(future_points, 4) if future_points is not None else None,
        "ptax": round(ptax_quote.value, 6) if ptax_quote and ptax_quote.value is not None else None,
        "selic_252_percent": round(selic_quote.value, 6) if selic_quote and selic_quote.value is not None else None,
        "us_1y_yield_percent": round(us_rate_quote.value, 6) if us_rate_quote and us_rate_quote.value is not None else None,
        "expiry_date": expiry.isoformat(),
        "business_days": business_days,
        "observed_basis_points": round(observed_basis, 4) if observed_basis is not None else None,
        "theoretical_future_points": round(theoretical_future, 4) if theoretical_future is not None else None,
        "theoretical_basis_points": round(theoretical_basis, 4) if theoretical_basis is not None else None,
        "future_minus_theoretical_points": round(deviation_points, 4) if deviation_points is not None else None,
        "future_minus_theoretical_percent": round(deviation_percent, 6) if deviation_percent is not None else None,
        "theoretical_available": not missing_for_theoretical,
        "missing_for_theoretical": missing_for_theoretical,
        "methodology": (
            "Paridade teórica por diferencial composto entre Selic anualizada base 252 e Treasury de 1 ano, "
            "usando os dias úteis até o primeiro dia útil do mês de vencimento. O resultado só é calculado "
            "quando todas as entradas reais estão disponíveis."
        ),
        "calendar_note": "Calendário de feriados nacionais do Brasil; feriados específicos da B3 podem exigir ajuste manual.",
        "sources": {
            "spot": spot_quote.source if spot_quote else None,
            "future": future_quote.source if future_quote else None,
            "selic": selic_quote.source if selic_quote else None,
            "us_rate": us_rate_quote.source if us_rate_quote else None,
            "ptax": ptax_quote.source if ptax_quote else None,
        },
    }
