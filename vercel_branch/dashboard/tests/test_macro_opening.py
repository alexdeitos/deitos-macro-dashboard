from datetime import datetime, timezone

from django.test import SimpleTestCase

from dashboard.services.macro_opening import build_macro_opening_analysis
from dashboard.services.types import Quote


def q(symbol: str, change: float, category: str = "index") -> Quote:
    return Quote(
        symbol=symbol,
        name=symbol,
        category=category,
        source="test",
        observed_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
        value=100.0,
        change_percent=change,
    )


class MacroOpeningAnalysisTests(SimpleTestCase):
    def test_reference_formula_produces_negative_strong_score(self):
        result = build_macro_opening_analysis([
            q("VIX", 8.38, "volatility"),
            q("IRON_ORE", -0.81, "commodity"),
            q("WTI", 3.46, "commodity"),
        ])

        self.assertEqual(result["score"], -5.73)
        self.assertEqual(result["direction"], "negativa")
        self.assertEqual(result["opening_bias"], "abertura vendedora")
        self.assertEqual(result["strength"], "forte")

    def test_positive_score_produces_buyer_bias(self):
        result = build_macro_opening_analysis([
            q("VIX", -5.11, "volatility"),
            q("IRON_ORE", 0.15, "commodity"),
            q("WTI", 4.07, "commodity"),
        ])

        self.assertEqual(result["score"], 9.33)
        self.assertEqual(result["opening_bias"], "abertura compradora")
        self.assertEqual(result["strength"], "forte")

    def test_score_is_not_calculated_with_missing_component(self):
        result = build_macro_opening_analysis([
            q("VIX", -5.0, "volatility"),
            q("IRON_ORE", 0.2, "commodity"),
        ])

        self.assertIsNone(result["score"])
        self.assertIn("Petróleo WTI (CL1)", result["missing_components"])
        self.assertIn("Não é probabilidade", result["disclaimer"])

    def test_strength_bands_match_reference(self):
        lateral = build_macro_opening_analysis([
            q("VIX", 0.0, "volatility"),
            q("IRON_ORE", 0.5, "commodity"),
            q("WTI", 0.9, "commodity"),
        ])
        weak = build_macro_opening_analysis([
            q("VIX", 0.0, "volatility"),
            q("IRON_ORE", 0.8, "commodity"),
            q("WTI", 1.0, "commodity"),
        ])
        moderate = build_macro_opening_analysis([
            q("VIX", 0.0, "volatility"),
            q("IRON_ORE", 1.4, "commodity"),
            q("WTI", 1.6, "commodity"),
        ])

        self.assertEqual(lateral["strength"], "lateral")
        self.assertEqual(weak["strength"], "fraca")
        self.assertEqual(moderate["strength"], "moderada")
