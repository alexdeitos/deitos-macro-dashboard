from datetime import datetime, timezone

from django.test import SimpleTestCase

from dashboard.services.sources import InvestingSource


class InvestingInstrumentParserTests(SimpleTestCase):
    def test_positive_ibovespa_is_not_inverted_and_value_is_in_points(self):
        html = """
        <html><body>
          <div data-test="instrument-price-last">177.866</div>
          <div data-test="instrument-price-change-percent">(+2,97%)</div>
          <div data-test="instrument-high">178.120</div>
          <div data-test="instrument-low">172.900</div>
          <div data-test="prevClose">172.742</div>
        </body></html>
        """
        quote = InvestingSource._instrument_quote(
            html,
            symbol="IBOV",
            name="Ibovespa",
            category="index",
            source_url="https://br.investing.com/indices/bovespa",
            currency="points",
            observed_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
        )

        self.assertEqual(quote.value, 177866.0)
        self.assertEqual(quote.previous_close, 172742.0)
        self.assertAlmostEqual(quote.change_percent, 2.97, places=2)
        self.assertEqual(
            quote.raw["validation"]["validation_status"],
            "confirmed_by_prices",
        )

    def test_legacy_wrong_sign_is_corrected_when_prices_confirm_the_magnitude(self):
        html = """
        <html><body>
          <div data-test="instrument-price-last">177.866</div>
          <div data-test="instrument-price-change-percent">(-2,97%)</div>
          <div data-test="prevClose">172.742</div>
        </body></html>
        """
        quote = InvestingSource._instrument_quote(
            html,
            symbol="IBOV",
            name="Ibovespa",
            category="index",
            source_url="https://br.investing.com/indices/bovespa",
            currency="points",
            observed_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
        )

        self.assertGreater(quote.change_percent, 0)
        self.assertEqual(
            quote.raw["validation"]["validation_status"],
            "corrected_sign_from_prices",
        )
