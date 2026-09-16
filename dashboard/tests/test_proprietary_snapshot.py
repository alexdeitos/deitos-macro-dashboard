from datetime import date, datetime
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from dashboard.models import ProprietaryAccount, PerformanceReport, PerformanceTrade
from dashboard.services.proprietary import evaluate_report

class ProprietarySnapshotTests(TestCase):
    def setUp(self):
        self.account = ProprietaryAccount.objects.create(name="MIDE TEST", plan_name="EXAME", max_loss=Decimal("3300"), approval_target=Decimal("5000"), max_contracts_day=20, mini_index_fee=Decimal("0.35"), mini_dollar_fee=Decimal("1.35"), start_date=date(2026,8,21))
    def report(self, name, results):
        r=PerformanceReport.objects.create(filename=name, total_rows=len(results))
        for i, result in enumerate(results,1):
            PerformanceTrade.objects.create(report=r, row_number=i, symbol="WINV26", opened_at=timezone.make_aware(datetime(2026,9,1,10,0,i)), buy_qty=1, sell_qty=1, result=Decimal(str(result)))
        return r
    def test_legacy_fee_values_are_normalized(self):
        from dashboard.services.proprietary import _trade_cost
        self.account.mini_index_fee = Decimal("35.00")
        self.account.mini_dollar_fee = Decimal("135.00")
        self.account.save(update_fields=["mini_index_fee", "mini_dollar_fee"])
        r=self.report("fees.csv", [100])
        trade=r.trades.first()
        self.assertEqual(_trade_cost(trade, self.account), Decimal("0.70"))

    def test_new_report_is_isolated_from_previous_report(self):
        e1=evaluate_report(self.account, self.report("r1.csv", [100, -50]))
        e2=evaluate_report(self.account, self.report("r2.csv", [20]))
        self.assertEqual(e1.current_result, Decimal("49.00"))
        self.assertEqual(e2.current_result, Decimal("19.30"))
        e1.refresh_from_db()
        self.assertFalse(e1.is_current)
        self.assertTrue(e2.is_current)
