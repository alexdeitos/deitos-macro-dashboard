from django.test import SimpleTestCase

from dashboard.services.win_opening import calculate_win_opening


class WinOpeningTests(SimpleTestCase):
    def test_positive_sp500_future_is_added_proportionally(self):
        result = calculate_win_opening(185693, 0.75)
        self.assertTrue(result["available"])
        self.assertAlmostEqual(result["value"], 187085.698, places=3)
        self.assertEqual(result["direction"], "alta")

    def test_negative_sp500_future_is_subtracted_proportionally(self):
        result = calculate_win_opening(185693, -0.75)
        self.assertAlmostEqual(result["value"], 184300.303, places=3)
        self.assertEqual(result["direction"], "baixa")

    def test_missing_inputs_do_not_fabricate_value(self):
        result = calculate_win_opening(None, -0.75)
        self.assertFalse(result["available"])
        self.assertIsNone(result["value"])
