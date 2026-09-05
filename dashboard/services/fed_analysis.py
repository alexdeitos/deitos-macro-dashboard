from __future__ import annotations

import logging
import math
import os
from datetime import date, timedelta
from typing import Any

import requests
from django.core.cache import cache

logger = logging.getLogger(__name__)

FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
CACHE_KEY = "macro-dashboard:fed-analysis:v1"
CACHE_TTL = int(os.getenv("FRED_CACHE_TTL", "900"))
HISTORY_YEARS = int(os.getenv("FRED_HISTORY_YEARS", "3"))

# Séries do grafico.py original + extensões úteis para a leitura do Fed.
SERIES = {
    "DGS10": {"label": "Treasury 10Y", "unit": "%", "group": "rates"},
    "DGS2": {"label": "Treasury 2Y", "unit": "%", "group": "rates"},
    "DFF": {"label": "Fed Funds", "unit": "%", "group": "rates"},
    "T10YIE": {"label": "Breakeven 10Y", "unit": "%", "group": "inflation"},
    "UNRATE": {"label": "Desemprego", "unit": "%", "group": "labor"},
    "PAYEMS": {"label": "Payrolls", "unit": "milhões", "group": "labor", "scale": 0.001},
    "CPIAUCSL": {"label": "CPI", "unit": "índice", "group": "inflation"},
    "PCEPI": {"label": "PCE", "unit": "índice", "group": "inflation"},
    "WTISPLC": {"label": "WTI", "unit": "USD/barril", "group": "cross"},
    "DEXUSEU": {"label": "EUR/USD", "unit": "EUR/USD", "group": "cross"},
    "GFDEBTN": {"label": "Dívida federal", "unit": "USD", "group": "fiscal", "scale": 1e-12},
    "WALCL": {"label": "Ativos do Fed", "unit": "USD", "group": "fed_balance", "scale": 1e-12},
    "RRPONTSYD": {"label": "ON RRP", "unit": "USD", "group": "fed_balance", "scale": 1e-12},
}


def _number(value: Any) -> float | None:
    try:
        if value in (None, "", "."):
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _fetch_series(series_id: str, start: date, end: date, api_key: str) -> list[dict[str, Any]]:
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "observation_start": start.isoformat(),
        "observation_end": end.isoformat(),
        "sort_order": "asc",
        "limit": 100000,
    }
    response = requests.get(FRED_BASE_URL, params=params, timeout=(5, 20))
    response.raise_for_status()
    payload = response.json()
    rows: list[dict[str, Any]] = []
    meta = SERIES[series_id]
    scale = float(meta.get("scale", 1))
    for item in payload.get("observations", []):
        value = _number(item.get("value"))
        if value is None:
            continue
        rows.append({"date": item.get("date"), "value": value * scale})
    return rows


def _last(rows: list[dict[str, Any]]) -> float | None:
    return rows[-1]["value"] if rows else None


def _change(rows: list[dict[str, Any]], periods: int = 1) -> float | None:
    if len(rows) <= periods:
        return None
    current = rows[-1]["value"]
    previous = rows[-1 - periods]["value"]
    if previous == 0:
        return None
    return (current / previous - 1) * 100


def _delta(rows: list[dict[str, Any]], periods: int = 1) -> float | None:
    if len(rows) <= periods:
        return None
    return rows[-1]["value"] - rows[-1 - periods]["value"]


def _annual_yoy(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # CPI/PCE têm frequência mensal; compara 12 observações para reproduzir a lógica do grafico.py.
    if len(rows) < 13:
        return []
    result = []
    for idx in range(12, len(rows)):
        base = rows[idx - 12]["value"]
        if base == 0:
            continue
        result.append({"date": rows[idx]["date"], "value": (rows[idx]["value"] / base - 1) * 100})
    return result


def _align_dates(*series: list[dict[str, Any]]) -> dict[str, list[Any]]:
    dates = sorted({row["date"] for rows in series for row in rows})
    lookup = [{row["date"]: row["value"] for row in rows} for rows in series]
    values = [[mapping.get(day) for day in dates] for mapping in lookup]
    return {"dates": dates, "values": values}


def _build_insights(data: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    dgs10 = _last(data.get("DGS10", []))
    dgs2 = _last(data.get("DGS2", []))
    dff = _last(data.get("DFF", []))
    breakeven = _last(data.get("T10YIE", []))
    unemployment = _last(data.get("UNRATE", []))
    cpi_yoy = _last(_annual_yoy(data.get("CPIAUCSL", [])))
    pce_yoy = _last(_annual_yoy(data.get("PCEPI", [])))

    spread = dgs10 - dgs2 if dgs10 is not None and dgs2 is not None else None
    score = 0
    drivers: list[str] = []
    caution: list[str] = []

    if spread is not None:
        if spread > 0:
            score += 1
            drivers.append(f"Curva 10Y-2Y positiva ({spread:+.2f} pp): regime menos invertido.")
        else:
            score -= 1
            drivers.append(f"Curva 10Y-2Y invertida ({spread:+.2f} pp): crescimento/risk-off merece atenção.")

    if dff is not None and dgs2 is not None:
        policy_gap = dgs2 - dff
        if policy_gap < -0.25:
            score -= 1
            drivers.append(f"2Y abaixo do Fed Funds ({policy_gap:+.2f} pp): mercado precifica flexibilização à frente.")
        elif policy_gap > 0.25:
            score += 1
            drivers.append(f"2Y acima do Fed Funds ({policy_gap:+.2f} pp): juros futuros ainda restritivos.")

    if cpi_yoy is not None:
        if cpi_yoy > 3:
            score += 1
            drivers.append(f"CPI YoY {cpi_yoy:.2f}%: inflação acima da região de conforto.")
        elif cpi_yoy < 2:
            score -= 1
            drivers.append(f"CPI YoY {cpi_yoy:.2f}%: desinflação forte.")

    if pce_yoy is not None and pce_yoy > 2.5:
        score += 1
        drivers.append(f"PCE YoY {pce_yoy:.2f}%: pressão inflacionária relevante para o Fed.")

    if unemployment is not None:
        if unemployment < 4:
            score += 1
            drivers.append(f"Desemprego {unemployment:.2f}%: mercado de trabalho aquecido.")
        elif unemployment > 6:
            score -= 1
            drivers.append(f"Desemprego {unemployment:.2f}%: deterioração forte do mercado de trabalho.")

    if breakeven is not None and breakeven > 3:
        caution.append(f"Breakeven 10Y em {breakeven:.2f}%: expectativas de inflação elevadas.")

    if score >= 3:
        bias = "USD estruturalmente mais forte"
        tone = "positive"
    elif score <= -2:
        bias = "USD estruturalmente mais fraco"
        tone = "negative"
    else:
        bias = "USD neutro / misto"
        tone = "neutral"

    return {
        "score": score,
        "bias": bias,
        "tone": tone,
        "spread_10_2": spread,
        "policy_gap_2y_fedfunds": (dgs2 - dff) if dgs2 is not None and dff is not None else None,
        "drivers": drivers,
        "caution": caution,
        "cpi_yoy": cpi_yoy,
        "pce_yoy": pce_yoy,
    }


def collect_fed_data(force: bool = False) -> dict[str, Any]:
    if not force:
        cached = cache.get(CACHE_KEY)
        if cached:
            return cached

    api_key = os.getenv("FRED_API_KEY", "").strip()
    if not api_key:
        return {
            "available": False,
            "message": "FRED_API_KEY não configurada. Defina a chave no .env para ativar a análise EUA.",
            "source": "FRED / Federal Reserve Bank of St. Louis",
        }

    end = date.today()
    start = end - timedelta(days=365 * max(HISTORY_YEARS, 1))
    series_data: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}

    for series_id in SERIES:
        try:
            series_data[series_id] = _fetch_series(series_id, start, end, api_key)
        except Exception as exc:  # uma série indisponível não derruba a página inteira
            logger.warning("FRED %s indisponível: %s", series_id, exc)
            errors[series_id] = str(exc)
            series_data[series_id] = []

    latest: dict[str, dict[str, Any]] = {}
    for series_id, rows in series_data.items():
        if not rows:
            continue
        latest[series_id] = {
            "label": SERIES[series_id]["label"],
            "value": _last(rows),
            "change": _change(rows),
            "delta": _delta(rows),
            "date": rows[-1]["date"],
            "unit": SERIES[series_id]["unit"],
        }

    inflation_cpi = _annual_yoy(series_data.get("CPIAUCSL", []))
    inflation_pce = _annual_yoy(series_data.get("PCEPI", []))

    rates = _align_dates(
        series_data.get("DGS10", []),
        series_data.get("DGS2", []),
        series_data.get("DFF", []),
    )
    spread_dates = rates["dates"]
    spread_values: list[float | None] = []
    for a, b in zip(rates["values"][0], rates["values"][1]):
        spread_values.append(a - b if a is not None and b is not None else None)

    result = {
        "available": True,
        "source": "FRED / Federal Reserve Bank of St. Louis",
        "source_url": "https://fred.stlouisfed.org/",
        "from": start.isoformat(),
        "to": end.isoformat(),
        "latest": latest,
        "series": series_data,
        "derived": {
            "cpi_yoy": inflation_cpi,
            "pce_yoy": inflation_pce,
            "spread_10_2": {"dates": spread_dates, "values": spread_values},
        },
        "insights": _build_insights(series_data),
        "errors": errors,
    }
    cache.set(CACHE_KEY, result, timeout=CACHE_TTL)
    return result
