from __future__ import annotations

import csv
import io
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from dashboard.models import PerformanceReport, PerformanceTrade, Trade, TradingAccount, TradeSetup
from dashboard.services.trade_diary import decimal_or_none


def _dec(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        text = str(value).strip().replace("R$", "").replace(" ", "")
        text = text.replace(".", "").replace(",", ".")
        return Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return None


def _date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _dt(value: str | None):
    if not value:
        return None
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            dt = datetime.strptime(value.strip(), fmt)
            return timezone.make_aware(dt, timezone.get_current_timezone())
        except ValueError:
            pass
    return None


def _int(value: Any) -> int:
    try:
        return int(str(value).strip() or 0)
    except (ValueError, TypeError):
        return 0


def _clean_header(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\ufeff", "").strip().lower())


def _detect_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:8])
    return ";" if sample.count(";") >= sample.count(",") else ","


def parse_performance_csv(uploaded) -> dict[str, Any]:
    raw = uploaded.read()
    if isinstance(raw, str):
        text = raw
    else:
        for enc in ("utf-8-sig", "latin1", "cp1252"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError("Não foi possível identificar a codificação do CSV.")

    delimiter = _detect_delimiter(text)
    lines = text.splitlines()
    meta: dict[str, Any] = {}
    header_idx = None
    for i, line in enumerate(lines):
        normalized = line.replace("\ufeff", "").lower()
        if "ativo;" in normalized or normalized.startswith("ativo,"):
            header_idx = i
            break
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip().lower()] = v.strip()
    if header_idx is None:
        raise ValueError("CSV de performance sem a coluna 'Ativo'.")

    reader = csv.DictReader(lines[header_idx:], delimiter=delimiter)
    rows = []
    for offset, raw_row in enumerate(reader, start=header_idx + 2):
        row = {_clean_header(k): (v or "").strip() for k, v in raw_row.items() if k}
        symbol = row.get("ativo", "").upper()
        opened = _dt(row.get("abertura"))
        if not symbol or opened is None:
            continue
        rows.append({
            "row_number": offset,
            "symbol": symbol,
            "opened_at": opened,
            "closed_at": _dt(row.get("fechamento")),
            "duration_label": row.get("tempo operação") or row.get("tempo operacao") or "",
            "buy_qty": _int(row.get("qtd compra")),
            "sell_qty": _int(row.get("qtd venda")),
            "side": row.get("lado", "").upper(),
            "buy_price": _dec(row.get("preço compra") or row.get("preco compra")),
            "sell_price": _dec(row.get("preço venda") or row.get("preco venda")),
            "market_price": _dec(row.get("preço de mercado") or row.get("preco de mercado")),
            "gross_interval": _dec(row.get("res. intervalo bruto") or row.get("res. intervalo bruta")),
            "gross_interval_pct": _dec(row.get("res. intervalo (%)")),
            "result": _dec(row.get("res. operação") or row.get("res. operacao")) or Decimal("0"),
            "result_pct": _dec(row.get("res. operação (%)") or row.get("res. operacao (%)")),
            "tet": row.get("tet", ""),
            "cumulative_total": _dec(row.get("total")),
            "raw": row,
        })

    return {
        "meta": meta,
        "rows": rows,
        "account_label": meta.get("conta", ""),
        "holder_label": meta.get("titular", ""),
        "period_start": _date(meta.get("data inicial")),
        "period_end": _date(meta.get("data final")),
    }


@transaction.atomic
def import_performance_report(uploaded) -> dict[str, Any]:
    parsed = parse_performance_csv(uploaded)
    rows = parsed["rows"]
    report = PerformanceReport.objects.create(
        filename=getattr(uploaded, "name", "relatorio performance.csv"),
        account_label=parsed["account_label"],
        holder_label=parsed["holder_label"],
        period_start=parsed["period_start"],
        period_end=parsed["period_end"],
        total_rows=len(rows),
        total_result=sum((r["result"] for r in rows), Decimal("0")),
        metadata={"source": "Profit Performance CSV", "meta": parsed["meta"]},
    )
    PerformanceTrade.objects.bulk_create([
        PerformanceTrade(report=report, row_number=r["row_number"], symbol=r["symbol"],
                         opened_at=r["opened_at"], closed_at=r["closed_at"],
                         duration_label=r["duration_label"], buy_qty=r["buy_qty"], sell_qty=r["sell_qty"],
                         side=r["side"], buy_price=r["buy_price"], sell_price=r["sell_price"],
                         market_price=r["market_price"], gross_interval=r["gross_interval"],
                         gross_interval_pct=r["gross_interval_pct"], result=r["result"],
                         result_pct=r["result_pct"], tet=r["tet"], cumulative_total=r["cumulative_total"],
                         metadata={"raw": r["raw"]})
        for r in rows
    ], batch_size=1000)
    return report_payload(report)


def _instrument(symbol: str) -> str:
    s = symbol.upper()
    if s.startswith("WDO"):
        return "WDO"
    if s.startswith("DOL"):
        return "DOL"
    if s.startswith("WIN"):
        return "WIN"
    if s.startswith("IND"):
        return "IND"
    return "OTHER"


def _direction(side: str) -> str:
    return "BUY" if side.upper().startswith("C") else "SELL"


def _default_account() -> TradingAccount:
    account = TradingAccount.objects.filter(is_default=True, is_active=True).first()
    return account or TradingAccount.objects.filter(is_active=True).first() or TradingAccount.objects.create(
        name="Conta principal", initial_capital=0, is_default=True
    )


def save_performance_trade_to_diary(perf: PerformanceTrade) -> Trade:
    account = _default_account()
    instrument = _instrument(perf.symbol)
    direction = _direction(perf.side)
    contracts = max(perf.buy_qty, perf.sell_qty, 1)
    entry = perf.buy_price if direction == "BUY" else perf.sell_price
    exit_price = perf.sell_price if direction == "BUY" else perf.buy_price
    if entry is None:
        entry = perf.sell_price or perf.buy_price
    if exit_price is None:
        exit_price = perf.market_price
    if entry is None:
        raise ValueError("Preço de entrada não disponível no relatório.")

    setup = TradeSetup.objects.filter(name="Importado do Profit", is_active=True).first()
    if setup is None:
        setup = TradeSetup.objects.create(name="Importado do Profit", description="Operação importada do relatório de performance do Profit.")

    technical = perf.justification.strip()
    execution = (
        f"Importado do relatório de performance do Profit. "
        f"Resultado reportado: R$ {perf.result:.2f}. "
        f"Duração: {perf.duration_label or 'N/D'}."
    )
    trade = Trade.objects.create(
        account=account,
        trade_date=perf.opened_at.date(),
        entry_time=perf.opened_at.timetz().replace(tzinfo=None),
        exit_time=perf.closed_at.timetz().replace(tzinfo=None) if perf.closed_at else None,
        instrument=instrument,
        symbol=perf.symbol,
        setup=setup,
        setup_label="Importado do Profit",
        direction=direction,
        contracts=contracts,
        entry_price=entry,
        exit_price=exit_price,
        point_value=Trade.default_point_value(instrument),
        financial_result_override=perf.result,
        technical_reading=technical,
        execution_notes=execution,
        discipline_score=perf.validation_score or 0,
        technical_quality=Trade.TechnicalQuality.UNRATED,
        followed_plan=None,
        opening_notes="Validação preenchida após importação do relatório Profit.",
    )
    perf.diary_trade = trade
    perf.save(update_fields=["diary_trade", "updated_at"])
    return trade


def report_payload(report: PerformanceReport) -> dict[str, Any]:
    rows = list(report.trades.all())
    results = [r.result for r in rows]
    wins = [x for x in results if x > 0]
    losses = [x for x in results if x < 0]
    gross_wins = sum(wins, Decimal("0"))
    gross_losses = sum(losses, Decimal("0"))
    by_instrument = {}
    for instrument, count in Counter(_instrument(r.symbol) for r in rows).items():
        subset = [r.result for r in rows if _instrument(r.symbol) == instrument]
        by_instrument[instrument] = {
            "trades": len(subset),
            "net": float(sum(subset, Decimal("0"))),
            "win_rate": round(sum(1 for x in subset if x > 0) / len(subset) * 100, 1) if subset else 0,
        }
    return {
        "id": report.id,
        "filename": report.filename,
        "account_label": report.account_label,
        "holder_label": report.holder_label,
        "period_start": report.period_start.isoformat() if report.period_start else None,
        "period_end": report.period_end.isoformat() if report.period_end else None,
        "imported_at": report.imported_at.isoformat(),
        "total_rows": len(rows),
        "total_result": float(sum(results, Decimal("0"))),
        "wins": len(wins),
        "losses": len(losses),
        "breakevens": sum(1 for x in results if x == 0),
        "win_rate": round(len(wins) / len(results) * 100, 1) if results else 0,
        "profit_factor": round(float(gross_wins / abs(gross_losses)), 2) if gross_losses < 0 else (99.0 if gross_wins > 0 else None),
        "average_trade": float(sum(results, Decimal("0")) / len(results)) if results else 0,
        "max_win": float(max(results)) if results else 0,
        "max_loss": float(min(results)) if results else 0,
        "by_instrument": by_instrument,
    }


def trade_payload(t: PerformanceTrade) -> dict[str, Any]:
    return {
        "id": t.id,
        "row_number": t.row_number,
        "symbol": t.symbol,
        "opened_at": t.opened_at.isoformat(),
        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        "duration_label": t.duration_label,
        "buy_qty": t.buy_qty,
        "sell_qty": t.sell_qty,
        "side": t.side,
        "side_label": "Compra" if t.side == "C" else "Venda" if t.side == "V" else "—",
        "entry_price": float(t.buy_price if t.side == "C" and t.buy_price is not None else t.sell_price) if (t.buy_price or t.sell_price) else None,
        "exit_price": float(t.sell_price if t.side == "C" and t.sell_price is not None else t.buy_price) if (t.buy_price or t.sell_price) else float(t.market_price) if t.market_price is not None else None,
        "buy_price": float(t.buy_price) if t.buy_price is not None else None,
        "sell_price": float(t.sell_price) if t.sell_price is not None else None,
        "market_price": float(t.market_price) if t.market_price is not None else None,
        "gross_interval": float(t.gross_interval) if t.gross_interval is not None else None,
        "gross_interval_pct": float(t.gross_interval_pct) if t.gross_interval_pct is not None else None,
        "result": float(t.result),
        "result_pct": float(t.result_pct) if t.result_pct is not None else None,
        "tet": t.tet,
        "cumulative_total": float(t.cumulative_total) if t.cumulative_total is not None else None,
        "justification": t.justification,
        "validation_score": t.validation_score,
        "setup_note": t.setup_note,
        "in_diary": bool(t.diary_trade_id),
        "diary_trade_id": t.diary_trade_id,
    }


def list_trades(report_id: int, limit: int = 500) -> list[dict[str, Any]]:
    qs = PerformanceTrade.objects.filter(report_id=report_id).order_by("-opened_at", "-id")[:limit]
    return [trade_payload(t) for t in qs]


@transaction.atomic
def update_validation(trade_id: int, justification: str, score: int, setup_note: str = "") -> dict[str, Any]:
    t = PerformanceTrade.objects.get(pk=trade_id)
    t.justification = justification.strip()
    t.validation_score = max(0, min(10, int(score or 0)))
    t.setup_note = setup_note.strip()
    t.save(update_fields=["justification", "validation_score", "setup_note", "updated_at"])
    return trade_payload(t)


@transaction.atomic
def save_and_link_diary(trade_id: int) -> dict[str, Any]:
    t = PerformanceTrade.objects.select_related("diary_trade").get(pk=trade_id)
    if t.diary_trade_id:
        return {"trade": trade_payload(t), "diary_trade_id": t.diary_trade_id, "created": False}
    diary = save_performance_trade_to_diary(t)
    return {"trade": trade_payload(t), "diary_trade_id": diary.id, "created": True}
