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

    def test_detects_days_above_fifty_percent_of_take_and_excess(self):
        # Take = 5.000; 50% = 2.500. Net daily gains after fees are used.
        r=PerformanceReport.objects.create(filename="50pct.csv", total_rows=3)
        day1=timezone.make_aware(datetime(2026,9,2,10,0,0))
        day2=timezone.make_aware(datetime(2026,9,3,10,0,0))
        PerformanceTrade.objects.create(report=r,row_number=1,symbol="WINV26",opened_at=day1,buy_qty=1,sell_qty=1,result=Decimal("3000"))
        PerformanceTrade.objects.create(report=r,row_number=2,symbol="WINV26",opened_at=day2,buy_qty=1,sell_qty=1,result=Decimal("1000"))
        e=evaluate_report(self.account,r)
        rule=e.metrics["fifty_percent_take_rule"]
        self.assertTrue(rule["violated"])
        self.assertEqual(rule["violation_count"],1)
        self.assertEqual(rule["violations"][0]["date"],"2026-09-02")
        self.assertEqual(rule["violations"][0]["excess"],499.3)
        self.assertEqual(rule["total_excess_to_earn_other_days"],499.3)
