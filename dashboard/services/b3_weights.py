from __future__ import annotations

import logging
import re
from typing import Any

import requests
from bs4 import BeautifulSoup
from django.core.cache import cache

logger = logging.getLogger(__name__)

URL = "https://sistemaswebb3-listados.b3.com.br/indexPage/day/IBOV"
CACHE_KEY = "macro-dashboard:b3-ibov-weights:v1"
CACHE_TTL = 6 * 60 * 60

# Fallback mínimo: apenas os maiores pesos confirmados na carteira definitiva de 08/09/2026.
# Quando a página oficial B3 estiver acessível, a lista completa substitui automaticamente este fallback.
FALLBACK = {
    "VALE3": 0.11159,
    "ITUB4": 0.08613,
    "PETR4": 0.07999,
    "PETR3": 0.04889,
    "AXIA3": 0.04848,
}


def _percent(text: str) -> float | None:
    text = text.replace("%", "").strip()
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        return None
    # B3 returns percentages such as 11,159; convert to weight 0..1.
    return value / 100.0 if value > 1 else value


def _parse_table(html: str) -> dict[str, float]:
    soup = BeautifulSoup(html, "lxml")
    weights: dict[str, float] = {}
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            code = re.sub(r"\s+", "", cells[0]).upper()
            if not re.fullmatch(r"[A-Z]{4,6}[0-9]{1,2}", code):
                continue
            candidate = cells[-1]
            value = _percent(candidate)
            if value is None or not 0 < value <= 0.20:
                continue
            weights[code] = value
    return weights


def get_ibov_weights(*, force: bool = False) -> dict[str, Any]:
    if not force:
        cached = cache.get(CACHE_KEY)
        if cached:
            return cached

    try:
        response = requests.get(URL, timeout=(5, 20), headers={"User-Agent": "MacroDashboard/2.0"})
        response.raise_for_status()
        weights = _parse_table(response.text)
        if len(weights) < 30:
            raise ValueError(f"Carteira B3 retornou apenas {len(weights)} ativos válidos")
        payload = {
            "weights": weights,
            "source": "B3 - Carteira do Dia do Ibovespa",
            "source_url": URL,
            "as_of": "dinâmico / Carteira do Dia",
            "count": len(weights),
            "complete": True,
        }
        cache.set(CACHE_KEY, payload, timeout=CACHE_TTL)
        return payload
    except Exception as exc:
        logger.warning("B3 IBOV weights unavailable: %s", exc)
        return {
            "weights": FALLBACK,
            "source": "fallback mínimo - B3 top weights",
            "source_url": URL,
            "as_of": "08/09/2026",
            "count": len(FALLBACK),
            "complete": False,
            "warning": str(exc),
        }
