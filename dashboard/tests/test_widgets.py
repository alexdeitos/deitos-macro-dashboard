from django.test import SimpleTestCase
from django.urls import reverse


class ExternalWidgetsTemplateTests(SimpleTestCase):
    def test_dashboard_contains_native_trading_economics_calendar(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn('id="calendarList"', html)
        self.assertIn("tradingeconomics.com/calendar", html)
        self.assertNotIn("sslecal2.investing.com", html)
        self.assertEqual(reverse("dashboard:api_calendar"), "/api/calendar/")

    def test_dashboard_contains_win_continuous_tradingview_chart(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8")
        self.assertIn("embed-widget-advanced-chart.js", html)
        self.assertIn("BMFBOVESPA:WIN1!", html)
        self.assertIn('"interval": "5"', html)
