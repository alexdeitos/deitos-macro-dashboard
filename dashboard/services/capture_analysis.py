from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import timedelta
from statistics import mean
from typing import Any

from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from dashboard.models import CapturePoint

from .b3_weights import get_ibov_weights
from .fed_analysis import collect_fed_data
from .persistence import get_latest_payload


CACHE_KEY = "macro-dashboard:index-radar:v2"
CACHE_TTL = 15
ANALYSIS_WINDOW_MINUTES = 180
CORRELATION_LIMIT = 1800

# Driver weights are normalized over the factors actually available at runtime.
EXTERNAL_FACTORS = (
    ("DJI", "Dow Jones", 0.13, 1),
    ("SP500", "S&P 500", 0.11, 1),
    ("NASDAQ", "Nasdaq", 0.05, 1),
    ("VIX", "VIX", 0.09, -1),
    ("DXY", "DXY", 0.06, -1),
    ("BRENT", "Brent", 0.05, 1),
    ("WTI", "WTI", 0.03, 1),
    ("IRON_ORE", "Minério de ferro", 0.04, 1),
    ("EEM", "Emergentes (EEM)", 0.03, 1),
    ("US10Y", "Treasury 10Y", 0.05, -1),
)

RATE_PREFIXES = ("DI1", "DAP", "PRE", "DIF")
TARGET_SYMBOLS = ("IBOV", "WIN", "WINFUT", "IBOVFUT")
# IFNC is used as an explicit internal confirmation factor for the index direction.
IFNC_INTERNAL_WEIGHT = 0.10
INDEX_CONTRACT_SYMBOL = "WINFUT"
DOLLAR_CONTRACT_SYMBOL = "WDOFUT"


def _num(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            text = value.strip().replace("%", "")
            # Accept both Excel/pt-BR and plain decimal strings.
            if "," in text and "." in text:
                text = text.replace(".", "").replace(",", ".")
            elif "," in text:
                text = text.replace(",", ".")
            x = float(text)
        else:
            x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _effective_change_percent(point: CapturePoint | None) -> float | None:
    """Return the real Profit VAR for CONFIG_CAPTURA when available.

    Older auto-sync records stored the RTD VAR in metadata but accidentally
    persisted an interval-to-interval return in change_percent. Prefer the
    explicit RTD field when present so historical rows are repaired at read
    time without requiring a destructive database rewrite.
    """
    if point is None:
        return None
    metadata = point.metadata if isinstance(point.metadata, dict) else {}
    if point.sheet_name == "CONFIG_CAPTURA":
        for key in ("rtD_field_c", "rtd_field_c", "variation_percent", "profit_var"):
            value = _num(metadata.get(key))
            if value is not None:
                return value
    return _num(point.change_percent)


def _parse_iso(value: Any):
    if value in (None, ""):
        return timezone.now()
    dt = parse_datetime(str(value))
    if dt is None:
        return timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


def _signal_from_percent(value: float | None, scale: float = 1.0) -> float | None:
    if value is None:
        return None
    return math.tanh(value / scale)


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 20 or len(xs) != len(ys):
        return None
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mx) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - my) ** 2 for y in ys))
    if not den_x or not den_y:
        return None
    return num / (den_x * den_y)


def _latest_capture_map(window_minutes: int = ANALYSIS_WINDOW_MINUTES) -> dict[str, CapturePoint]:
    """Return the latest Profit/Excel capture per symbol.

    CONFIG_CAPTURA is the authoritative source for the stock/curve radar when
    the user is feeding the workbook through RTD/COM. Restricting this map to
    that sheet prevents a duplicated symbol from another sheet/source from
    silently replacing the value used in the weighted IBOV calculation.
    """
    start = timezone.now() - timedelta(minutes=window_minutes)
    rows = (
        CapturePoint.objects.filter(
            observed_at__gte=start,
            sheet_name="CONFIG_CAPTURA",
        )
        .order_by("observed_at", "id")
        .only("observed_at", "symbol", "value", "change_percent", "sheet_name")
    )
    latest: dict[str, CapturePoint] = {}
    for row in rows.iterator(chunk_size=5000):
        current = latest.get(row.symbol)
        if current is None or row.observed_at >= current.observed_at:
            latest[row.symbol] = row
    return latest


def _find_target(latest: dict[str, CapturePoint]) -> CapturePoint | None:
    for symbol in TARGET_SYMBOLS:
        if symbol in latest:
            return latest[symbol]
    # Accept symbols that clearly represent the index/future.
    for symbol, point in latest.items():
        token = symbol.upper().replace("-", "")
        if token.startswith("WIN") or token.startswith("IBOV"):
            return point
    return None


def _weighted_stocks(latest: dict[str, CapturePoint], weights: dict[str, float]) -> dict[str, Any]:
    """Calculate raw variation, official weight and index contribution separately.

    * change_percent: the exact VAR (%) coming from Profit/RTD.
    * weight_percent: the theoretical Ibovespa weight.
    * contribution_percent: change × weight, expressed in percentage points
      of the index. This is intentionally *not* renormalized.
    * weighted_change_percent: weighted average of only the covered names,
      useful as a descriptive breadth metric when coverage is partial.
    """
    rows = []
    weighted_change = 0.0
    available_weight = 0.0
    positive_weight = 0.0
    negative_weight = 0.0

    for symbol, weight in weights.items():
        point = latest.get(symbol)
        if point is None:
            aliases = {
                "SP500": ("ES", "SPX", "SP500", "^GSPC"),
                "DJI": ("YM", "DOW", "DJI", "^DJI"),
                "NASDAQ": ("NQ", "NDX", "NASDAQ", "^IXIC"),
                "IRON_ORE": ("IRON", "MINERIO", "FE"),
                "US10Y": ("US10Y", "TNX", "US10YRATE"),
            }.get(symbol, ())
            for alias in aliases:
                if alias in latest:
                    point = latest[alias]
                    break
        change = _effective_change_percent(point)
        if change is None:
            continue
        contribution = change * weight
        weighted_change += contribution
        available_weight += weight
        if change > 0:
            positive_weight += weight
        elif change < 0:
            negative_weight += weight
        rows.append(
            {
                "symbol": symbol,
                "sheet": point.sheet_name if point else "",
                "price": round(_num(point.value) or 0.0, 6),
                "change_percent": round(change, 5),
                "weight": round(weight, 8),
                "weight_percent": round(weight * 100, 4),
                "contribution_percent": round(contribution, 6),
                "contribution_label": "p.p. IBOV",
                "observed_at": point.observed_at.isoformat(),
                "source": (
                    "Excel/Profit"
                    if isinstance(point.metadata, dict) and point.metadata.get("source") == "profit_excel_com"
                    else "CONFIG_CAPTURA"
                ),
            }
        )

    rows.sort(key=lambda item: abs(item["contribution_percent"]), reverse=True)
    normalized_change = weighted_change / available_weight if available_weight else None
    coverage = available_weight / sum(weights.values()) if weights else 0.0

    return {
        "weighted_change_percent": round(normalized_change, 5) if normalized_change is not None else None,
        "index_contribution_percent": round(weighted_change, 5),
        "raw_contribution_percent": round(weighted_change, 5),
        "coverage_percent": round(coverage * 100, 1),
        "positive_weight_percent": round(positive_weight * 100, 2),
        "negative_weight_percent": round(negative_weight * 100, 2),
        "available_assets": len(rows),
        "total_assets": len(weights),
        "top_positive": [r for r in rows if r["contribution_percent"] > 0][:10],
        "top_negative": [r for r in rows if r["contribution_percent"] < 0][:10],
        "all": rows,
    }


def _external_latest(latest: dict[str, CapturePoint]) -> dict[str, dict[str, Any]]:
    public_payload = get_latest_payload() or {}
    public_quotes = public_payload.get("quotes", {}) if isinstance(public_payload, dict) else {}
    result: dict[str, dict[str, Any]] = {}
    for symbol, label, base_weight, orientation in EXTERNAL_FACTORS:
        point = latest.get(symbol)
        if point is None:
            aliases = {
                "SP500": ("ES", "SPX", "SP500", "^GSPC"),
                "DJI": ("YM", "DOW", "DJI", "^DJI"),
                "NASDAQ": ("NQ", "NDX", "NASDAQ", "^IXIC"),
                "IRON_ORE": ("IRON", "MINERIO", "FE"),
                "US10Y": ("US10Y", "TNX", "US10YRATE"),
            }.get(symbol, ())
            for alias in aliases:
                if alias in latest:
                    point = latest[alias]
                    break
        public = public_quotes.get(symbol) if isinstance(public_quotes, dict) else None
        if point is not None:
            change = _effective_change_percent(point)
            value = _num(point.value)
            source = "Excel/Profit capture"
            observed = point.observed_at.isoformat()
        elif isinstance(public, dict):
            change = _num(public.get("change_percent"))
            value = _num(public.get("value"))
            source = public.get("source") or "coleta externa do dashboard"
            observed = public.get("observed_at")
        else:
            change = None
            value = None
            source = None
            observed = None

        adjusted = change * orientation if change is not None else None
        result[symbol] = {
            "symbol": symbol,
            "label": label,
            "base_weight": base_weight,
            "orientation": orientation,
            "change_percent": round(change, 5) if change is not None else None,
            "adjusted_change_percent": round(adjusted, 5) if adjusted is not None else None,
            "value": value,
            "source": source,
            "observed_at": observed,
        }

    # Treasury 10Y: use FRED when neither Excel nor the public market collector has it.
    if result["US10Y"]["change_percent"] is None:
        try:
            fred = collect_fed_data()
            latest_rate = fred.get("latest", {}).get("DGS10", {})
            if latest_rate:
                delta = _num(latest_rate.get("delta"))
                value = _num(latest_rate.get("value"))
                # Rising Treasury yields are treated as a risk-off pressure here.
                signal_change = delta
                result["US10Y"].update(
                    {
                        "value": value,
                        "change_percent": round(signal_change, 5) if signal_change is not None else None,
                        "adjusted_change_percent": round(signal_change * -1, 5) if signal_change is not None else None,
                        "source": "FRED / Treasury 10Y",
                        "observed_at": latest_rate.get("date"),
                        "unit": "p.p. diário",
                    }
                )
        except Exception:
            pass

    return result


def _captured_rate(latest: dict[str, CapturePoint]) -> dict[str, Any] | None:
    candidates = [p for s, p in latest.items() if s.upper().startswith(RATE_PREFIXES)]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.observed_at, reverse=True)
    point = candidates[0]
    change = _effective_change_percent(point)
    if change is None:
        return None
    return {
        "symbol": point.symbol,
        "label": f"Juros B3 ({point.symbol})",
        "change_percent": round(change, 5),
        "orientation": -1,
        "signal": _signal_from_percent(-change, scale=0.5),
        "source": "Excel/Profit capture",
        "observed_at": point.observed_at.isoformat(),
    }


def _correlations(target: CapturePoint | None) -> list[dict[str, Any]]:
    if target is None:
        return []

    symbols = [s for s, _, _, _ in EXTERNAL_FACTORS]
    start = timezone.now() - timedelta(minutes=ANALYSIS_WINDOW_MINUTES)
    wanted = list(TARGET_SYMBOLS) + symbols
    rows = (
        CapturePoint.objects.filter(observed_at__gte=start, symbol__in=wanted)
        .order_by("observed_at", "id")
        .only("observed_at", "symbol", "change_percent", "metadata", "sheet_name")
    )

    buckets: dict[str, dict[str, float]] = defaultdict(dict)
    for point in rows.iterator(chunk_size=5000):
        number = _effective_change_percent(point)
        observed_at, symbol = point.observed_at, point.symbol
        if number is None:
            continue
        key = observed_at.replace(microsecond=0).isoformat()
        buckets[key][symbol] = number
        if len(buckets) > CORRELATION_LIMIT:
            break

    target_symbol = target.symbol
    result = []
    for symbol, label, _, orientation in EXTERNAL_FACTORS:
        xs, ys = [], []
        for values in buckets.values():
            x = values.get(target_symbol)
            y = values.get(symbol)
            if x is None or y is None:
                continue
            xs.append(x)
            ys.append(y)
        corr = _pearson(xs, ys)
        if corr is None:
            # Fallback: use the dashboard's persistent MarketPoint history when
            # the Excel capture does not contain the external factor at the same timestamp.
            from dashboard.models import MarketPoint
            target_rows = list(
                MarketPoint.objects.filter(observed_at__gte=start, symbol=target_symbol)
                .order_by("observed_at")
                .values_list("observed_at", "change_percent")[:2000]
            )
            factor_rows = list(
                MarketPoint.objects.filter(observed_at__gte=start, symbol=symbol)
                .order_by("observed_at")
                .values_list("observed_at", "change_percent")[:2000]
            )
            target_by_minute = {t.replace(second=0, microsecond=0): _num(v) for t, v in target_rows if _num(v) is not None}
            factor_by_minute = {t.replace(second=0, microsecond=0): _num(v) for t, v in factor_rows if _num(v) is not None}
            xs2, ys2 = [], []
            for ts, x in target_by_minute.items():
                y = factor_by_minute.get(ts)
                if x is not None and y is not None:
                    xs2.append(x); ys2.append(y)
            corr = _pearson(xs2, ys2)
            if corr is not None:
                xs = xs2; ys = ys2
        if corr is None:
            continue
        result.append(
            {
                "symbol": symbol,
                "label": label,
                "correlation": round(corr, 3),
                "absolute_correlation": round(abs(corr), 3),
                "sample_size": len(xs),
                "relationship": "forte" if abs(corr) >= 0.60 else "moderada" if abs(corr) >= 0.35 else "fraca",
            }
        )

    result.sort(key=lambda item: item["absolute_correlation"], reverse=True)
    return result


def _direction(score: float | None) -> tuple[str, str]:
    if score is None:
        return "AGUARDAR", "neutral"
    if score >= 35:
        return "VIÉS COMPRADOR", "positive"
    if score <= -35:
        return "VIÉS VENDEDOR", "negative"
    return "MISTO / LATERAL", "neutral"


def _captured_instrument(latest: dict[str, CapturePoint], symbol: str) -> dict[str, Any]:
    point = latest.get(symbol)
    if point is None:
        return {
            "symbol": symbol,
            "available": False,
            "value": None,
            "change_percent": None,
            "volume": None,
            "trades": None,
            "observed_at": None,
            "source": None,
        }
    change = _effective_change_percent(point)
    return {
        "symbol": symbol,
        "available": True,
        "value": _num(point.value),
        "change_percent": change,
        "volume": _num(point.volume),
        "trades": _num(point.trades),
        "observed_at": point.observed_at.isoformat(),
        "source": (
            "Excel/Profit"
            if isinstance(point.metadata, dict) and point.metadata.get("source") == "profit_excel_com"
            else "CONFIG_CAPTURA"
        ),
    }

def build_index_radar(*, force: bool = False) -> dict[str, Any]:
    if not force:
        cached = cache.get(CACHE_KEY)
        if cached:
            return cached

    latest = _latest_capture_map()
    excel_latest_times = [p.observed_at for p in latest.values() if p.sheet_name == "CONFIG_CAPTURA"]
    excel_latest = max(excel_latest_times) if excel_latest_times else None
    weights_info = get_ibov_weights(force=force)
    weights = weights_info.get("weights", {})
    stocks = _weighted_stocks(latest, weights)
    externals = _external_latest(latest)

    factors: list[dict[str, Any]] = []
    weighted_signals = []
    for symbol, label, base_weight, orientation in EXTERNAL_FACTORS:
        item = externals[symbol]
        adjusted = item.get("adjusted_change_percent")
        signal = _signal_from_percent(adjusted, 1.0) if adjusted is not None else None
        if signal is None:
            continue
        weight = base_weight
        weighted_signals.append((signal, weight))
        factors.append(
            {
                **item,
                "signal": round(signal, 4),
                "weight_percent": round(weight * 100, 2),
                "weighted_signal": round(signal * weight, 5),
            }
        )

    stock_signal = _signal_from_percent(stocks["weighted_change_percent"], 1.0)
    if stock_signal is not None:
        weighted_signals.append((stock_signal, 0.55))

    # IFNC comes directly from CONFIG_CAPTURA/Profit and acts as an explicit
    # financial-sector confirmation for the index. It is not part of the
    # official IBOV stock-weight coverage; it is a separate directional factor.
    ifnc = _captured_instrument(latest, "IFNC")
    if ifnc["change_percent"] is not None:
        ifnc_signal = _signal_from_percent(ifnc["change_percent"], 1.0)
        if ifnc_signal is not None:
            weighted_signals.append((ifnc_signal, IFNC_INTERNAL_WEIGHT))
    rate = _captured_rate(latest)
    if rate is not None:
        weighted_signals.append((rate["signal"], 0.08))
        factors.append({**rate, "weight_percent": 8.0, "weighted_signal": round(rate["signal"] * 0.08, 5)})

    total_weight = sum(weight for _, weight in weighted_signals)
    composite = (sum(signal * weight for signal, weight in weighted_signals) / total_weight) if total_weight else None
    score = round(composite * 100, 1) if composite is not None else None
    direction, tone = _direction(score)

    available = len(stocks["all"])
    stock_coverage = stocks["coverage_percent"]
    factor_count = len(factors)
    agreement = None
    if weighted_signals:
        weighted_positive = sum(w for s, w in weighted_signals if s > 0.10)
        weighted_negative = sum(w for s, w in weighted_signals if s < -0.10)
        directional = weighted_positive + weighted_negative
        agreement = (max(weighted_positive, weighted_negative) / directional * 100) if directional else 0.0

    confidence = "baixa"
    if factor_count >= 5 and stock_coverage >= 60 and (agreement or 0) >= 70:
        confidence = "alta"
    elif factor_count >= 3 and stock_coverage >= 35 and (agreement or 0) >= 55:
        confidence = "moderada"

    correlation = _correlations(_find_target(latest))

    context_lines = []
    if stock_signal is not None:
        context_lines.append(
            f"Ações ponderadas: média ponderada das variações cobertas {stocks['weighted_change_percent']:+.3f}%; contribuição estimada para o IBOV {stocks['index_contribution_percent']:+.3f} p.p.; cobertura {stock_coverage:.1f}%."
        )
    if factors:
        top = factors[:3]
        context_lines.append(
            "Drivers externos dominantes: " + ", ".join(f"{x['label']} {x.get('adjusted_change_percent', 0):+.2f}%" for x in top)
        )
    if rate:
        context_lines.append(f"Juros B3: {rate['symbol']} {rate['change_percent']:+.3f}%, sinal invertido para ações.")
    if ifnc["change_percent"] is not None:
        context_lines.append(f"IFNC: {ifnc['change_percent']:+.3f}% · confirmação do setor financeiro.")

    result = {
        "available": bool(latest),
        "generated_at": timezone.now().isoformat(),
        "window_minutes": ANALYSIS_WINDOW_MINUTES,
        "target": (_find_target(latest).symbol if _find_target(latest) else None),
        "direction": direction,
        "tone": tone,
        "score": score,
        "confidence": confidence,
        "agreement_percent": round(agreement, 1) if agreement is not None else None,
        "coverage": {
            "ibov_weight_percent": stock_coverage,
            "captured_assets": available,
            "ibov_total_assets": stocks["total_assets"],
            "external_factor_count": factor_count,
            "weights_source": weights_info.get("source"),
            "weights_as_of": weights_info.get("as_of"),
            "weights_complete": bool(weights_info.get("complete", False)),
        },
        "stock_pressure": stocks,
        "ifnc": ifnc,
        "captured_instruments": {
            "WINFUT": _captured_instrument(latest, "WINFUT"),
            "WDOFUT": _captured_instrument(latest, "WDOFUT"),
            "IFNC": ifnc,
        },
        "external_factors": factors,
        "correlations": correlation,
        "context": context_lines,
        "excel_capture": {
            "status_label": "ONLINE" if excel_latest else "SEM CAPTURA",
            "observed_at": excel_latest.isoformat() if excel_latest else None,
            "asset_count": sum(1 for p in latest.values() if p.sheet_name == "CONFIG_CAPTURA"),
            "expected_interval_seconds": 60,
            "source": (
                "profit_excel_com"
                if any(
                    p.sheet_name == "CONFIG_CAPTURA"
                    and isinstance(p.metadata, dict)
                    and p.metadata.get("source") == "profit_excel_com"
                    for p in latest.values()
                )
                else "workbook_cache"
            ),
            "live_bridge": any(
                p.sheet_name == "CONFIG_CAPTURA"
                and isinstance(p.metadata, dict)
                and p.metadata.get("source") == "profit_excel_com"
                for p in latest.values()
            ),
        },
        "methodology": {
            "index_stock_pressure": "Soma ponderada das variações das ações pela participação teórica do Ibovespa; pesos ausentes não são inventados e a cobertura é informada.",
            "external_score": "Fatores externos recebem pesos explícitos e são renormalizados somente entre sinais disponíveis. VIX, DXY e juros são invertidos por pressão típica sobre ações; a leitura é contextual, não uma regra determinística.",
            "ifnc_confirmation": "IFNC do Profit/Excel entra como fator separado de confirmação do setor financeiro, com peso explícito de 10% no composto direcional do índice.",
            "correlation": "Correlação de Pearson intradiária calculada com capturas do Excel quando disponíveis e, como fallback, com o histórico persistido de MarketPoint do dashboard.",
            "disclaimer": "Indicação de viés, não probabilidade de acerto, recomendação financeira ou ordem de compra/venda.",
        },
    }
    cache.set(CACHE_KEY, result, timeout=CACHE_TTL)
    return result
