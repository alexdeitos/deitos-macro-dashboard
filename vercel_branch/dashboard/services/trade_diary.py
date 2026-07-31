from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from dashboard.models import (
    CapitalMovement,
    EconomicEvent,
    MarketNews,
    MarketSnapshot,
    Trade,
    TradingAccount,
)

ZERO = Decimal("0")


def decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(" ", "").replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None


def decimal_float(value: Decimal | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _direction_sign(trade: Trade) -> Decimal:
    return Decimal("1") if trade.direction == Trade.Direction.BUY else Decimal("-1")


def calculate_trade(trade: Trade) -> dict[str, Any]:
    sign = _direction_sign(trade)
    exits = list(trade.partial_exits.all())
    point_value = trade.point_value or Trade.default_point_value(trade.instrument)
    total_fees = trade.fees or ZERO
    weighted_points_total = ZERO
    exited_contracts = 0
    weighted_exit_price_total = ZERO
    last_exit_time = trade.exit_time

    if exits:
        for item in exits:
            contracts = max(int(item.contracts or 0), 0)
            if contracts <= 0:
                continue
            points = sign * (item.price - trade.entry_price)
            weighted_points_total += points * contracts
            weighted_exit_price_total += item.price * contracts
            exited_contracts += contracts
            total_fees += item.fees or ZERO
            if item.exit_time and (last_exit_time is None or item.exit_time > last_exit_time):
                last_exit_time = item.exit_time
        remaining_contracts = max(int(trade.contracts or 0) - exited_contracts, 0)
        if trade.exit_price is not None and remaining_contracts > 0:
            points = sign * (trade.exit_price - trade.entry_price)
            weighted_points_total += points * remaining_contracts
            weighted_exit_price_total += trade.exit_price * remaining_contracts
            exited_contracts += remaining_contracts
    elif trade.exit_price is not None:
        exited_contracts = int(trade.contracts or 0)
        points = sign * (trade.exit_price - trade.entry_price)
        weighted_points_total = points * exited_contracts
        weighted_exit_price_total = trade.exit_price * exited_contracts

    open_contracts = max(int(trade.contracts or 0) - exited_contracts, 0)
    average_points = weighted_points_total / exited_contracts if exited_contracts else None
    average_exit_price = weighted_exit_price_total / exited_contracts if exited_contracts else trade.exit_price
    gross_result = weighted_points_total * point_value if exited_contracts else None
    net_result = (
        trade.financial_result_override
        if trade.financial_result_override is not None
        else (gross_result - total_fees if gross_result is not None else None)
    )
    status = "open" if exited_contracts == 0 else ("partial" if open_contracts > 0 else "closed")
    outcome = "open"
    if net_result is not None:
        outcome = "win" if net_result > 0 else "loss" if net_result < 0 else "breakeven"

    risk_value = None
    risk_reward = None
    if trade.planned_stop_points is not None and trade.planned_stop_points > 0:
        risk_value = trade.planned_stop_points * point_value * Decimal(trade.contracts)
        if net_result is not None and risk_value:
            risk_reward = net_result / risk_value

    return {
        "status": status,
        "outcome": outcome,
        "exited_contracts": exited_contracts,
        "open_contracts": open_contracts,
        "average_exit_price": average_exit_price,
        "result_points": average_points,
        "gross_result": gross_result,
        "total_fees": total_fees,
        "net_result": net_result,
        "risk_value": risk_value,
        "risk_reward": risk_reward,
        "last_exit_time": last_exit_time,
    }


def serialize_trade(trade: Trade, include_context: bool = True) -> dict[str, Any]:
    calc = calculate_trade(trade)
    exits = [
        {
            "id": item.id,
            "exit_time": item.exit_time.isoformat(timespec="minutes") if item.exit_time else None,
            "contracts": item.contracts,
            "price": decimal_float(item.price, 4),
            "fees": decimal_float(item.fees),
            "notes": item.notes,
        }
        for item in trade.partial_exits.all()
    ]
    screenshot_url = trade.screenshot_url
    if trade.screenshot:
        screenshot_url = reverse("dashboard:trade_screenshot", kwargs={"trade_id": trade.id})
    payload = {
        "id": trade.id,
        "account_id": trade.account_id,
        "trade_date": trade.trade_date.isoformat(),
        "entry_time": trade.entry_time.isoformat(timespec="minutes"),
        "exit_time": trade.exit_time.isoformat(timespec="minutes") if trade.exit_time else None,
        "instrument": trade.instrument,
        "instrument_label": trade.get_instrument_display(),
        "symbol": trade.symbol,
        "setup_id": trade.setup_id,
        "setup": trade.setup_label or (trade.setup.name if trade.setup else "Sem setup"),
        "direction": trade.direction,
        "direction_label": trade.get_direction_display(),
        "contracts": trade.contracts,
        "entry_price": decimal_float(trade.entry_price, 4),
        "exit_price": decimal_float(trade.exit_price, 4),
        "point_value": decimal_float(trade.point_value, 4),
        "planned_stop_points": decimal_float(trade.planned_stop_points),
        "mae_points": decimal_float(trade.mae_points),
        "mfe_points": decimal_float(trade.mfe_points),
        "fees": decimal_float(trade.fees),
        "financial_result_override": decimal_float(trade.financial_result_override),
        "screenshot_url": screenshot_url,
        "technical_reading": trade.technical_reading,
        "execution_notes": trade.execution_notes,
        "emotions_before": trade.emotions_before or [],
        "emotions_after": trade.emotions_after or [],
        "discipline_score": trade.discipline_score,
        "technical_quality": trade.technical_quality,
        "technical_quality_label": trade.get_technical_quality_display(),
        "followed_plan": trade.followed_plan,
        "mistakes": trade.mistakes or [],
        "had_relevant_news": trade.had_relevant_news,
        "news_impact": trade.news_impact,
        "news_impact_label": trade.get_news_impact_display(),
        "news_notes": trade.news_notes,
        "linked_event_id": trade.linked_event_id,
        "opening_bias": trade.opening_bias,
        "opening_bias_label": trade.get_opening_bias_display(),
        "opening_score": decimal_float(trade.opening_score),
        "opening_matched": trade.opening_matched,
        "opening_notes": trade.opening_notes,
        "market_snapshot_id": trade.market_snapshot_id,
        "partial_exits": exits,
        "created_at": trade.created_at.isoformat(),
        "updated_at": trade.updated_at.isoformat(),
    }
    payload.update({
        "status": calc["status"],
        "outcome": calc["outcome"],
        "exited_contracts": calc["exited_contracts"],
        "open_contracts": calc["open_contracts"],
        "average_exit_price": decimal_float(calc["average_exit_price"], 4),
        "result_points": decimal_float(calc["result_points"]),
        "gross_result": decimal_float(calc["gross_result"]),
        "total_fees": decimal_float(calc["total_fees"]),
        "net_result": decimal_float(calc["net_result"]),
        "risk_value": decimal_float(calc["risk_value"]),
        "risk_reward": decimal_float(calc["risk_reward"]),
        "last_exit_time": calc["last_exit_time"].isoformat(timespec="minutes") if calc["last_exit_time"] else None,
    })
    if include_context and trade.linked_event:
        payload["linked_event"] = {
            "event_at": timezone.localtime(trade.linked_event.event_at).isoformat(),
            "country_code": trade.linked_event.country_code,
            "importance": trade.linked_event.importance,
            "event": trade.linked_event.event,
            "actual": trade.linked_event.actual,
            "consensus": trade.linked_event.consensus,
        }
    return payload


def infer_opening_context(trade_date: date, entry_time: time, instrument: str) -> dict[str, Any]:
    naive = datetime.combine(trade_date, entry_time)
    trade_at = timezone.make_aware(naive, timezone.get_current_timezone())
    snapshot = (
        MarketSnapshot.objects.filter(collected_at__date=trade_date, collected_at__lte=trade_at)
        .order_by("-collected_at")
        .first()
    )
    if snapshot is None:
        snapshot = MarketSnapshot.objects.filter(collected_at__date=trade_date).order_by("collected_at").first()

    key = "win" if instrument in {"WIN", "IND"} else "wdo" if instrument in {"WDO", "DOL"} else None
    side: dict[str, Any] = {}
    if snapshot and key:
        side = ((snapshot.payload or {}).get("opening_analysis") or {}).get(key) or {}
    score = decimal_or_none(side.get("score"))
    label = str(side.get("bias") or "")
    if "comprador" in label:
        bias = Trade.OpeningBias.BUY
    elif "vendedor" in label:
        bias = Trade.OpeningBias.SELL
    elif label:
        bias = Trade.OpeningBias.NEUTRAL
    else:
        bias = Trade.OpeningBias.UNKNOWN

    start = trade_at - timedelta(minutes=90)
    end = trade_at + timedelta(minutes=90)
    events = EconomicEvent.objects.filter(event_at__range=(start, end)).order_by("event_at", "-importance")[:20]
    day_events_count = EconomicEvent.objects.filter(event_at__date=trade_date).count()
    news_count = MarketNews.objects.filter(published_at__date=trade_date).count()
    return {
        "snapshot_id": snapshot.id if snapshot else None,
        "snapshot_collected_at": snapshot.collected_at.isoformat() if snapshot else None,
        "opening_score": decimal_float(score),
        "opening_bias": bias,
        "opening_bias_label": dict(Trade.OpeningBias.choices).get(bias),
        "opening_source_label": label or "Sem snapshot de abertura",
        "day_events_count": day_events_count,
        "market_news_count": news_count,
        "nearby_events": [
            {
                "id": event.id,
                "event_at": timezone.localtime(event.event_at).isoformat(),
                "country_code": event.country_code,
                "importance": event.importance,
                "event": event.event,
                "actual": event.actual,
                "consensus": event.consensus,
                "previous": event.previous,
            }
            for event in events
        ],
    }


def account_payload(account: TradingAccount) -> dict[str, Any]:
    analytics = build_trade_analytics(account)
    return {
        "id": account.id,
        "name": account.name,
        "broker": account.broker,
        "initial_capital": decimal_float(account.initial_capital),
        "current_capital": analytics["capital"]["current"],
        "net_profit": analytics["summary"]["net_profit"],
        "is_default": account.is_default,
        "is_active": account.is_active,
        "notes": account.notes,
    }


def _safe_pf(wins: Decimal, losses: Decimal) -> float | None:
    if losses < 0:
        return round(float(wins / abs(losses)), 2)
    return None if wins == 0 else 99.0


def _group_stats(rows: Iterable[dict[str, Any]], key_func) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[str(key_func(row))].append(row)
    output: list[dict[str, Any]] = []
    for label, items in groups.items():
        values = [item["net_decimal"] for item in items]
        wins = [value for value in values if value > 0]
        losses = [value for value in values if value < 0]
        points = [item["points_decimal"] for item in items if item["points_decimal"] is not None]
        output.append({
            "label": label,
            "trades": len(items),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(items) * 100, 1) if items else 0,
            "net_profit": decimal_float(sum(values, ZERO)),
            "avg_trade": decimal_float(sum(values, ZERO) / len(items)) if items else 0,
            "avg_points": decimal_float(sum(points, ZERO) / len(points)) if points else None,
            "profit_factor": _safe_pf(sum(wins, ZERO), sum(losses, ZERO)),
        })
    return sorted(output, key=lambda item: (item["net_profit"] or 0, item["trades"]), reverse=True)


def _parse_date_filter(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def build_trade_analytics(
    account: TradingAccount,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    queryset = (
        Trade.objects.filter(account=account)
        .select_related("setup", "linked_event")
        .prefetch_related("partial_exits")
        .order_by("trade_date", "entry_time", "id")
    )
    if start_date:
        queryset = queryset.filter(trade_date__gte=start_date)
    if end_date:
        queryset = queryset.filter(trade_date__lte=end_date)

    rows: list[dict[str, Any]] = []
    for trade in queryset:
        calc = calculate_trade(trade)
        if calc["net_result"] is None:
            continue
        rows.append({
            "trade": trade,
            "net_decimal": calc["net_result"],
            "points_decimal": calc["result_points"],
            "date": trade.trade_date,
            "hour": trade.entry_time.hour,
            "setup": trade.setup_label or (trade.setup.name if trade.setup else "Sem setup"),
            "instrument": trade.instrument,
            "direction": trade.get_direction_display(),
            "news": "Com notícia" if trade.had_relevant_news else "Sem notícia",
            "news_impact": trade.get_news_impact_display(),
            "opening": "Bateu" if trade.opening_matched is True else "Não bateu" if trade.opening_matched is False else "Não avaliado",
            "plan": "Seguiu o plano" if trade.followed_plan is True else "Fora do plano" if trade.followed_plan is False else "Não avaliado",
        })

    net_values = [row["net_decimal"] for row in rows]
    wins = [value for value in net_values if value > 0]
    losses = [value for value in net_values if value < 0]
    breakevens = [value for value in net_values if value == 0]
    net_profit = sum(net_values, ZERO)
    total = len(rows)

    movements_qs = CapitalMovement.objects.filter(account=account)
    if start_date:
        movements_qs = movements_qs.filter(movement_date__gte=start_date)
    if end_date:
        movements_qs = movements_qs.filter(movement_date__lte=end_date)
    movements = list(movements_qs)
    net_movements = sum((item.signed_amount for item in movements), ZERO)

    daily_pnl: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for row in rows:
        daily_pnl[row["date"]] += row["net_decimal"]
    daily_moves: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for item in movements:
        daily_moves[item.movement_date] += item.signed_amount

    dates = sorted(set(daily_pnl) | set(daily_moves))
    equity = account.initial_capital
    peak = equity
    max_drawdown = ZERO
    curve: list[dict[str, Any]] = []
    for current_date in dates:
        equity += daily_moves[current_date] + daily_pnl[current_date]
        peak = max(peak, equity)
        drawdown = equity - peak
        max_drawdown = min(max_drawdown, drawdown)
        curve.append({
            "date": current_date.isoformat(),
            "daily_pnl": decimal_float(daily_pnl[current_date]),
            "capital_movement": decimal_float(daily_moves[current_date]),
            "equity": decimal_float(equity),
            "drawdown": decimal_float(drawdown),
        })

    current_capital = account.initial_capital + net_movements + net_profit
    contributed_capital = account.initial_capital + sum(
        (item.amount for item in movements if item.kind in {CapitalMovement.Kind.DEPOSIT, CapitalMovement.Kind.ADJUSTMENT}),
        ZERO,
    )
    return_pct = (net_profit / contributed_capital * 100) if contributed_capital > 0 else None
    avg_win = sum(wins, ZERO) / len(wins) if wins else None
    avg_loss = sum(losses, ZERO) / len(losses) if losses else None
    expectancy = net_profit / total if total else None
    payoff = (avg_win / abs(avg_loss)) if avg_win is not None and avg_loss not in (None, ZERO) else None

    best_row = max(rows, key=lambda row: row["net_decimal"], default=None)
    worst_row = min(rows, key=lambda row: row["net_decimal"], default=None)
    best_points_row = max(
        (row for row in rows if row["points_decimal"] is not None),
        key=lambda row: row["points_decimal"],
        default=None,
    )

    max_win_streak = max_loss_streak = current_win = current_loss = 0
    for value in net_values:
        if value > 0:
            current_win += 1
            current_loss = 0
        elif value < 0:
            current_loss += 1
            current_win = 0
        else:
            current_win = current_loss = 0
        max_win_streak = max(max_win_streak, current_win)
        max_loss_streak = max(max_loss_streak, current_loss)

    day_stats = _group_stats(rows, lambda row: row["date"].isoformat())
    weekday_names = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    breakdowns = {
        "setups": _group_stats(rows, lambda row: row["setup"]),
        "hours": _group_stats(rows, lambda row: f'{row["hour"]:02d}:00'),
        "weekdays": _group_stats(rows, lambda row: weekday_names[row["date"].weekday()]),
        "instruments": _group_stats(rows, lambda row: row["instrument"]),
        "directions": _group_stats(rows, lambda row: row["direction"]),
        "news": _group_stats(rows, lambda row: row["news"]),
        "news_impact": _group_stats(rows, lambda row: row["news_impact"]),
        "opening": _group_stats(rows, lambda row: row["opening"]),
        "plan": _group_stats(rows, lambda row: row["plan"]),
        "days": day_stats,
    }

    def highlight(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        trade = row["trade"]
        return {
            "trade_id": trade.id,
            "date": trade.trade_date.isoformat(),
            "time": trade.entry_time.isoformat(timespec="minutes"),
            "instrument": trade.instrument,
            "setup": row["setup"],
            "net_result": decimal_float(row["net_decimal"]),
            "points": decimal_float(row["points_decimal"]),
        }

    closed_days = len(daily_pnl)
    positive_days = sum(1 for value in daily_pnl.values() if value > 0)
    negative_days = sum(1 for value in daily_pnl.values() if value < 0)
    return {
        "account": {"id": account.id, "name": account.name},
        "period": {
            "start": start_date.isoformat() if start_date else (rows[0]["date"].isoformat() if rows else None),
            "end": end_date.isoformat() if end_date else (rows[-1]["date"].isoformat() if rows else None),
        },
        "summary": {
            "trades": total,
            "wins": len(wins),
            "losses": len(losses),
            "breakevens": len(breakevens),
            "win_rate": round(len(wins) / total * 100, 1) if total else 0,
            "net_profit": decimal_float(net_profit),
            "gross_profit": decimal_float(sum(wins, ZERO)),
            "gross_loss": decimal_float(sum(losses, ZERO)),
            "profit_factor": _safe_pf(sum(wins, ZERO), sum(losses, ZERO)),
            "avg_trade": decimal_float(expectancy),
            "avg_win": decimal_float(avg_win),
            "avg_loss": decimal_float(avg_loss),
            "payoff": decimal_float(payoff),
            "max_drawdown": decimal_float(max_drawdown),
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak,
            "trading_days": closed_days,
            "positive_days": positive_days,
            "negative_days": negative_days,
            "positive_day_rate": round(positive_days / closed_days * 100, 1) if closed_days else 0,
        },
        "capital": {
            "initial": decimal_float(account.initial_capital),
            "movements": decimal_float(net_movements),
            "current": decimal_float(current_capital),
            "return_pct": decimal_float(return_pct),
        },
        "highlights": {
            "best_trade": highlight(best_row),
            "worst_trade": highlight(worst_row),
            "most_points": highlight(best_points_row),
            "best_setup": breakdowns["setups"][0] if breakdowns["setups"] else None,
            "best_hour": breakdowns["hours"][0] if breakdowns["hours"] else None,
            "best_day": breakdowns["days"][0] if breakdowns["days"] else None,
        },
        "curve": curve,
        "breakdowns": breakdowns,
    }


def parse_date_filter(value: str | None) -> date | None:
    return _parse_date_filter(value)
