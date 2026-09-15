from __future__ import annotations

import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import CapturePoint
from .services.capture_analysis import build_index_radar
from .services.capture_import import import_workbook
from .services.performance_validation import (
    import_performance_report, list_trades, report_payload,
    update_validation, save_and_link_diary,
)
from .models import PerformanceReport, PerformanceTrade


@ensure_csrf_cookie
@require_GET
def index_radar(request):
    return render(request, "dashboard/index_radar.html")


@require_GET
def api_index_radar(request):
    return JsonResponse(build_index_radar(), json_dumps_params={"ensure_ascii": False})


@require_POST
def api_index_radar_refresh(request):
    return JsonResponse(build_index_radar(force=True), json_dumps_params={"ensure_ascii": False})


@require_POST
def api_import_captures(request):
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse({"ok": False, "message": "Envie o arquivo Excel no campo 'file'."}, status=400)
    try:
        result = import_workbook(uploaded)
        return JsonResponse({"ok": True, **result}, json_dumps_params={"ensure_ascii": False})
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)




@require_GET
def api_capture_status(request):
    from django.utils import timezone
    from datetime import timedelta

    latest = (
        CapturePoint.objects.filter(
            metadata__source="profit_excel_com",
            sheet_name="CONFIG_CAPTURA",
        )
        .order_by("-observed_at", "-id")
        .first()
    )
    if latest is None:
        return JsonResponse({
            "online": False,
            "status": "SEM_PONTE",
            "message": "Nenhuma captura ao vivo do Excel/Profit foi recebida.",
            "observed_at": None,
            "asset_count": 0,
        })
    age = max(0.0, (timezone.now() - latest.observed_at).total_seconds())
    asset_count = CapturePoint.objects.filter(
        metadata__source="profit_excel_com",
        sheet_name="CONFIG_CAPTURA",
        observed_at=latest.observed_at,
    ).count()
    return JsonResponse({
        "online": age <= 90,
        "status": "ONLINE" if age <= 90 else "ATRASADA",
        "message": "Ponte Windows COM conectada." if age <= 90 else "Última captura ao vivo está atrasada.",
        "observed_at": latest.observed_at.isoformat(),
        "age_seconds": round(age, 1),
        "asset_count": asset_count,
    })


@csrf_exempt
@require_POST
def api_ingest_captures(request):
    try:
        body = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"ok": False, "message": "JSON inválido."}, status=400)

    observed_at = body.get("observed_at")
    rows = body.get("rows", [])
    if not isinstance(rows, list) or not rows:
        return JsonResponse({"ok": False, "message": "O JSON precisa conter rows[]."}, status=400)

    from django.utils.dateparse import parse_datetime
    from django.utils import timezone

    dt = parse_datetime(str(observed_at)) if observed_at else timezone.now()
    if dt is None:
        dt = timezone.now()
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt)

    objects = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol", row.get("ativo", ""))).strip().upper()
        if not symbol:
            continue
        metadata = {
            k: v
            for k, v in row.items()
            if k not in {
                "symbol", "ativo", "sheet", "aba", "value", "ultimo",
                "change_percent", "variacao", "trades", "negocios", "volume"
            }
        }
        # The Windows bridge sends source=profit_excel_com. Keep the marker
        # explicit so the automatic file-sync task never overwrites live data
        # with stale workbook cache values.
        source = str(body.get("source") or metadata.get("source") or "").strip()
        if source:
            metadata["source"] = source
        objects.append(
            CapturePoint(
                observed_at=dt,
                sheet_name=str(row.get("sheet", row.get("aba", "EXCEL")))[:80],
                symbol=symbol[:40],
                value=row.get("value", row.get("ultimo")),
                change_percent=row.get("change_percent", row.get("variacao")),
                trades=row.get("trades", row.get("negocios")),
                volume=row.get("volume"),
                metadata=metadata,
            )
        )

    if not objects:
        return JsonResponse({"ok": False, "message": "Nenhum ativo válido foi encontrado."}, status=400)
    CapturePoint.objects.bulk_create(objects, batch_size=1000)
    # Invalidate both radar and daytrade caches immediately after a live bridge push.
    try:
        from django.core.cache import cache
        cache.delete("macro-dashboard:index-radar:v2")
        cache.delete("macro-dashboard:daytrade:v1")
    except Exception:
        pass
    return JsonResponse({"ok": True, "inserted": len(objects), "observed_at": dt.isoformat()})


@ensure_csrf_cookie
@require_GET
def operations_validation(request):
    return render(request, "dashboard/operations_validation.html")


@require_GET
def api_performance_latest(request):
    report = PerformanceReport.objects.first()
    if report is None:
        return JsonResponse({"available": False, "message": "Nenhum relatório Profit importado."}, status=404)
    payload = report_payload(report)
    payload["trades"] = list_trades(report.id)
    return JsonResponse({"available": True, "report": payload}, json_dumps_params={"ensure_ascii": False})


@require_POST
def api_performance_import(request):
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return JsonResponse({"ok": False, "message": "Envie o CSV do relatório de performance do Profit."}, status=400)
    try:
        report = import_performance_report(uploaded)
        report["trades"] = list_trades(report["id"])
        return JsonResponse({"ok": True, "report": report}, json_dumps_params={"ensure_ascii": False})
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)


@require_POST
def api_performance_validate(request, trade_id: int):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        result = update_validation(
            trade_id,
            str(payload.get("justification") or ""),
            int(payload.get("score") or 0),
            str(payload.get("setup_note") or ""),
        )
        return JsonResponse({"ok": True, "trade": result}, json_dumps_params={"ensure_ascii": False})
    except PerformanceTrade.DoesNotExist:
        return JsonResponse({"ok": False, "message": "Trade não encontrado."}, status=404)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)


@require_POST
def api_performance_save_diary(request, trade_id: int):
    try:
        result = save_and_link_diary(trade_id)
        return JsonResponse({"ok": True, **result}, json_dumps_params={"ensure_ascii": False})
    except PerformanceTrade.DoesNotExist:
        return JsonResponse({"ok": False, "message": "Trade não encontrado."}, status=404)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
