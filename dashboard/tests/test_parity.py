from datetime import date, datetime, timezone

from django.test import SimpleTestCase

from dashboard.services.parity import build_dollar_parity
from dashboard.services.types import Quote


class ParityTests(SimpleTestCase):
    def quote(self, symbol, value):
        return Quote(
            symbol=symbol,
            name=symbol,
            category="test",
            source="test",
            observed_at=datetime.now(timezone.utc),
            value=value,
        )

    def test_does_not_create_reference_values(self):
        result = build_dollar_parity([], today=date(2026, 7, 12))
        self.assertIsNone(result["spot_points"])
        self.assertIsNone(result["theoretical_future_points"])
        self.assertFalse(result["theoretical_available"])

    def test_calculates_only_with_all_real_inputs(self):
        quotes = [
            self.quote("USD_BRL", 5.10),
            self.quote("DOL_FUT", 5120.0),
            self.quote("SELIC_252", 14.0),
            self.quote("US_1Y_YIELD", 4.5),
        ]
        result = build_dollar_parity(quotes, today=date(2026, 7, 12))
        self.assertTrue(result["theoretical_available"])
        self.assertIsNotNone(result["theoretical_future_points"])
