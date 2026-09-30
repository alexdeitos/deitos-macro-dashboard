from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .services.ict_analysis import analyze_ict, analyze_ict_path


@ensure_csrf_cookie
@require_GET
def ict_analysis(request):
    return render(request, "dashboard/ict_analysis.html")


def _latest_ict_csv() -> Path | None:
    data_dir = Path(settings.BASE_DIR) / "data"
    candidates = [
        path
        for path in data_dir.glob("*.csv")
        if "WIN" in path.name.upper() and path.is_file()
    ]
    if not candidates:
        candidates = [path for path in data_dir.glob("*.csv") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"ok": False, "message": message}, status=status)


@require_GET
def api_ict_analysis_auto(request):
    selected_date = request.GET.get("date") or None
    path = _latest_ict_csv()
    if path is None:
        return _error("Nenhum CSV encontrado em data/. Coloque o CSV de 5 minutos do WIN em data/ ou use o upload manual.", 404)
    try:
        payload = analyze_ict_path(path, selected_date=selected_date)
        payload["source_file"] = path.name
        payload["source_mode"] = "data/"
        return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
    except Exception as exc:
        return _error(str(exc))


@require_POST
def api_ict_analysis(request):
    uploaded = request.FILES.get("file")
    selected_date = request.POST.get("date") or None
    if uploaded is None:
        return _error("Envie o CSV de candles de 5 minutos do Profit no campo 'file'.")
    try:
        payload = analyze_ict(uploaded, selected_date=selected_date)
        payload["source_file"] = uploaded.name
        payload["source_mode"] = "upload"
        return JsonResponse(payload, json_dumps_params={"ensure_ascii": False})
    except Exception as exc:
        return _error(str(exc))
