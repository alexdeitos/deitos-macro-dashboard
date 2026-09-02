from datetime import datetime, timezone

from django.test import SimpleTestCase

from dashboard.services.opening import build_opening_analysis
from dashboard.services.types import Quote


def q(symbol, change, category="index"):
    return Quote(symbol=symbol, name=symbol, category=category, source="test", observed_at=datetime.now(timezone.utc), value=100.0, change_percent=change)


class OpeningAnalysisTests(SimpleTestCase):
    def test_win_negative_context_produces_sell_bias(self):
        quotes = [q("EWZ", -2.0, "etf"), q("DJI", -1.5), q("SP500", -1.0), q("NASDAQ", -1.0), q("EEM", -1.0, "etf"), q("DXY", 0.5, "currency_index"), q("VIX", 8.0, "volatility")]
        result = build_opening_analysis(quotes, {})
        self.assertLess(result["win"]["score"], -15)
        self.assertIn("vendedor", result["win"]["bias"])


    def test_dow_has_higher_weight_than_sp500_for_win(self):
        quotes = [
            q("DJI", 1.0),
            q("SP500", 1.0),
            q("NASDAQ", 1.0),
        ]
        result = build_opening_analysis(quotes, {})
        weights = {item["symbol"]: item["weight"] for item in result["win"]["components"]}
        self.assertGreater(weights["DJI"], weights["SP500"])

    def test_score_is_not_probability(self):
        result = build_opening_analysis([], {})
        self.assertIn("não uma probabilidade", result["disclaimer"])
