from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .services.dollar_analysis import build_automatic_dollar_analysis
from .services.persistence import get_latest_payload


@require_GET
def dollar_analysis(request):
    return render(request, "dashboard/dollar_analysis.html")


@require_GET
def api_dollar_analysis(request):
    payload = get_latest_payload()
    if payload is None:
        return JsonResponse(
            {"available": False, "detail": "Nenhuma coleta disponível para análise do dólar."},
            status=503,
        )
    result = build_automatic_dollar_analysis(payload)
    return JsonResponse(result, json_dumps_params={"ensure_ascii": False})
