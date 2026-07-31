from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction

from dashboard.models import MarketPoint, MarketSnapshot
from dashboard.services.analytics import build_market_analysis
from dashboard.services.opening import build_opening_analysis
from dashboard.services.macro_opening import build_macro_opening_analysis
from dashboard.services.parity import build_dollar_parity
from dashboard.services.parsing import parse_iso_datetime, reconcile_change_percent
from dashboard.services.persistence import LATEST_CACHE_KEY
from dashboard.services.types import Quote



def _legacy_scale_fix(row: dict[str, Any]) -> bool:
    """Corrige IBOV antigo salvo como 177.866 em vez de 177866 pontos."""
    if row.get("symbol") != "IBOV":
        return False

    changed = False
    for key in ("value", "high", "low", "open", "previous_close"):
        value = row.get(key)
        if isinstance(value, (int, float)) and 100 <= abs(float(value)) < 1000:
            row[key] = float(value) * 1000.0
            changed = True
    return changed


def _repair_quote_dict(row: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    repaired = deepcopy(row)
    changed = _legacy_scale_fix(repaired)

    corrected, validation = reconcile_change_percent(
        scraped_change=repaired.get("change_percent"),
        value=repaired.get("value"),
        previous_close=repaired.get("previous_close"),
    )

    if corrected != repaired.get("change_percent"):
        repaired["change_percent"] = corrected
        changed = True

    raw = repaired.get("raw") if isinstance(repaired.get("raw"), dict) else {}
    old_validation = raw.get("validation")
    if old_validation != validation:
        raw["validation"] = validation
        repaired["raw"] = raw
        changed = True

    return repaired, changed


def _quote_from_dict(row: dict[str, Any]) -> Quote | None:
    symbol = str(row.get("symbol", "")).strip()
    if not symbol:
        return None
    return Quote(
        symbol=symbol,
        name=str(row.get("name", symbol)),
        category=str(row.get("category", "unknown")),
        source=str(row.get("source", "unknown")),
        observed_at=parse_iso_datetime(row.get("observed_at")),
        value=row.get("value"),
        change_percent=row.get("change_percent"),
        high=row.get("high"),
        low=row.get("low"),
        open=row.get("open"),
        previous_close=row.get("previous_close"),
        currency=row.get("currency"),
        source_url=row.get("source_url"),
        raw=row.get("raw") if isinstance(row.get("raw"), dict) else {},
    )


def _repair_payload(payload: dict[str, Any], *, trade_date) -> tuple[dict[str, Any], int]:
    result = deepcopy(payload)
    changed_rows = 0

    quote_list = result.get("quote_list")
    if not isinstance(quote_list, list):
        quotes_map = result.get("quotes", {})
        quote_list = list(quotes_map.values()) if isinstance(quotes_map, dict) else []

    repaired_list: list[dict[str, Any]] = []
    for row in quote_list:
        if not isinstance(row, dict):
            continue
        repaired, changed = _repair_quote_dict(row)
        repaired_list.append(repaired)
        changed_rows += int(changed)

    quote_map: dict[str, dict[str, Any]] = {}
    for row in repaired_list:
        symbol = str(row.get("symbol", ""))
        if not symbol:
            continue
        current = quote_map.get(symbol)
        if current is None or str(row.get("observed_at", "")) >= str(current.get("observed_at", "")):
            quote_map[symbol] = row

    quotes = [quote for row in repaired_list if (quote := _quote_from_dict(row)) is not None]
    result["quote_list"] = repaired_list
    result["quotes"] = quote_map
    groups = result.get("groups") if isinstance(result.get("groups"), dict) else {}
    groups["adrs"] = [row for row in repaired_list if row.get("category") == "adr"]
    groups["bonds"] = [row for row in repaired_list if row.get("category") == "bond_yield"]
    result["groups"] = groups
    result["schema_version"] = max(int(result.get("schema_version", 0) or 0), 4)

    corrected_symbols = sorted({
        str(row.get("symbol"))
        for row in repaired_list
        if isinstance(row.get("raw"), dict)
        and isinstance(row["raw"].get("validation"), dict)
        and row["raw"]["validation"].get("change_corrected")
    })
    mismatch_symbols = sorted({
        str(row.get("symbol"))
        for row in repaired_list
        if isinstance(row.get("raw"), dict)
        and isinstance(row["raw"].get("validation"), dict)
        and row["raw"]["validation"].get("validation_status") == "price_reference_mismatch"
    })
    source_status = result.get("source_status") if isinstance(result.get("source_status"), dict) else {}
    investing_status = source_status.get("investing") if isinstance(source_status.get("investing"), dict) else {}
    investing_metadata = (
        investing_status.get("metadata")
        if isinstance(investing_status.get("metadata"), dict)
        else {}
    )
    investing_metadata.update({
        "history_repaired": True,
        "corrected_change_symbols": corrected_symbols,
        "price_reference_mismatch_symbols": mismatch_symbols,
    })
    investing_status["metadata"] = investing_metadata
    source_status["investing"] = investing_status
    result["source_status"] = source_status

    if quotes:
        parity = build_dollar_parity(quotes, today=trade_date)
        result["analysis"] = build_market_analysis(quotes)
        result["dollar_parity"] = parity
        result["macro_opening"] = build_macro_opening_analysis(quotes)
        result["opening_analysis"] = build_opening_analysis(quotes, parity)

    return result, changed_rows


class Command(BaseCommand):
    help = (
        "Repara snapshots históricos com sinais invertidos do Investing, "
        "corrige a escala antiga do IBOV e recalcula análises."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Mostra o que seria alterado sem salvar.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Limita a quantidade de snapshots; 0 processa todos.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])
        limit = max(0, int(options["limit"]))

        queryset = MarketSnapshot.objects.order_by("collected_at", "id")
        if limit:
            queryset = queryset[:limit]

        snapshots_changed = 0
        quote_rows_changed = 0

        for snapshot in queryset.iterator(chunk_size=100):
            payload = snapshot.payload if isinstance(snapshot.payload, dict) else {}
            repaired, changed_rows = _repair_payload(
                payload,
                trade_date=snapshot.collected_at.date(),
            )
            if repaired != payload:
                snapshots_changed += 1
                quote_rows_changed += changed_rows
                if not dry_run:
                    snapshot.payload = repaired
                    snapshot.save(update_fields=["payload"])

        points_changed = 0
        points_to_update: list[MarketPoint] = []
        for point in MarketPoint.objects.order_by("id").iterator(chunk_size=500):
            old_value = float(point.value) if point.value is not None else None
            old_change = float(point.change_percent) if point.change_percent is not None else None
            metadata = deepcopy(point.metadata) if isinstance(point.metadata, dict) else {}
            previous_close = metadata.get("previous_close")

            new_value = old_value
            if point.symbol == "IBOV" and old_value is not None and 100 <= abs(old_value) < 1000:
                new_value = old_value * 1000.0
                if isinstance(previous_close, (int, float)) and 100 <= abs(float(previous_close)) < 1000:
                    previous_close = float(previous_close) * 1000.0
                    metadata["previous_close"] = previous_close

            new_change, validation = reconcile_change_percent(
                scraped_change=old_change,
                value=new_value,
                previous_close=previous_close,
            )
            raw = metadata.get("raw") if isinstance(metadata.get("raw"), dict) else {}
            raw["validation"] = validation
            metadata["raw"] = raw

            changed = new_value != old_value or new_change != old_change or metadata != point.metadata
            if changed:
                points_changed += 1
                if not dry_run:
                    point.value = new_value
                    point.change_percent = new_change
                    point.metadata = metadata
                    points_to_update.append(point)

            if len(points_to_update) >= 500:
                MarketPoint.objects.bulk_update(
                    points_to_update,
                    ["value", "change_percent", "metadata"],
                    batch_size=500,
                )
                points_to_update.clear()

        if points_to_update and not dry_run:
            MarketPoint.objects.bulk_update(
                points_to_update,
                ["value", "change_percent", "metadata"],
                batch_size=500,
            )

        if dry_run:
            transaction.set_rollback(True)
        else:
            cache.delete(LATEST_CACHE_KEY)

        mode = "SIMULAÇÃO" if dry_run else "CONCLUÍDO"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: {snapshots_changed} snapshots, "
                f"{quote_rows_changed} cotações em snapshots e "
                f"{points_changed} pontos históricos identificados."
            )
        )
