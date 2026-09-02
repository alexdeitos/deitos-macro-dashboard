from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from dashboard.models import CollectionRun, MarketPoint, MarketSnapshot

LATEST_CACHE_KEY = "market-dashboard:latest"
HISTORY_SYMBOLS = ("USD_BRL", "DXY", "IBOV", "EWZ", "DJI", "SP500", "VIX")


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _float(value: Any) -> float | None:
    """Converte somente valores numéricos válidos para JSON, sem formatar."""
    decimal_value = _decimal(value)
    return float(decimal_value) if decimal_value is not None else None


def _point_from_dict(row: dict[str, Any]) -> MarketPoint | None:
    observed_at = parse_datetime(str(row.get("observed_at", "")))
    if observed_at is None:
        return None
    if timezone.is_naive(observed_at):
        observed_at = timezone.make_aware(observed_at)
    symbol = str(row.get("symbol", "")).strip()
    if not symbol:
        return None
    return MarketPoint(
        observed_at=observed_at,
        symbol=symbol,
        name=str(row.get("name", symbol))[:120],
        category=str(row.get("category", "unknown"))[:40],
        value=_decimal(row.get("value")),
        change_percent=_decimal(row.get("change_percent")),
        source=str(row.get("source", "unknown"))[:50],
        metadata={
            **{
                key: row.get(key)
                for key in ("high", "low", "open", "previous_close", "currency", "source_url")
                if row.get(key) is not None
            },
            **({"raw": row.get("raw")} if isinstance(row.get("raw"), dict) else {}),
        },
    )


@transaction.atomic
def persist_payload(payload: dict[str, Any], run: CollectionRun) -> MarketSnapshot:
    collected_at = parse_datetime(payload["collected_at"])
    if collected_at is None:
        collected_at = timezone.now()
    snapshot = MarketSnapshot.objects.create(
        collected_at=collected_at,
        payload=payload,
        source_status=payload.get("source_status", {}),
        is_complete=bool(payload.get("is_complete")),
        duration_ms=int(payload.get("duration_ms", 0)),
        run=run,
    )

    rows = list(payload.get("quote_list", []))
    rows.extend(payload.get("groups", {}).get("intraday", []))
    points = [point for row in rows if (point := _point_from_dict(row)) is not None]
    if points:
        MarketPoint.objects.bulk_create(points, ignore_conflicts=True, batch_size=500)

    cache.set(LATEST_CACHE_KEY, payload, timeout=settings.MARKET_CACHE_TTL)
    return snapshot


def get_latest_payload() -> dict[str, Any] | None:
    cached = cache.get(LATEST_CACHE_KEY)
    if cached:
        return cached
    snapshot = MarketSnapshot.objects.first()
    if snapshot:
        cache.set(LATEST_CACHE_KEY, snapshot.payload, timeout=settings.MARKET_CACHE_TTL)
        return snapshot.payload
    return None


def history_payload() -> dict[str, Any]:
    """Monta o histórico usando uma linha por atualização salva no banco.

    A fonte do gráfico é MarketSnapshot, e não o horário informado por cada
    provedor. Assim, cada execução da coleta gera no máximo um ponto por ativo,
    com o timestamp real da atualização do dashboard.
    """
    hours = int(getattr(settings, "MARKET_CHART_HISTORY_HOURS", 24))
    start = timezone.now() - timedelta(hours=max(1, hours))

    snapshots = (
        MarketSnapshot.objects.filter(collected_at__gte=start)
        .order_by("collected_at", "id")
        .only("collected_at", "payload")
    )

    series: dict[str, list[dict[str, Any]]] = {
        symbol: [] for symbol in HISTORY_SYMBOLS
    }
    composite: list[dict[str, Any]] = []

    for snapshot in snapshots.iterator(chunk_size=200):
        payload = snapshot.payload if isinstance(snapshot.payload, dict) else {}
        quotes = payload.get("quotes", {})
        if not isinstance(quotes, dict):
            quotes = {}

        timestamp = snapshot.collected_at.isoformat()

        for symbol in HISTORY_SYMBOLS:
            quote = quotes.get(symbol)
            if not isinstance(quote, dict):
                continue

            value = _float(quote.get("value"))
            if value is None:
                continue

            series[symbol].append(
                {
                    "timestamp": timestamp,
                    "value": value,
                    "change_percent": _float(quote.get("change_percent")),
                    "source": str(quote.get("source", "")),
                    "observed_at": quote.get("observed_at"),
                }
            )

        analysis = payload.get("analysis", {})
        if not isinstance(analysis, dict):
            analysis = {}
        global_analysis = analysis.get("global", {})
        brazil_analysis = analysis.get("brazil", {})
        if not isinstance(global_analysis, dict):
            global_analysis = {}
        if not isinstance(brazil_analysis, dict):
            brazil_analysis = {}

        global_value = _float(global_analysis.get("composite_change_percent"))
        brazil_value = _float(brazil_analysis.get("composite_change_percent"))

        if global_value is not None or brazil_value is not None:
            global_confidence = global_analysis.get("confidence", {})
            brazil_confidence = brazil_analysis.get("confidence", {})
            if not isinstance(global_confidence, dict):
                global_confidence = {}
            if not isinstance(brazil_confidence, dict):
                brazil_confidence = {}

            composite.append(
                {
                    "timestamp": timestamp,
                    "global": global_value,
                    "brazil": brazil_value,
                    "global_sample_size": global_confidence.get("sample_size"),
                    "brazil_sample_size": brazil_confidence.get("sample_size"),
                    "global_direction": global_analysis.get("direction"),
                    "brazil_direction": brazil_analysis.get("direction"),
                }
            )

    return {
        "window_hours": hours,
        "source": "database_snapshots",
        "series": series,
        "composite": composite,
    }


def cleanup_old_data() -> dict[str, int]:
    cutoff = timezone.now() - timedelta(days=settings.MARKET_HISTORY_DAYS)
    points_deleted = MarketPoint.objects.filter(observed_at__lt=cutoff).delete()[0]
    snapshots_deleted = MarketSnapshot.objects.filter(collected_at__lt=cutoff).delete()[0]
    runs_deleted = CollectionRun.objects.filter(started_at__lt=cutoff).delete()[0]
    return {
        "points_deleted": points_deleted,
        "snapshots_deleted": snapshots_deleted,
        "runs_deleted": runs_deleted,
    }
