from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .services.ict_analysis import analyze_ict


@ensure_csrf_cookie
@require_GET
def ict_analysis(request):
    return render(request, "dashboard/ict_analysis.html")


@require_POST
def api_ict_analysis(request):
    uploaded = request.FILES.get("file")
    selected_date = request.POST.get("date") or None
    if uploaded is None:
        return JsonResponse(
            {"ok": False, "message": "Envie o CSV de candles de 5 minutos do Profit no campo 'file'."},
            status=400,
        )
    try:
        payload = analyze_ict(uploaded, selected_date=selected_date)
        return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
    except Exception as exc:
        return JsonResponse(
            {"ok": False, "message": str(exc)},
            status=400,
        )
