from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from dashboard.models import CapturePoint
from dashboard.services.capture_analysis import build_index_radar


class PainelDirecionalProfitCaptureTests(TestCase):
    def setUp(self):
        now = timezone.now()
        for symbol, value, change, volume in [
            ("WINFUT", 188060.0, -0.2387, 54120000000),
            ("WDOFUT", 5167.5, -0.0670, 77176428640),
            ("IFNC", 19967.1, 0.8081, 2496545173),
            ("PETR4", 49.29, -2.2606, 1501007354),
            ("VALE3", 73.41, -1.5952, 2952507478),
            ("ITUB4", 42.55, -0.2812, 553330935),
            ("AXIA3", 55.44, 0.9109, 221585704),
        ]:
            CapturePoint.objects.create(
                observed_at=now,
                sheet_name="CONFIG_CAPTURA",
                symbol=symbol,
                value=value,
                change_percent=change,
                volume=volume,
                metadata={"variation_source": "profit_rtd_var"},
            )

    def test_contracts_are_exposed_from_profit_capture(self):
        result = build_index_radar(force=True)
        self.assertEqual(result["captured_instruments"]["WINFUT"]["value"], 188060.0)
        self.assertEqual(result["captured_instruments"]["WDOFUT"]["value"], 5167.5)
        self.assertAlmostEqual(result["captured_instruments"]["WINFUT"]["change_percent"], -0.2387, places=4)
        self.assertAlmostEqual(result["captured_instruments"]["WDOFUT"]["change_percent"], -0.0670, places=4)
        self.assertEqual(result["captured_instruments"]["IFNC"]["volume"], 2496545173)

    def test_ifnc_is_available_as_index_confirmation(self):
        result = build_index_radar(force=True)
        self.assertAlmostEqual(result["ifnc"]["change_percent"], 0.8081, places=4)
        self.assertIn("IFNC", " ".join(result["context"]))
