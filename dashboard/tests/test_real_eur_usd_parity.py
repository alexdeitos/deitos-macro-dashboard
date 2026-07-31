from datetime import datetime, timezone

from django.test import SimpleTestCase

from dashboard.services.collector import build_real_eur_usd_parity
from dashboard.services.types import Quote


class RealEurUsdParityTests(SimpleTestCase):
    def test_calculates_cross_rate_and_compounded_change(self):
        observed = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
        result = build_real_eur_usd_parity(
            [
                Quote(
                    symbol="EUR_BRL",
                    name="Euro / Real",
                    category="currency",
                    source="investing",
                    observed_at=observed,
                    value=6.12,
                    change_percent=1.0,
                ),
                Quote(
                    symbol="EUR_USD",
                    name="Euro / Dólar",
                    category="currency",
                    source="investing",
                    observed_at=observed,
                    value=1.20,
                    change_percent=0.5,
                ),
            ]
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.value, 5.10, places=8)
        self.assertAlmostEqual(result.change_percent, ((1.01 / 1.005) - 1) * 100, places=8)
        self.assertEqual(result.symbol, "REAL_EUR_USD_PARITY")

    def test_returns_none_when_a_leg_is_missing(self):
        observed = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
        result = build_real_eur_usd_parity(
            [
                Quote(
                    symbol="EUR_BRL",
                    name="Euro / Real",
                    category="currency",
                    source="investing",
                    observed_at=observed,
                    value=6.12,
                )
            ]
        )
        self.assertIsNone(result)
