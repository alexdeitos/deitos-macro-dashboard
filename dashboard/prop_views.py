from __future__ import annotations
import json
from decimal import Decimal, InvalidOperation
from datetime import date
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from .models import ProprietaryAccount, ProprietaryEvaluation, PerformanceReport
from .services.proprietary import create_account, account_payload, evaluation_payload, evaluate_report
from .services.performance_validation import import_performance_report

def _decimal(value):
    text = str(value if value is not None else "0").strip().replace(" ", "")
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    return Decimal(text or "0")

@ensure_csrf_cookie
@require_GET
def proprietary_dashboard(request):
    return render(request, "dashboard/proprietary.html")

@require_GET
def api_proprietary_accounts(request):
    return JsonResponse({"accounts": [account_payload(a) for a in ProprietaryAccount.objects.all()]}, json_dumps_params={"ensure_ascii": False})

@require_POST
def api_proprietary_account_create(request):
    try:
        data=json.loads(request.body.decode("utf-8") or "{}")
        if not str(data.get("name") or "").strip():
            return JsonResponse({"ok":False,"message":"Informe o nome da conta."}, status=400)
        account=create_account(data)
        return JsonResponse({"ok":True,"account":account_payload(account)}, status=201, json_dumps_params={"ensure_ascii":False})
    except (InvalidOperation, ValueError, TypeError) as exc:
        return JsonResponse({"ok":False,"message":f"Valores inválidos: {exc}"}, status=400)
    except Exception as exc:
        return JsonResponse({"ok":False,"message":str(exc)}, status=400)

@require_POST
def api_proprietary_account_update(request, account_id: int):
    try:
        account = ProprietaryAccount.objects.get(pk=account_id)
        data = json.loads(request.body.decode("utf-8") or "{}")
        account.name = str(data.get("name") or account.name).strip()
        account.plan_name = str(data.get("plan_name") or "").strip()
        account.plan_value = _decimal(data.get("plan_value"))
        account.starting_balance = _decimal(data.get("starting_balance"))
        account.max_loss = _decimal(data.get("max_loss"))
        account.approval_target = _decimal(data.get("approval_target"))
        account.max_contracts_day = int(data.get("max_contracts_day") or 0)
        start_date = str(data.get("start_date") or "").strip()
        account.start_date = date.fromisoformat(start_date) if start_date else None
        account.mini_index_fee = _decimal(data.get("mini_index_fee"))
        account.mini_dollar_fee = _decimal(data.get("mini_dollar_fee"))
        account.notes = str(data.get("notes") or "").strip()
        account.save()
        return JsonResponse({"ok": True, "account": account_payload(account)}, json_dumps_params={"ensure_ascii": False})
    except ProprietaryAccount.DoesNotExist:
        return JsonResponse({"ok": False, "message": "Conta não encontrada."}, status=404)
    except Exception as exc:
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)

@require_POST
def api_proprietary_evaluate(request):
    uploaded=request.FILES.get("file")
    account_id=request.POST.get("account_id")
    if not uploaded:
        return JsonResponse({"ok":False,"message":"Envie o relatório de performance do Profit."}, status=400)
    try:
        account=ProprietaryAccount.objects.get(pk=int(account_id))
    except (ProprietaryAccount.DoesNotExist, TypeError, ValueError):
        return JsonResponse({"ok":False,"message":"Selecione uma conta/plano."}, status=400)
    try:
        report=import_performance_report(uploaded)
        report_obj=PerformanceReport.objects.get(pk=report["id"])
        evaluation=evaluate_report(account, report_obj)
        return JsonResponse({"ok":True,"evaluation":evaluation_payload(evaluation)}, json_dumps_params={"ensure_ascii":False})
    except Exception as exc:
        return JsonResponse({"ok":False,"message":str(exc)}, status=400)

@require_GET
def api_proprietary_latest(request, account_id: int):
    evaluation=ProprietaryEvaluation.objects.filter(account_id=account_id, is_current=True).select_related("account","report").order_by("-evaluated_at","-id").first()
    if not evaluation:
        return JsonResponse({"available":False,"message":"Nenhuma avaliação foi salva para esta conta."}, status=404)
    return JsonResponse({"available":True,"evaluation":evaluation_payload(evaluation)}, json_dumps_params={"ensure_ascii":False})

@require_GET
def api_proprietary_history(request, account_id: int):
    qs=ProprietaryEvaluation.objects.filter(account_id=account_id).select_related("account","report")[:30]
    return JsonResponse({"evaluations":[evaluation_payload(e) for e in qs]}, json_dumps_params={"ensure_ascii":False})
