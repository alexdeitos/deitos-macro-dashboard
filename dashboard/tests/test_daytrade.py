from datetime import date

from django.test import SimpleTestCase

from dashboard.services.investing_calendar import parse_investing_calendar
from dashboard.services.daytrade import _event_surprise


class InvestingDaytradeCalendarTests(SimpleTestCase):
    def test_parser_keeps_only_three_star_target_countries_and_today(self):
        html = '''
        <table>
          <tr data-event-id="a" data-country="BR" data-importance="3" data-datetime="2026-09-15T09:00:00">
            <td class="calendar-time">09:00</td><td><a data-event-name="IPCA">IPCA</a></td>
            <td data-field="previous">0,24%</td><td data-field="forecast">0,30%</td><td data-field="actual">0,28%</td>
          </tr>
          <tr data-event-id="b" data-country="US" data-importance="2" data-datetime="2026-09-15T10:00:00">
            <td class="calendar-time">10:00</td><td><a data-event-name="Retail Sales">Retail Sales</a></td>
          </tr>
          <tr data-event-id="c" data-country="CN" data-importance="3" data-datetime="2026-09-14T23:00:00">
            <td class="calendar-time">23:00</td><td><a data-event-name="PMI">PMI</a></td>
          </tr>
        </table>
        '''
        rows = parse_investing_calendar(html, target_date=date(2026, 9, 15))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["country_code"], "BR")
        self.assertEqual(rows[0]["importance"], 3)


class DaytradeEventAnalysisTests(SimpleTestCase):
    def test_inflation_above_consensus_is_negative_for_equity_context(self):
        event = {
            "event": "CPI",
            "category": "Inflation",
            "country_code": "US",
            "actual": "3.2%",
            "forecast": "3.0%",
            "previous": "3.1%",
        }
        result = _event_surprise(event)
        self.assertEqual(result["market_bias"], "NEGATIVO")
        self.assertEqual(result["status"], "DIVULGADO")

    def test_unreleased_event_does_not_invent_actual(self):
        event = {
            "event": "CPI",
            "category": "Inflation",
            "country_code": "US",
            "actual": "",
            "forecast": "3.0%",
            "previous": "3.1%",
        }
        result = _event_surprise(event)
        self.assertEqual(result["status"], "AGUARDANDO")
        self.assertIsNone(result["surprise"])
