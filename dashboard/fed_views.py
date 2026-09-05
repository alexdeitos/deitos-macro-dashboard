from __future__ import annotations

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .services.fed_analysis import collect_fed_data


@ensure_csrf_cookie
@require_GET
def fed_analysis(request):
    return render(request, "dashboard/fed_analysis.html")


@require_GET
def api_fed_analysis(request):
    return JsonResponse(collect_fed_data(), json_dumps_params={"ensure_ascii": False})


@require_POST
def api_fed_refresh(request):
    return JsonResponse(collect_fed_data(force=True), json_dumps_params={"ensure_ascii": False})
