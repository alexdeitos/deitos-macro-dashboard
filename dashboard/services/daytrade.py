from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from dashboard.models import CapturePoint

from .capture_analysis import EXTERNAL_FACTORS, build_index_radar
from .investing_calendar import collect_investing_daytrade_calendar, investing_daytrade_events

CACHE_KEY = "macro-dashboard:daytrade:v1"
CACHE_TTL = 20
EVENT_GATE_MINUTES = 20
EVENT_WARNING_MINUTES = 45

# Sinais positivos/negativos por mercado e por regime. Os pesos são explícitos,
# reduzindo o risco de um único indicador dominar o painel.
MARKET_WEIGHTS = {
    "stock_pressure": 0.35,
    "global_risk": 0.25,
    "rates": 0.20,
    "breadth": 0.10,
    "event_context": 0.10,
}


def _num(v: Any) -> float | None:
    try:
        if v in (None, ""):
            return None
        value = float(v)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _sign(v: float | None) -> float:
    if v is None:
        return 0.0
    return 1.0 if v > 0 else -1.0 if v < 0 else 0.0


def _clamp(v: float, low: float = -1.0, high: float = 1.0) -> float:
    return max(low, min(high, v))


def _normalized_change(value: float | None, scale: float) -> float | None:
    if value is None:
        return None
    return math.tanh(value / scale)


def _event_type(event: dict[str, Any]) -> str:
    text = f"{event.get('event','')} {event.get('category','')}".lower()
    text = re.sub(r"[^a-z0-9áéíóúãõç ]+", " ", text)
    if any(k in text for k in ("cpi", "inflation", "inflacao", "pce", "ppi", "ipca", "inpc", "igpm")):
        return "inflation"
    if any(k in text for k in ("interest rate", "fed funds", "selic", "policy rate", "decision", "juros", "taxa basica")):
        return "rates"
    if any(k in text for k in ("payroll", "employment", "unemployment", "non farm", "jobless", "emprego", "desemprego")):
        return "labor"
    if any(k in text for k in ("gdp", "pmi", "industrial production", "retail sales", "manufacturing", "services", "atividade", "producao industrial")):
        return "growth"
    if any(k in text for k in ("trade balance", "current account", "exports", "imports", "balanca comercial")):
        return "trade"
    if any(k in text for k in ("central bank", "fomc", "bcb", "people's bank", "speech")):
        return "central_bank"
    return "other"


def _parse_value(text: str | None) -> float | None:
    if not text:
        return None
    raw = str(text).strip().replace("−", "-").replace("%", "")
    raw = raw.replace(" ", "")
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    match = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
    return float(match.group(0)) if match else None


def _event_surprise(event: dict[str, Any]) -> dict[str, Any]:
    actual = _parse_value(event.get("actual"))
    forecast = _parse_value(event.get("forecast"))
    previous = _parse_value(event.get("previous"))
    etype = _event_type(event)
    released = actual is not None

    if actual is None:
        return {
            "status": "AGUARDANDO",
            "actual": event.get("actual") or "—",
            "forecast": event.get("forecast") or "—",
            "previous": event.get("previous") or "—",
            "surprise": None,
            "delta_previous": None,
            "market_bias": "NEUTRO",
            "analysis": "Evento ainda não divulgado. O consenso e o anterior servem como referência, mas não entram como dado realizado.",
            "event_type": etype,
        }

    surprise = actual - forecast if forecast is not None else None
    delta_previous = actual - previous if previous is not None else None

    # Sem escala universal entre indicadores, a primeira camada usa direção da
    # surpresa e uma regra de interpretação específica do tipo de evento.
    if surprise is None:
        market = "MISTO"
        analysis = "Dado saiu sem consenso numérico utilizável; comparar apenas com o anterior e com a reação de preço/juros."
    elif etype == "inflation":
        market = "NEGATIVO" if surprise > 0 else "POSITIVO" if surprise < 0 else "NEUTRO"
        analysis = "Acima do consenso aumenta a leitura de pressão inflacionária/juros; abaixo favorece alívio de juros."
    elif etype == "rates":
        market = "NEGATIVO" if surprise > 0 else "POSITIVO" if surprise < 0 else "NEUTRO"
        analysis = "Taxa acima do esperado tende a apertar condições financeiras; abaixo tende a aliviar."
    elif etype == "labor":
        market = "MISTO"
        analysis = "Mercado de trabalho forte pode melhorar crescimento, mas também elevar a leitura de juros. Confirme com Treasury e índice."
    elif event.get("country_code") == "CN":
        market = "POSITIVO" if surprise > 0 else "NEGATIVO" if surprise < 0 else "NEUTRO"
        analysis = "Para China, surpresa positiva em atividade tende a favorecer commodities e emergentes; negativa faz o oposto."
    elif etype in {"growth", "trade"}:
        market = "POSITIVO" if surprise > 0 else "NEGATIVO" if surprise < 0 else "NEUTRO"
        analysis = "Surpresa de atividade/comércio acima do consenso tende a favorecer risco; valide com juros e bolsas."
    elif etype == "central_bank":
        market = "MISTO"
        analysis = "Decisões e comunicação de BC não devem ser reduzidas apenas a maior/menor; valide pelo repricing de juros."
    else:
        market = "POSITIVO" if surprise > 0 else "NEGATIVO" if surprise < 0 else "NEUTRO"
        analysis = "Surpresa acima/abaixo do consenso como referência direcional; reação efetiva do mercado prevalece."

    return {
        "status": "DIVULGADO",
        "actual": event.get("actual") or "—",
        "forecast": event.get("forecast") or "—",
        "previous": event.get("previous") or "—",
        "surprise": round(surprise, 6) if surprise is not None else None,
        "delta_previous": round(delta_previous, 6) if delta_previous is not None else None,
        "market_bias": market,
        "analysis": analysis,
        "event_type": etype,
        "released": released,
    }


def _event_context(events: list[dict[str, Any]], now=None) -> dict[str, Any]:
    now = now or timezone.localtime()
    analyzed = []
    event_score = 0.0
    released_count = 0
    next_event = None
    active_risk = False
    warning_risk = False

    for event in events:
        item = dict(event)
        analysis = _event_surprise(event)
        item["analysis"] = analysis
        when = datetime.fromisoformat(str(event["event_at"]))
        if timezone.is_naive(when):
            when = timezone.make_aware(when)
        delta_min = (when - now).total_seconds() / 60
        item["minutes_to_event"] = round(delta_min, 1)

        if next_event is None and delta_min >= -2:
            next_event = item
        if analysis["status"] == "DIVULGADO":
            released_count += 1
            if analysis["market_bias"] == "POSITIVO":
                event_score += 1.0
            elif analysis["market_bias"] == "NEGATIVO":
                event_score -= 1.0
        elif delta_min <= EVENT_GATE_MINUTES and delta_min >= -2:
            active_risk = True
        elif delta_min <= EVENT_WARNING_MINUTES and delta_min >= -2:
            warning_risk = True
        analyzed.append(item)

    released_signal = _clamp(event_score / max(1, released_count)) if released_count else 0.0
    if active_risk:
        gate = "EVENTO DE ALTO IMPACTO — AGUARDAR"
    elif warning_risk:
        gate = "EVENTO 3★ PRÓXIMO — CAUTELA"
    else:
        gate = "SEM EVENTO IMINENTE"
    return {
        "events": analyzed,
        "score": round(released_signal, 3),
        "released_count": released_count,
        "next_event": next_event,
        "active_risk": active_risk,
        "warning_risk": warning_risk,
        "gate": gate,
    }


def _factor_map(radar: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(item.get("symbol")): item for item in radar.get("external_factors", [])}


def _global_risk_score(radar: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    factors = _factor_map(radar)
    components = []
    raw = []
    for symbol, label, _, _orientation in EXTERNAL_FACTORS:
        item = factors.get(symbol)
        adjusted = _num(item.get("adjusted_change_percent")) if item else None
        signal = _normalized_change(adjusted, 1.0)
        if signal is None:
            continue
        # O painel já ajusta a orientação: VIX/DXY/US10Y negativos para ações.
        weight_map = {"DJI": .30, "SP500": .22, "NASDAQ": .10, "VIX": .12, "DXY": .08, "BRENT": .05, "WTI": .03, "IRON_ORE": .05, "EEM": .05}
        weight = weight_map.get(symbol, .03)
        raw.append(signal * weight)
        components.append({"symbol": symbol, "label": label, "signal": round(signal, 3), "weight_percent": round(weight * 100, 1), "weighted": round(signal * weight, 4)})
    total_weight = sum((abs(c.get("weight_percent", 0)) / 100 for c in components), 0.0)
    score = sum(raw) / total_weight if total_weight else 0.0
    return _clamp(score), components


def _rates_score() -> tuple[float, str]:
    now = timezone.now()
    start = now - timedelta(minutes=8)
    points = CapturePoint.objects.filter(
        observed_at__gte=start,
        symbol__iregex=r"^(DI1|DAP|PRE|DIF)",
    ).order_by("-observed_at")[:80]
    values = [_num(p.change_percent) for p in points]
    values = [v for v in values if v is not None]
    if not values:
        return 0.0, "Juros B3 sem captura recente."
    avg = sum(values) / len(values)
    score = _clamp(-avg / 1.5)
    return score, f"Variação média recente dos contratos de juros: {avg:+.3f}% · efeito direcional invertido para ações."


def _breadth_score(radar: dict[str, Any]) -> tuple[float, str]:
    stocks = radar.get("stock_pressure", {})
    pos = _num(stocks.get("positive_weight_percent")) or 0.0
    neg = _num(stocks.get("negative_weight_percent")) or 0.0
    coverage = _num(stocks.get("coverage_percent")) or 0.0
    denom = pos + neg
    breadth = ((pos - neg) / denom) if denom else 0.0
    return _clamp(breadth * min(coverage / 60.0, 1.0)), f"Peso positivo {pos:.1f}% · negativo {neg:.1f}% · cobertura {coverage:.1f}%."


def _fresh_capture_minutes(radar: dict[str, Any]) -> float | None:
    raw = radar.get("excel_capture", {}).get("observed_at")
    if not raw:
        return None
    try:
        observed = datetime.fromisoformat(str(raw))
        if timezone.is_naive(observed):
            observed = timezone.make_aware(observed)
        return max(0.0, (timezone.now() - observed).total_seconds() / 60)
    except Exception:
        return None


def _direction(score: float, *, gate: dict[str, Any], fresh_minutes: float | None) -> tuple[str, str, str]:
    if fresh_minutes is None or fresh_minutes > 3.0:
        return "AGUARDAR", "neutral", "Dados do Excel/Profit desatualizados ou ausentes."
    if gate["active_risk"]:
        return "AGUARDAR", "warning", "Há divulgação 3★ iminente; aguarde o dado e o primeiro repricing."
    if score >= .25:
        return "VIÉS COMPRADOR", "positive", "Confluência favorável ao índice; aguarde confirmação de preço/fluxo."
    if score <= -.25:
        return "VIÉS VENDEDOR", "negative", "Confluência desfavorável ao índice; aguarde confirmação de preço/fluxo."
    return "NEUTRO / LATERAL", "neutral", "Sinais mistos; reduza agressividade e espere o preço definir o lado."


def build_daytrade(*, force: bool = False) -> dict[str, Any]:
    if not force:
        cached = cache.get(CACHE_KEY)
        if cached:
            return cached

    # Keep the existing radar as the source of the already-built market model.
    radar = build_index_radar(force=force)
    investing_status = {}
    try:
        investing_status = collect_investing_daytrade_calendar(force=force)
    except Exception as exc:
        investing_status = {"status": "failed", "message": str(exc)}
    events = investing_daytrade_events()
    event_ctx = _event_context(events)

    stock = _normalized_change(_num(radar.get("stock_pressure", {}).get("weighted_change_percent")), 1.0)
    global_risk, global_components = _global_risk_score(radar)
    rates, rates_note = _rates_score()
    breadth, breadth_note = _breadth_score(radar)
    event_score = event_ctx["score"]

    pieces = {
        "stock_pressure": stock if stock is not None else 0.0,
        "global_risk": global_risk,
        "rates": rates,
        "breadth": breadth,
        "event_context": event_score,
    }
    score = sum(pieces.get(key, 0.0) * weight for key, weight in MARKET_WEIGHTS.items())
    score = _clamp(score)
    fresh_minutes = _fresh_capture_minutes(radar)
    direction, tone, action = _direction(score, gate=event_ctx, fresh_minutes=fresh_minutes)

    # Confiabilidade é qualidade da confluência, não probabilidade estatística.
    available = [v for v in pieces.values() if v is not None]
    dispersion = (sum(abs(v) for v in available) / len(available)) if available else 0.0
    agreement = sum(1 for v in available if _sign(v) == _sign(score) and abs(v) >= .10) / max(1, sum(1 for v in available if abs(v) >= .10))
    confidence = "BAIXA"
    if dispersion >= .30 and agreement >= .70:
        confidence = "ALTA"
    elif dispersion >= .18 and agreement >= .55:
        confidence = "MODERADA"

    # Prioridade operacional: evento > freshness > directional confluence.
    state = "NORMAL"
    if event_ctx["active_risk"]:
        state = "EVENTO"
    elif fresh_minutes is None or fresh_minutes > 3:
        state = "DADOS DESATUALIZADOS"
    elif event_ctx["warning_risk"]:
        state = "CAUTELA"

    payload = {
        "generated_at": timezone.now().isoformat(),
        "direction": direction,
        "tone": tone,
        "score": round(score * 100, 1),
        "confidence": confidence,
        "state": state,
        "action": action,
        "market_target": radar.get("target"),
        "capture_age_minutes": round(fresh_minutes, 1) if fresh_minutes is not None else None,
        "components": [
            {"key": "stock_pressure", "label": "Ações IBOV ponderadas", "score": round(pieces["stock_pressure"] * 100, 1), "weight_percent": 35.0, "note": f"{radar.get('stock_pressure', {}).get('weighted_change_percent') or 0:+.3f}% ponderado."},
            {"key": "global_risk", "label": "Ambiente global", "score": round(pieces["global_risk"] * 100, 1), "weight_percent": 25.0, "note": "DJI principal, seguido por S&P/Nasdaq, VIX, DXY, commodities e EEM."},
            {"key": "rates", "label": "Juros B3", "score": round(pieces["rates"] * 100, 1), "weight_percent": 20.0, "note": rates_note},
            {"key": "breadth", "label": "Amplitude / breadth", "score": round(pieces["breadth"] * 100, 1), "weight_percent": 10.0, "note": breadth_note},
            {"key": "event_context", "label": "Agenda 3★", "score": round(pieces["event_context"] * 100, 1), "weight_percent": 10.0, "note": event_ctx["gate"]},
        ],
        "global_components": global_components,
        "radar": radar,
        "calendar": {**event_ctx, "source_status": investing_status, "source": "Investing.com", "scope": {"countries": ["BR", "US", "CN"], "importance": 3, "date": timezone.localdate().isoformat()}},
        "methodology": {
            "weights": {k: int(v * 100) for k, v in MARKET_WEIGHTS.items()},
            "hard_gate": "Dados Excel/Profit > 3 min ou evento 3★ iminente => AGUARDAR.",
            "event_policy": "Somente Brasil, EUA e China, importância 3 estrelas e data de hoje.",
            "disclaimer": "Viés contextual para apoio à decisão; não é recomendação financeira nem gatilho automático.",
        },
    }
    cache.set(CACHE_KEY, payload, timeout=CACHE_TTL)
    return payload
