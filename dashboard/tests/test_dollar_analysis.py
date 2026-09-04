from datetime import date

from django.test import SimpleTestCase

from dashboard.services.dollar_analysis import DollarInputs, calculate_dollar_analysis


class DollarAnalysisTests(SimpleTestCase):
    def test_ptax_required_remaining_average_matches_four_fixing_target(self):
        result = calculate_dollar_analysis(
            DollarInputs(
                previous_ptax=5.18,
                ptax1=5.20,
                ptax2=5.21,
                target_ptax=5.22,
            )
        )
        self.assertAlmostEqual(result["ptax"]["required_remaining_average"], 5.235, places=6)
        self.assertEqual(result["ptax"]["known_count"], 2)
        self.assertEqual(result["ptax"]["remaining_count"], 2)

    def test_forward_uses_compounded_rate_differential(self):
        result = calculate_dollar_analysis(
            DollarInputs(
                spot_points=5180,
                future_points=5210,
                selic_percent=14.25,
                us_1y_percent=4.0,
                business_days=17,
            )
        )
        self.assertIsNotNone(result["forward"]["fair_forward_points"])
        self.assertGreater(result["forward"]["fair_forward_points"], 5180)

    def test_neutral_ptax_projection_carries_last_known_fixing(self):
        result = calculate_dollar_analysis(
            DollarInputs(previous_ptax=5.18, ptax1=5.205)
        )
        self.assertEqual(result["ptax"]["neutral_projection"], 5.205)
        self.assertAlmostEqual(result["ptax"]["vs_previous_points"], 25.0, places=6)
