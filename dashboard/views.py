from __future__ import annotations

import uuid

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .models import CollectionRun
from .services.collector import MarketCollector
from .services.economic_calendar import TradingEconomicsCalendarCollector, calendar_payload
from .services.news import InvestingNewsCollector, news_payload
from .services.persistence import get_latest_payload, history_payload, persist_payload
from .services.remote_market import remote_market_enabled
import hmac
import os
REFRESH_LOCK_KEY = "market-dashboard:refresh-lock"


@ensure_csrf_cookie
@require_GET
def index(request):
    return render(request, "dashboard/index.html")

@require_GET
def api_public_market_snapshot(request):
    expected_token = os.getenv("PUBLIC_MARKET_API_TOKEN", "")
    received_token = request.headers.get("X-Market-Token", "")

    if not expected_token or not hmac.compare_digest(
        received_token,
        expected_token,
    ):
        return JsonResponse({"detail": "Unauthorized"}, status=401)

    payload = get_latest_payload()
    if payload is None:
        return JsonResponse(
            {"available": False, "detail": "Nenhuma coleta disponível."},
            status=503,
        )

    return JsonResponse(
        payload,
        json_dumps_params={"ensure_ascii": False},
    )
    
@require_GET
def validation(request):
    payload = get_latest_payload()
    return render(request, "dashboard/validation.html", {"payload": payload, "source_status": (payload or {}).get("source_status", {})})


@require_GET
def api_dashboard(request):
    payload = get_latest_payload()
    # No SQLite temporário da Vercel, a primeira instância pode nascer sem dados.
    # Quando o modo remoto está ativo, inicializa automaticamente usando o JSON local.
    if payload is None and remote_market_enabled():
        try:
            _sync_market_collection()
            payload = get_latest_payload()
        except Exception:
            payload = None
    if payload is None:
        return JsonResponse({"available": False, "message": "Ainda não existe uma coleta válida. Use o botão Atualizar.", "data_policy": "Nenhum valor de referência foi usado."}, status=503)
    response = dict(payload)
    response["available"] = True
    response["history"] = history_payload()
    return JsonResponse(response)


def _sync_market_collection() -> dict:
    run = CollectionRun.objects.create(task_id=f"vercel-{uuid.uuid4().hex[:12]}")
    try:
        payload = MarketCollector().collect()
        persist_payload(payload, run)
        run.status = CollectionRun.Status.SUCCESS if payload.get("is_complete") else CollectionRun.Status.PARTIAL
        run.source_status = payload.get("source_status", {})
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "source_status", "finished_at"])
        return {"status": run.status, "collected_at": payload["collected_at"]}
    except Exception as exc:
        run.status = CollectionRun.Status.FAILED
        run.error = str(exc)
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "finished_at"])
        raise


@require_POST
def api_refresh(request):
    if not cache.add(REFRESH_LOCK_KEY, "1", timeout=60):
        return JsonResponse({"accepted": False, "message": "Já existe uma atualização recente em andamento."}, status=429)
    try:
        result = _sync_market_collection()
        return JsonResponse({"accepted": True, "completed": True, "result": result})
    except Exception as exc:
        return JsonResponse({"accepted": False, "message": f"Falha na coleta: {exc}"}, status=503)
    finally:
        cache.delete(REFRESH_LOCK_KEY)


@require_GET
def api_task_status(request, task_id: str):
    return JsonResponse({"task_id": task_id, "state": "SUCCESS", "ready": True, "result": {"status": "completed"}})


@require_GET
def api_news(request):
    try:
        limit = int(request.GET.get("limit", "50"))
    except ValueError:
        limit = 50
    return JsonResponse(news_payload(limit=limit, market=request.GET.get("market", ""), category=request.GET.get("category", "")))


@require_POST
def api_refresh_news(request):
    try:
        result = InvestingNewsCollector().collect()
        return JsonResponse({"accepted": True, "completed": True, "result": result})
    except Exception as exc:
        return JsonResponse({"accepted": False, "message": f"Não foi possível atualizar as notícias: {exc}"}, status=503)


@require_GET
def api_calendar(request):
    try:
        days = int(request.GET.get("days", "7"))
    except ValueError:
        days = 7
    try:
        importance = int(request.GET.get("importance", "1"))
    except ValueError:
        importance = 1
    return JsonResponse(calendar_payload(days=days, country=request.GET.get("country", ""), min_importance=importance))


@require_POST
def api_refresh_calendar(request):
    try:
        result = TradingEconomicsCalendarCollector().collect()
        return JsonResponse({"accepted": True, "completed": True, "result": result})
    except Exception as exc:
        return JsonResponse({"accepted": False, "message": f"Não foi possível atualizar o calendário: {exc}"}, status=503)


@require_GET
def api_raw_snapshot(request):
    payload = get_latest_payload()
    if payload is None:
        return JsonResponse({"available": False}, status=404)
    return JsonResponse(payload)


@require_GET
def health(request):
    checks = {"database": False, "cache": False}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database"] = cursor.fetchone()[0] == 1
    except Exception:
        pass
    try:
        cache.set("healthcheck", "ok", timeout=5)
        checks["cache"] = cache.get("healthcheck") == "ok"
    except Exception:
        pass
    healthy = all(checks.values())
    return JsonResponse({"status": "ok" if healthy else "degraded", "checks": checks}, status=200 if healthy else 503)
