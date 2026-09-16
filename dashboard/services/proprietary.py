from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from datetime import date
from typing import Any

from django.db import transaction
from django.utils import timezone

from dashboard.models import ProprietaryAccount, ProprietaryEvaluation, PerformanceReport

D0 = Decimal("0")

DEFAULT_WIN_FEE = Decimal("0.35")
DEFAULT_WDO_FEE = Decimal("1.35")

def _normalized_fee(value: Any, default: Decimal) -> Decimal:
    """Normalize fee values while preserving legitimately entered amounts.

    Legacy versions of the UI could turn 0.35 into 35 and 1.35 into 135
    because the JavaScript decimal parser removed every dot. Values exactly
    35/135 are therefore treated as the known legacy representation.
    """
    fee = _decimal(value)
    if fee in (Decimal("35"), Decimal("135")):
        return fee / Decimal("100")
    return fee if fee >= D0 else default



def _money(v: Decimal) -> float:
    return float(v.quantize(Decimal("0.01")))

def _brl(v: Decimal) -> str:
    text = f"{_money(v):,.2f}"
    return "R$ " + text.replace(",", "X").replace(".", ",").replace("X", ".")

def _decimal(value: Any) -> Decimal:
    text = str(value if value is not None else "0").strip().replace("R$", "").replace(" ", "")
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".") if text.rfind(",") > text.rfind(".") else text.replace(",", "")
    else:
        text = text.replace(",", ".")
    return Decimal(text or "0")


def _instrument(t) -> str:
    symbol = (t.symbol or "").upper()
    if symbol.startswith("WIN"):
        return "WIN"
    if symbol.startswith("WDO"):
        return "WDO"
    return "OTHER"


def _trade_cost(t: Any, account: ProprietaryAccount) -> Decimal:
    # O Profit cobra a taxa operacional nas duas pontas da operação:
    # entrada + saída. Por isso, para cada trade, somamos a quantidade
    # executada na compra e na venda. Ex.: 2 WIN na entrada + 2 WIN na
    # saída = 4 contratos tarifados.
    contracts = max(int(t.buy_qty or 0), 0) + max(int(t.sell_qty or 0), 0)
    instrument = _instrument(t)
    if instrument == "WIN":
        return _normalized_fee(account.mini_index_fee, DEFAULT_WIN_FEE) * contracts
    if instrument == "WDO":
        return _normalized_fee(account.mini_dollar_fee, DEFAULT_WDO_FEE) * contracts
    return D0


def _evaluate_metrics(report: PerformanceReport, account: ProprietaryAccount) -> dict[str, Any]:
    all_trades = list(report.trades.all().order_by("opened_at", "id"))
    # O relatório do Profit pode conter operações anteriores ao início da conta.
    # A avaliação da mesa deve considerar somente o período do plano cadastrado.
    if account.start_date:
        trades = [
            t for t in all_trades
            if timezone.localtime(t.opened_at).date() >= account.start_date
        ]
    else:
        trades = all_trades
    gross_total = sum((t.result for t in trades), D0)
    operational_costs = sum((_trade_cost(t, account) for t in trades), D0)
    total = gross_total - operational_costs
    net_results = {t.id: t.result - _trade_cost(t, account) for t in trades}
    max_trade_loss = abs(min(net_results.values(), default=D0))
    daily = defaultdict(lambda: D0)
    daily_contracts = defaultdict(int)
    for t in trades:
        day = timezone.localtime(t.opened_at).date()
        daily[day] += net_results[t.id]
        daily_contracts[day] = max(daily_contracts[day], max(t.buy_qty or 0, t.sell_qty or 0))
    max_daily_loss = abs(min(daily.values(), default=D0))
    max_contracts = max(daily_contracts.values(), default=0)
    remaining_target = max(account.approval_target - total, D0)
    remaining_loss_buffer = max(account.max_loss + total, D0) if account.max_loss > D0 else D0
    target_reached = account.approval_target > D0 and total >= account.approval_target
    eliminated = account.max_loss > D0 and total <= -account.max_loss
    contract_ok = account.max_contracts_day <= 0 or max_contracts <= account.max_contracts_day
    # Controle interno de risco: uma única perda acima de 10% do limite total
    # ou um pior dia acima de 25% do limite total merece revisão.
    trade_ratio = (max_trade_loss / account.max_loss * 100) if account.max_loss > D0 else D0
    risk_ok = account.max_loss <= D0 or (max_trade_loss <= account.max_loss * Decimal("0.10") and max_daily_loss <= account.max_loss * Decimal("0.25"))
    performance_ok = total > D0 and not eliminated

    if eliminated:
        status = ProprietaryEvaluation.Status.ELIMINATED
    elif target_reached:
        status = ProprietaryEvaluation.Status.APPROVED
    elif not trades:
        status = ProprietaryEvaluation.Status.INVALID
    else:
        status = ProprietaryEvaluation.Status.IN_PROGRESS

    guidance: list[str] = []
    if eliminated:
        guidance.append("O resultado acumulado atingiu ou ultrapassou o limite máximo de perda informado. Pela regra configurada, a conta está eliminada.")
    elif target_reached:
        guidance.append("A meta de aprovação configurada foi atingida. Confira as regras formais da mesa antes de considerar a avaliação encerrada.")
    else:
        guidance.append(f"Faltam {_brl(remaining_target)} para a meta configurada.")
    if not contract_ok:
        guidance.append(f"Foram observados até {max_contracts} contratos no dia, acima do limite configurado de {account.max_contracts_day}.")
    if account.max_loss > D0 and max_trade_loss > account.max_loss * Decimal("0.10"):
        guidance.append(f"A maior perda individual representa {trade_ratio:.1f}% do limite total configurado; reduzir exposição por operação melhora a margem de segurança.")
    if account.max_loss > D0 and max_daily_loss > account.max_loss * Decimal("0.25"):
        guidance.append("O pior dia consumiu mais de 25% do limite total configurado; considere reduzir o risco diário e interromper após sequência adversa.")
    if total <= D0 and trades and not eliminated:
        guidance.append("O resultado líquido ainda está abaixo de zero; priorize consistência e preservação do limite antes de buscar aceleração da meta.")
    if gross_total > D0 and operational_costs > D0:
        cost_ratio = operational_costs / gross_total * Decimal("100")
        guidance.append(f"Os custos operacionais consumiram {cost_ratio:.1f}% do resultado bruto. O cálculo da meta, perda e margem usa o resultado líquido após custos.")
    if contract_ok and risk_ok and total > D0:
        guidance.append("O tamanho observado está dentro dos limites configurados e os indicadores internos de risco não apontaram excesso de concentração.")

    return {
        "status": status,
        "current_result": total,
        "gross_result": gross_total,
        "operational_costs": operational_costs,
        "remaining_to_target": remaining_target,
        "remaining_loss_buffer": remaining_loss_buffer,
        "max_daily_loss": max_daily_loss,
        "max_trade_loss": max_trade_loss,
        "max_contracts_observed": max_contracts,
        "trade_count": len(trades),
        "performance_ok": performance_ok,
        "contract_limit_ok": contract_ok,
        "risk_ok": risk_ok,
        "risk_ratio_percent": trade_ratio,
        "guidance": guidance,
        "metrics": {
            "period_start": account.start_date.isoformat() if account.start_date else None,
            "period_trade_count": len(trades),
            "excluded_before_start": max(len(all_trades) - len(trades), 0),
            "winning_trades": sum(1 for t in trades if net_results[t.id] > D0),
            "losing_trades": sum(1 for t in trades if net_results[t.id] < D0),
            "win_rate": round(sum(1 for t in trades if net_results[t.id] > D0) / len(trades) * 100, 1) if trades else 0,
            "best_day": _money(max(daily.values(), default=D0)),
            "worst_day": _money(min(daily.values(), default=D0)),
            "result_vs_starting_balance_percent": round(float(total / account.starting_balance * 100), 2) if account.starting_balance > D0 else None,
            "max_loss_vs_starting_balance_percent": round(float(account.max_loss / account.starting_balance * 100), 2) if account.starting_balance > D0 and account.max_loss > D0 else None,
            "profit_factor": round(float(sum((net_results[t.id] for t in trades if net_results[t.id] > D0), D0) / abs(sum((net_results[t.id] for t in trades if net_results[t.id] < D0), D0))), 2) if sum((net_results[t.id] for t in trades if net_results[t.id] < D0), D0) < D0 else None,
            "gross_result": _money(gross_total),
            "operational_costs": _money(operational_costs),
            "fee_config": {"WIN": _money(_normalized_fee(account.mini_index_fee, DEFAULT_WIN_FEE)), "WDO": _money(_normalized_fee(account.mini_dollar_fee, DEFAULT_WDO_FEE))},
        },
    }


def account_payload(account: ProprietaryAccount) -> dict[str, Any]:
    latest = account.evaluations.filter(is_current=True).order_by("-evaluated_at", "-id").first()
    return {
        "id": account.id,
        "name": account.name,
        "firm": account.firm,
        "plan_name": account.plan_name,
        "plan_value": _money(account.plan_value),
        "starting_balance": _money(account.starting_balance),
        "max_loss": _money(account.max_loss),
        "approval_target": _money(account.approval_target),
        "max_contracts_day": account.max_contracts_day,
        "start_date": account.start_date.isoformat() if account.start_date else "",
        "mini_index_fee": _money(account.mini_index_fee),
        "mini_dollar_fee": _money(account.mini_dollar_fee),
        "notes": account.notes,
        "is_active": account.is_active,
        "latest_evaluation_id": latest.id if latest else None,
    }


def evaluation_payload(e: ProprietaryEvaluation) -> dict[str, Any]:
    a = e.account
    return {
        "id": e.id,
        "account_id": a.id,
        "account": account_payload(a),
        "report_id": e.report_id,
        "report_filename": e.report.filename,
        "evaluated_at": e.evaluated_at.isoformat(),
        "status": e.status,
        "status_label": e.get_status_display(),
        "current_result": _money(e.current_result),
        "gross_result": _money(e.gross_result),
        "operational_costs": _money(e.operational_costs),
        "remaining_to_target": _money(e.remaining_to_target),
        "remaining_loss_buffer": _money(e.remaining_loss_buffer),
        "max_daily_loss": _money(e.max_daily_loss),
        "max_trade_loss": _money(e.max_trade_loss),
        "max_contracts_observed": e.max_contracts_observed,
        "trade_count": e.trade_count,
        "performance_ok": e.performance_ok,
        "contract_limit_ok": e.contract_limit_ok,
        "risk_ok": e.risk_ok,
        "risk_ratio_percent": _money(e.risk_ratio_percent),
        "guidance": e.guidance,
        "metrics": e.metrics,
    }


@transaction.atomic
def create_account(data: dict[str, Any]) -> ProprietaryAccount:
    return ProprietaryAccount.objects.create(
        name=str(data.get("name") or "").strip(),
        firm=str(data.get("firm") or "MIDE").strip(),
        plan_name=str(data.get("plan_name") or "").strip(),
        plan_value=_decimal(data.get("plan_value")),
        starting_balance=_decimal(data.get("starting_balance")),
        max_loss=_decimal(data.get("max_loss")),
        approval_target=_decimal(data.get("approval_target")),
        max_contracts_day=int(data.get("max_contracts_day") or 0),
        start_date=(date.fromisoformat(str(data.get("start_date")).strip()) if str(data.get("start_date") or "").strip() else None),
        mini_index_fee=_decimal(data.get("mini_index_fee")) if data.get("mini_index_fee") not in (None, "") else Decimal("0.35"),
        mini_dollar_fee=_decimal(data.get("mini_dollar_fee")) if data.get("mini_dollar_fee") not in (None, "") else Decimal("1.35"),
        notes=str(data.get("notes") or "").strip(),
    )


@transaction.atomic
def evaluate_report(account: ProprietaryAccount, report: PerformanceReport) -> ProprietaryEvaluation:
    """Evaluate only the freshly imported report as an isolated snapshot.

    Older evaluations remain in history but are never aggregated into the
    current result. The new evaluation becomes the single current snapshot.
    """
    ProprietaryEvaluation.objects.filter(account=account, is_current=True).update(is_current=False)
    m = _evaluate_metrics(report, account)
    metrics = dict(m["metrics"])
    metrics.update({"source_report_id": report.id, "source_report_filename": report.filename, "snapshot_only": True})
    return ProprietaryEvaluation.objects.create(
        account=account, report=report, status=m["status"],
        current_result=m["current_result"], gross_result=m["gross_result"],
        operational_costs=m["operational_costs"], remaining_to_target=m["remaining_to_target"],
        remaining_loss_buffer=m["remaining_loss_buffer"], max_daily_loss=m["max_daily_loss"],
        max_trade_loss=m["max_trade_loss"], max_contracts_observed=m["max_contracts_observed"],
        trade_count=m["trade_count"], performance_ok=m["performance_ok"],
        contract_limit_ok=m["contract_limit_ok"], risk_ok=m["risk_ok"],
        risk_ratio_percent=m["risk_ratio_percent"], guidance=m["guidance"],
        metrics=metrics, is_current=True,
    )
