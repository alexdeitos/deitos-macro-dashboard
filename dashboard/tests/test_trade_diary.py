from datetime import date, time
from decimal import Decimal

from django.test import TestCase

from dashboard.models import CapitalMovement, Trade, TradeExit, TradeSetup, TradingAccount
from dashboard.services.trade_diary import build_trade_analytics, calculate_trade


class TradeCalculationTests(TestCase):
    def setUp(self):
        self.account = TradingAccount.objects.create(name="Conta teste", initial_capital=Decimal("2000"))
        self.setup = TradeSetup.objects.create(name="Rompimento")

    def test_win_financial_calculation(self):
        trade = Trade.objects.create(
            account=self.account,
            trade_date=date(2026, 7, 17),
            entry_time=time(9, 5),
            exit_time=time(9, 10),
            instrument=Trade.Instrument.WIN,
            setup=self.setup,
            direction=Trade.Direction.BUY,
            contracts=2,
            entry_price=Decimal("130000"),
            exit_price=Decimal("130500"),
            fees=Decimal("2"),
        )
        result = calculate_trade(trade)
        self.assertEqual(result["result_points"], Decimal("500"))
        self.assertEqual(result["gross_result"], Decimal("200.00"))
        self.assertEqual(result["net_result"], Decimal("198.00"))

    def test_partial_exits_weighted_result(self):
        trade = Trade.objects.create(
            account=self.account,
            trade_date=date(2026, 7, 17),
            entry_time=time(10),
            instrument=Trade.Instrument.WDO,
            direction=Trade.Direction.SELL,
            contracts=2,
            entry_price=Decimal("5500"),
            fees=Decimal("1"),
        )
        TradeExit.objects.create(trade=trade, contracts=1, price=Decimal("5498"), fees=Decimal("0.5"))
        TradeExit.objects.create(trade=trade, contracts=1, price=Decimal("5496"), fees=Decimal("0.5"))
        result = calculate_trade(trade)
        self.assertEqual(result["result_points"], Decimal("3"))
        self.assertEqual(result["gross_result"], Decimal("60.00"))
        self.assertEqual(result["net_result"], Decimal("58.00"))
        self.assertEqual(result["status"], "closed")


class TradeAnalyticsTests(TestCase):
    def setUp(self):
        self.account = TradingAccount.objects.create(name="Conta analytics", initial_capital=Decimal("2000"))
        setup = TradeSetup.objects.create(name="Pullback")
        Trade.objects.create(
            account=self.account, trade_date=date(2026, 7, 16), entry_time=time(9), exit_time=time(9, 5),
            instrument="WIN", setup=setup, direction="BUY", contracts=1,
            entry_price=Decimal("100000"), exit_price=Decimal("100500"), followed_plan=True,
            had_relevant_news=True, opening_matched=True,
        )
        Trade.objects.create(
            account=self.account, trade_date=date(2026, 7, 17), entry_time=time(10), exit_time=time(10, 5),
            instrument="WIN", setup=setup, direction="BUY", contracts=1,
            entry_price=Decimal("100000"), exit_price=Decimal("99800"), followed_plan=False,
            had_relevant_news=False, opening_matched=False,
        )
        CapitalMovement.objects.create(
            account=self.account, movement_date=date(2026, 7, 15), kind="deposit", amount=Decimal("500")
        )

    def test_analytics_summary_and_breakdowns(self):
        payload = build_trade_analytics(self.account)
        self.assertEqual(payload["summary"]["trades"], 2)
        self.assertEqual(payload["summary"]["wins"], 1)
        self.assertEqual(payload["summary"]["losses"], 1)
        self.assertEqual(payload["summary"]["net_profit"], 60.0)
        self.assertEqual(payload["capital"]["current"], 2560.0)
        self.assertEqual(payload["breakdowns"]["setups"][0]["label"], "Pullback")


class TradeDiaryApiTests(TestCase):
    def setUp(self):
        self.account = TradingAccount.objects.create(name="Conta API", initial_capital=Decimal("1000"), is_default=True)

    def test_diary_page_and_trade_creation(self):
        self.assertEqual(self.client.get("/diario/").status_code, 200)
        response = self.client.post("/api/trade/trades/", {
            "account_id": self.account.id,
            "trade_date": "2026-07-17",
            "entry_time": "09:10",
            "exit_time": "09:15",
            "instrument": "WDO",
            "direction": "SELL",
            "contracts": "1",
            "entry_price": "5500",
            "exit_price": "5498",
            "setup_label": "Reversão",
            "fees": "1.50",
            "partial_exits": "[]",
            "had_relevant_news": "true",
            "news_impact": "high",
            "opening_matched": "true",
        })
        self.assertEqual(response.status_code, 201)
        item = response.json()["item"]
        self.assertEqual(item["net_result"], 18.5)
        self.assertTrue(item["had_relevant_news"])
        self.assertTrue(item["opening_matched"])

    def test_analytics_endpoint(self):
        response = self.client.get(f"/api/trade/analytics/?account={self.account.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("breakdowns", response.json())
