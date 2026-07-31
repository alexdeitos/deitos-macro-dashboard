from django.test import SimpleTestCase

from dashboard.services.parsing import (
    parse_number,
    parse_number_pt_br,
    parse_percent,
    reconcile_change_percent,
)


class ParseNumberTests(SimpleTestCase):
    def test_preserves_negative_sign_pt_br(self):
        self.assertEqual(parse_number("-0,26%"), -0.26)

    def test_preserves_unicode_minus(self):
        self.assertEqual(parse_number("−1,35"), -1.35)

    def test_parses_thousands_and_decimal(self):
        self.assertEqual(parse_number("5.133,33"), 5133.33)
        self.assertEqual(parse_number("5,133.33"), 5133.33)

    def test_investing_parenthesized_positive_percent_is_not_inverted(self):
        self.assertEqual(parse_percent("(+2,97%)"), 2.97)
        self.assertEqual(parse_percent("(2,97%)"), 2.97)

    def test_investing_parenthesized_negative_percent_stays_negative(self):
        self.assertEqual(parse_percent("(-2,97%)"), -2.97)
        self.assertEqual(parse_percent("(−2,97%)"), -2.97)

    def test_pt_br_index_value_uses_dot_as_thousands_separator(self):
        self.assertEqual(parse_number_pt_br("177.866"), 177866.0)
        self.assertEqual(parse_number_pt_br("5.133,33"), 5133.33)
        self.assertEqual(parse_number_pt_br("101,130"), 101.13)

    def test_reconciles_sign_when_price_change_has_same_magnitude(self):
        corrected, metadata = reconcile_change_percent(
            scraped_change=-2.97,
            value=177866,
            previous_close=172742,
        )
        self.assertAlmostEqual(corrected, 2.9663, places=3)
        self.assertTrue(metadata["change_corrected"])
        self.assertEqual(metadata["validation_status"], "corrected_sign_from_prices")

    def test_keeps_scraped_change_when_previous_close_is_incompatible(self):
        corrected, metadata = reconcile_change_percent(
            scraped_change=0.42,
            value=7575.39,
            previous_close=7575.25,
        )
        self.assertEqual(corrected, 0.42)
        self.assertFalse(metadata["change_corrected"])
        self.assertEqual(metadata["validation_status"], "price_reference_mismatch")
