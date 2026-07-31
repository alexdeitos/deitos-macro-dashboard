from datetime import datetime
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from dashboard.models import EconomicEvent
from dashboard.services.economic_calendar import (
    TradingEconomicsCalendarCollector,
    calendar_payload,
    parse_calendar_html,
)

CALENDAR_HTML = '''
<html><body>
<table><tr><td>outra tabela</td></tr></table>
<table class="calendar-table">
  <thead class="table-header"><tr><th colspan="3">Friday July 17 2026</th></tr></thead>
  <tbody>
    <tr data-country="brazil" data-id="br-igp-10" data-category="Prices">
      <td><span class="calendar-date-3">11:00 AM</span></td>
      <td><div class="flag-br" title="Brazil"></div></td>
      <td><a class="calendar-event" href="/brazil/igp-10-inflation">IGP-10 Inflation MoM</a><span id="reference">JUL</span></td>
      <td><span id="actual">-1.1%</span></td><td><span id="previous">-0.30%</span></td>
      <td><span id="consensus">-0.99%</span></td><td><span id="forecast">-0.4%</span></td>
    </tr>
    <tr data-country="united-states" data-id="us-housing">
      <td><span class="calendar-date-2">12:30 PM</span></td>
      <td><div class="flag-us" title="United States"></div></td>
      <td><a class="calendar-event" href="/united-states/housing-starts">Housing Starts</a></td>
      <td><span id="actual">1.427M</span></td><td><span id="previous">1.199M</span></td>
      <td><span id="consensus">1.31M</span></td><td><span id="forecast">1.2M</span></td>
    </tr>
    <tr data-country="canada" data-id="ca-event">
      <td><span class="calendar-date-3">12:30 PM</span></td>
      <td><div class="flag-ca" title="Canada"></div></td>
      <td><a class="calendar-event" href="/canada/test">Canada Test</a></td>
    </tr>
  </tbody>
</table>
</body></html>
'''


@override_settings(
    ECONOMIC_CALENDAR_SOURCE_TIMEZONE="UTC",
    TIME_ZONE="America/Sao_Paulo",
    ECONOMIC_CALENDAR_COUNTRIES=["BR", "US", "CN", "EA"],
    ECONOMIC_CALENDAR_MIN_HTML_BYTES=100,
    ECONOMIC_CALENDAR_RETENTION_DAYS=14,
)
class CalendarParserTests(SimpleTestCase):
    def test_parser_extracts_fields_and_converts_utc_to_brasilia(self):
        events = parse_calendar_html(CALENDAR_HTML)
        self.assertEqual(len(events), 2)
        brazil = events[0]
        self.assertEqual(brazil["country_code"], "BR")
        self.assertEqual(brazil["importance"], 3)
        self.assertEqual(brazil["actual"], "-1.1%")
        self.assertEqual(brazil["consensus"], "-0.99%")
        self.assertEqual(brazil["forecast"], "-0.4%")
        self.assertEqual(brazil["event_at"].hour, 8)
        self.assertTrue(brazil["url"].endswith("/brazil/igp-10-inflation"))


class FakeResponse:
    def __init__(self, text=CALENDAR_HTML, status_code=200):
        self.text = text
        self.status_code = status_code
        self.headers = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, response=None):
        self.response = response or FakeResponse()
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


@override_settings(
    ECONOMIC_CALENDAR_ENABLED=True,
    ECONOMIC_CALENDAR_SOURCE_TIMEZONE="UTC",
    TIME_ZONE="America/Sao_Paulo",
    ECONOMIC_CALENDAR_COUNTRIES=["BR", "US", "CN", "EA"],
    ECONOMIC_CALENDAR_MIN_HTML_BYTES=100,
    ECONOMIC_CALENDAR_RETENTION_DAYS=14,
    ECONOMIC_CALENDAR_HTTP_TIMEOUT_SECONDS=1,
)
class CalendarCollectorTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_collector_saves_selected_countries_without_duplication(self):
        collector = TradingEconomicsCalendarCollector(session=FakeSession())
        first = collector.collect()
        second = collector.collect()
        self.assertEqual(first["status"], "success")
        self.assertEqual(first["created"], 2)
        self.assertEqual(second["created"], 0)
        self.assertEqual(EconomicEvent.objects.count(), 2)

    def test_payload_filters_importance_and_country(self):
        event_at = timezone.make_aware(datetime(2026, 7, 17, 9, 0))
        EconomicEvent.objects.create(
            external_id="a" * 64,
            event_at=event_at,
            country="Brasil",
            country_code="BR",
            event="IBC-BR Economic Activity",
            importance=3,
            actual="0.1%",
            consensus="0%",
            previous="0.5%",
        )
        with patch("dashboard.services.economic_calendar.timezone.now", return_value=event_at):
            payload = calendar_payload(days=1, country="BR", min_importance=3)
        self.assertTrue(payload["available"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["country_code"], "BR")
