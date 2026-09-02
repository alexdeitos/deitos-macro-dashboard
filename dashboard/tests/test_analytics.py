from datetime import datetime, timezone

from django.test import SimpleTestCase

from dashboard.services.analytics import build_market_analysis
from dashboard.services.types import Quote


class AnalyticsTests(SimpleTestCase):
    def test_missing_values_are_not_replaced(self):
        result = build_market_analysis([])
        self.assertIsNone(result["global"]["composite_change_percent"])
        self.assertEqual(result["global"]["direction"], "indisponível")

    def test_dow_is_primary_us_equity_weight(self):
        # Estrutura de pesos publicada pelo módulo; garante que o driver
        # americano escolhido para o contexto global continua sendo o Dow.
        quotes = [
            Quote(symbol="DJI", name="DJI", category="index", source="test", observed_at=datetime.now(timezone.utc), value=100.0, change_percent=1.0),
            Quote(symbol="SP500", name="SP500", category="index", source="test", observed_at=datetime.now(timezone.utc), value=100.0, change_percent=1.0),
        ]
        result = build_market_analysis(quotes)
        weights = {item["symbol"]: item["weight"] for item in result["global"]["components"]}
        self.assertGreater(weights["DJI"], weights["SP500"])

    def test_dxy_is_inverted_from_real_input(self):
        quote = Quote(
            symbol="DXY",
            name="DXY",
            category="currency_index",
            source="test",
            observed_at=datetime.now(timezone.utc),
            value=100.0,
            change_percent=1.0,
        )
        result = build_market_analysis([quote])
        component = result["global"]["components"][0]
        self.assertEqual(component["adjusted_change_percent"], -1.0)
