from __future__ import annotations

import json
import mimetypes
from datetime import date, time
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

from django.db import transaction
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_http_methods

from .models import (
    CapitalMovement,
    EconomicEvent,
    Trade,
    TradeExit,
    TradeSetup,
    TradingAccount,
    TradingDay,
)
from .services.trade_diary import (
    account_payload,
    build_trade_analytics,
    decimal_or_none,
    infer_opening_context,
    parse_date_filter,
    serialize_trade,
)

MAX_SCREENSHOT_BYTES = 5 * 1024 * 1024
ALLOWED_SCREENSHOT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_SCREENSHOT_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _json_body(request) -> dict[str, Any]:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _source_data(request) -> dict[str, Any]:
    if request.content_type and request.content_type.startswith("application/json"):
        return _json_body(request)
    return request.POST.dict()


def _parse_bool(value: Any) -> bool | None:
    if value in (None, "", "null", "none", "unknown"):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "sim", "on"}:
        return True
    if text in {"0", "false", "no", "nao", "não", "off"}:
        return False
    return None


def _parse_list(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    try:
        parsed = json.loads(str(value))
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _parse_time(value: Any) -> time | None:
    if not value:
        return None
    try:
        return time.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _validate_screenshot(upload) -> str | None:
    if not upload:
        return None
    if upload.size > MAX_SCREENSHOT_BYTES:
        return "O print deve ter no máximo 5 MB."
    extension = Path(upload.name).suffix.lower()
    if extension not in ALLOWED_SCREENSHOT_EXTENSIONS:
        return "Formato inválido. Use JPG, PNG ou WEBP."
    content_type = getattr(upload, "content_type", "")
    if content_type and content_type not in ALLOWED_SCREENSHOT_TYPES:
        return "O arquivo enviado não é uma imagem válida."
    return None


def _ensure_defaults() -> TradingAccount:
    account = TradingAccount.objects.filter(is_default=True, is_active=True).first()
    if not account:
        account = TradingAccount.objects.filter(is_active=True).first()
    if not account:
        account = TradingAccount.objects.create(name="Conta principal", initial_capital=0, is_default=True)
    if not TradeSetup.objects.exists():
        for name in ["Rompimento", "Pullback", "Reversão", "Tendência", "Scalping", "Leitura de fluxo", "Price Action", "Outro"]:
            TradeSetup.objects.get_or_create(name=name)
    return account


@ensure_csrf_cookie
@require_GET
def trade_diary(request):
    account = _ensure_defaults()
    return render(request, "dashboard/trade_diary.html", {"default_account_id": account.id})


@require_http_methods(["GET", "POST"])
def api_trade_accounts(request):
    _ensure_defaults()
    if request.method == "GET":
        accounts = TradingAccount.objects.filter(is_active=True)
        return JsonResponse({"items": [account_payload(account) for account in accounts]})

    data = _source_data(request)
    name = str(data.get("name") or "").strip()
    if not name:
        return JsonResponse({"message": "Informe o nome da conta."}, status=400)
    initial_capital = decimal_or_none(data.get("initial_capital"))
    if initial_capital is None or initial_capital < 0:
        return JsonResponse({"message": "Capital inicial inválido."}, status=400)
    if TradingAccount.objects.filter(name__iexact=name).exists():
        return JsonResponse({"message": "Já existe uma conta com esse nome."}, status=409)
    make_default = _parse_bool(data.get("is_default")) is True
    with transaction.atomic():
        if make_default:
            TradingAccount.objects.update(is_default=False)
        account = TradingAccount.objects.create(
            name=name,
            broker=str(data.get("broker") or "").strip(),
            initial_capital=initial_capital,
            is_default=make_default,
            notes=str(data.get("notes") or "").strip(),
        )
    return JsonResponse({"item": account_payload(account)}, status=201)


@require_http_methods(["GET", "POST", "DELETE"])
def api_trade_account_detail(request, account_id: int):
    account = get_object_or_404(TradingAccount, pk=account_id)
    if request.method == "GET":
        return JsonResponse({"item": account_payload(account)})
    if request.method == "DELETE":
        if account.trades.exists() or account.capital_movements.exists():
            account.is_active = False
            account.is_default = False
            account.save(update_fields=["is_active", "is_default", "updated_at"])
        else:
            account.delete()
        return JsonResponse({"deleted": True})

    data = _source_data(request)
    name = str(data.get("name") or account.name).strip()
    if not name:
        return JsonResponse({"message": "Informe o nome da conta."}, status=400)
    duplicate = TradingAccount.objects.filter(name__iexact=name).exclude(pk=account.pk).exists()
    if duplicate:
        return JsonResponse({"message": "Já existe uma conta com esse nome."}, status=409)
    capital = decimal_or_none(data.get("initial_capital"))
    if capital is not None and capital < 0:
        return JsonResponse({"message": "Capital inicial inválido."}, status=400)
    with transaction.atomic():
        if _parse_bool(data.get("is_default")) is True:
            TradingAccount.objects.exclude(pk=account.pk).update(is_default=False)
            account.is_default = True
        account.name = name
        account.broker = str(data.get("broker") if "broker" in data else account.broker).strip()
        account.notes = str(data.get("notes") if "notes" in data else account.notes).strip()
        if capital is not None:
            account.initial_capital = capital
        account.save()
    return JsonResponse({"item": account_payload(account)})


@require_GET
def api_trade_setups(request):
    _ensure_defaults()
    items = TradeSetup.objects.filter(is_active=True).values("id", "name", "description")
    return JsonResponse({"items": list(items)})


@require_http_methods(["GET", "POST"])
def api_trades(request):
    if request.method == "GET":
        account_id = request.GET.get("account")
        trade_date = _parse_date(request.GET.get("date"))
        queryset = (
            Trade.objects.select_related("account", "setup", "linked_event")
            .prefetch_related("partial_exits")
            .order_by("entry_time", "id")
        )
        if account_id:
            queryset = queryset.filter(account_id=account_id)
        if trade_date:
            queryset = queryset.filter(trade_date=trade_date)
        return JsonResponse({"items": [serialize_trade(trade) for trade in queryset[:500]]})

    return _save_trade(request, None)


@require_http_methods(["GET", "POST", "DELETE"])
def api_trade_detail(request, trade_id: int):
    trade = get_object_or_404(
        Trade.objects.select_related("account", "setup", "linked_event").prefetch_related("partial_exits"),
        pk=trade_id,
    )
    if request.method == "GET":
        return JsonResponse({"item": serialize_trade(trade)})
    if request.method == "DELETE":
        if trade.screenshot:
            trade.screenshot.delete(save=False)
        trade.delete()
        return JsonResponse({"deleted": True})
    return _save_trade(request, trade)


def _save_trade(request, trade: Trade | None):
    data = _source_data(request)
    errors: list[str] = []
    account = TradingAccount.objects.filter(pk=data.get("account_id"), is_active=True).first()
    trade_date = _parse_date(data.get("trade_date"))
    entry_time = _parse_time(data.get("entry_time"))
    exit_time = _parse_time(data.get("exit_time"))
    instrument = str(data.get("instrument") or "").upper()
    direction = str(data.get("direction") or "").upper()
    entry_price = decimal_or_none(data.get("entry_price"))
    exit_price = decimal_or_none(data.get("exit_price"))
    contracts_raw = data.get("contracts")
    try:
        contracts = int(contracts_raw)
    except (TypeError, ValueError):
        contracts = 0

    if not account:
        errors.append("Conta inválida.")
    if not trade_date:
        errors.append("Data inválida.")
    if not entry_time:
        errors.append("Horário de entrada inválido.")
    if instrument not in dict(Trade.Instrument.choices):
        errors.append("Ativo inválido.")
    if direction not in dict(Trade.Direction.choices):
        errors.append("Direção inválida.")
    if contracts <= 0:
        errors.append("A quantidade de contratos deve ser maior que zero.")
    if entry_price is None or entry_price <= 0:
        errors.append("Preço de entrada inválido.")
    if exit_price is not None and exit_price <= 0:
        errors.append("Preço de saída inválido.")
    screenshot = request.FILES.get("screenshot")
    screenshot_url = str(data.get("screenshot_url") or "").strip()
    if screenshot_url and urlparse(screenshot_url).scheme not in {"http", "https"}:
        errors.append("A URL do print deve começar com http:// ou https://.")
    screenshot_error = _validate_screenshot(screenshot)
    if screenshot_error:
        errors.append(screenshot_error)
    if errors:
        return JsonResponse({"message": " ".join(errors), "errors": errors}, status=400)

    setup = TradeSetup.objects.filter(pk=data.get("setup_id"), is_active=True).first()
    linked_event = EconomicEvent.objects.filter(pk=data.get("linked_event_id")).first()
    context = infer_opening_context(trade_date, entry_time, instrument)
    point_value = decimal_or_none(data.get("point_value")) or Trade.default_point_value(instrument)
    discipline_score = min(max(int(data.get("discipline_score") or 0), 0), 10)
    technical_quality = str(data.get("technical_quality") or Trade.TechnicalQuality.UNRATED)
    if technical_quality not in dict(Trade.TechnicalQuality.choices):
        technical_quality = Trade.TechnicalQuality.UNRATED
    news_impact = str(data.get("news_impact") or Trade.NewsImpact.UNKNOWN)
    if news_impact not in dict(Trade.NewsImpact.choices):
        news_impact = Trade.NewsImpact.UNKNOWN
    opening_bias = str(data.get("opening_bias") or "")
    if opening_bias in {"", Trade.OpeningBias.UNKNOWN}:
        opening_bias = str(context.get("opening_bias") or Trade.OpeningBias.UNKNOWN)
    if opening_bias not in dict(Trade.OpeningBias.choices):
        opening_bias = Trade.OpeningBias.UNKNOWN

    partial_exits = data.get("partial_exits", "[]")
    if isinstance(partial_exits, str):
        try:
            partial_exits = json.loads(partial_exits or "[]")
        except json.JSONDecodeError:
            partial_exits = []
    if not isinstance(partial_exits, list):
        partial_exits = []

    with transaction.atomic():
        if trade is None:
            trade = Trade(account=account)
        trade.account = account
        trade.trade_date = trade_date
        trade.entry_time = entry_time
        trade.exit_time = exit_time
        trade.instrument = instrument
        trade.symbol = str(data.get("symbol") or "").strip()
        trade.setup = setup
        trade.setup_label = str(data.get("setup_label") or (setup.name if setup else "Outro")).strip()
        trade.direction = direction
        trade.contracts = contracts
        trade.entry_price = entry_price
        trade.exit_price = exit_price
        trade.point_value = point_value
        trade.planned_stop_points = decimal_or_none(data.get("planned_stop_points"))
        trade.mae_points = decimal_or_none(data.get("mae_points"))
        trade.mfe_points = decimal_or_none(data.get("mfe_points"))
        trade.fees = decimal_or_none(data.get("fees")) or Decimal("0")
        trade.financial_result_override = decimal_or_none(data.get("financial_result_override"))
        trade.screenshot_url = screenshot_url
        trade.technical_reading = str(data.get("technical_reading") or "").strip()
        trade.execution_notes = str(data.get("execution_notes") or "").strip()
        trade.emotions_before = _parse_list(data.get("emotions_before"))
        trade.emotions_after = _parse_list(data.get("emotions_after"))
        trade.discipline_score = discipline_score
        trade.technical_quality = technical_quality
        trade.followed_plan = _parse_bool(data.get("followed_plan"))
        trade.mistakes = _parse_list(data.get("mistakes"))
        trade.had_relevant_news = linked_event is not None or _parse_bool(data.get("had_relevant_news")) is True
        trade.news_impact = news_impact
        trade.news_notes = str(data.get("news_notes") or "").strip()
        trade.linked_event = linked_event
        trade.opening_bias = opening_bias
        trade.opening_score = decimal_or_none(data.get("opening_score"))
        if trade.opening_score is None:
            trade.opening_score = decimal_or_none(context.get("opening_score"))
        trade.opening_matched = _parse_bool(data.get("opening_matched"))
        trade.opening_notes = str(data.get("opening_notes") or "").strip()
        if context.get("snapshot_id"):
            trade.market_snapshot_id = context["snapshot_id"]
        if screenshot:
            if trade.screenshot:
                trade.screenshot.delete(save=False)
            trade.screenshot = screenshot
        trade.save()

        trade.partial_exits.all().delete()
        total_partial_contracts = 0
        for item in partial_exits:
            if not isinstance(item, dict):
                continue
            partial_price = decimal_or_none(item.get("price"))
            try:
                partial_contracts = int(item.get("contracts") or 0)
            except (TypeError, ValueError):
                partial_contracts = 0
            if partial_price is None or partial_price <= 0 or partial_contracts <= 0:
                continue
            total_partial_contracts += partial_contracts
            TradeExit.objects.create(
                trade=trade,
                exit_time=_parse_time(item.get("exit_time")),
                contracts=partial_contracts,
                price=partial_price,
                fees=decimal_or_none(item.get("fees")) or Decimal("0"),
                notes=str(item.get("notes") or "").strip(),
            )
        if total_partial_contracts > trade.contracts:
            transaction.set_rollback(True)
            return JsonResponse({"message": "As saídas parciais superam os contratos iniciais."}, status=400)

    trade = Trade.objects.select_related("account", "setup", "linked_event").prefetch_related("partial_exits").get(pk=trade.pk)
    return JsonResponse({"item": serialize_trade(trade)}, status=201 if request.path.endswith("/trades/") else 200)


@require_GET
def api_trade_context(request):
    trade_date = _parse_date(request.GET.get("date"))
    entry_time = _parse_time(request.GET.get("time"))
    instrument = str(request.GET.get("instrument") or "WIN").upper()
    if not trade_date or not entry_time:
        return JsonResponse({"message": "Informe data e horário válidos."}, status=400)
    return JsonResponse(infer_opening_context(trade_date, entry_time, instrument))


@require_http_methods(["GET", "POST"])
def api_trading_day(request):
    account = get_object_or_404(TradingAccount, pk=request.GET.get("account") or _source_data(request).get("account_id"))
    day_date = _parse_date(request.GET.get("date") or _source_data(request).get("date"))
    if not day_date:
        return JsonResponse({"message": "Data inválida."}, status=400)
    day, _ = TradingDay.objects.get_or_create(account=account, date=day_date)
    if request.method == "POST":
        data = _source_data(request)
        day.no_trade = _parse_bool(data.get("no_trade")) is True
        day.no_trade_reason = str(data.get("no_trade_reason") or "").strip()
        day.premarket_notes = str(data.get("premarket_notes") or "").strip()
        day.opening_plan = str(data.get("opening_plan") or "").strip()
        day.daily_review = str(data.get("daily_review") or "").strip()
        day.save()
    return JsonResponse({
        "item": {
            "id": day.id,
            "account_id": day.account_id,
            "date": day.date.isoformat(),
            "no_trade": day.no_trade,
            "no_trade_reason": day.no_trade_reason,
            "premarket_notes": day.premarket_notes,
            "opening_plan": day.opening_plan,
            "daily_review": day.daily_review,
        }
    })


@require_GET
def api_trade_analytics(request):
    account = get_object_or_404(TradingAccount, pk=request.GET.get("account"))
    return JsonResponse(build_trade_analytics(
        account,
        start_date=parse_date_filter(request.GET.get("start")),
        end_date=parse_date_filter(request.GET.get("end")),
    ))


@require_http_methods(["GET", "POST"])
def api_capital_movements(request):
    account_id = request.GET.get("account") or _source_data(request).get("account_id")
    account = get_object_or_404(TradingAccount, pk=account_id)
    if request.method == "POST":
        data = _source_data(request)
        movement_date = _parse_date(data.get("movement_date"))
        amount = decimal_or_none(data.get("amount"))
        kind = str(data.get("kind") or "")
        if not movement_date or amount is None or amount <= 0 or kind not in dict(CapitalMovement.Kind.choices):
            return JsonResponse({"message": "Movimentação de capital inválida."}, status=400)
        movement = CapitalMovement.objects.create(
            account=account,
            movement_date=movement_date,
            kind=kind,
            amount=amount,
            description=str(data.get("description") or "").strip(),
        )
        return JsonResponse({"item": _serialize_movement(movement)}, status=201)
    items = CapitalMovement.objects.filter(account=account)[:200]
    return JsonResponse({"items": [_serialize_movement(item) for item in items]})


def _serialize_movement(item: CapitalMovement) -> dict[str, Any]:
    return {
        "id": item.id,
        "movement_date": item.movement_date.isoformat(),
        "kind": item.kind,
        "kind_label": item.get_kind_display(),
        "amount": float(item.amount),
        "signed_amount": float(item.signed_amount),
        "description": item.description,
    }


@require_http_methods(["DELETE"])
def api_capital_movement_detail(request, movement_id: int):
    movement = get_object_or_404(CapitalMovement, pk=movement_id)
    movement.delete()
    return JsonResponse({"deleted": True})


@require_GET
def trade_screenshot(request, trade_id: int):
    trade = get_object_or_404(Trade, pk=trade_id)
    if not trade.screenshot:
        raise Http404("Print não encontrado.")
    try:
        return FileResponse(trade.screenshot.open("rb"), content_type=mimetypes.guess_type(trade.screenshot.name)[0] or "application/octet-stream")
    except FileNotFoundError as exc:
        raise Http404("Arquivo do print não encontrado.") from exc
