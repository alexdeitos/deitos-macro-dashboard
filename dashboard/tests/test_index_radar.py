from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from dashboard.models import CapturePoint
from dashboard.services.capture_analysis import build_index_radar


class IndexRadarTests(TestCase):
    def test_weighted_stock_pressure_uses_ibov_weights(self):
        now = timezone.now()
        CapturePoint.objects.bulk_create([
            CapturePoint(observed_at=now, sheet_name="Planilha1", symbol="IBOV", value=170000, change_percent=0.5),
            CapturePoint(observed_at=now, sheet_name="Planilha1", symbol="VALE3", value=100, change_percent=2.0),
            CapturePoint(observed_at=now, sheet_name="Planilha1", symbol="ITUB4", value=40, change_percent=-1.0),
            CapturePoint(observed_at=now, sheet_name="Planilha1", symbol="PETR4", value=40, change_percent=1.0),
            CapturePoint(observed_at=now, sheet_name="Planilha1", symbol="PETR3", value=40, change_percent=-0.5),
            CapturePoint(observed_at=now, sheet_name="Planilha1", symbol="AXIA3", value=30, change_percent=0.2),
        ])
        weights = {"VALE3": .5, "ITUB4": .2, "PETR4": .1, "PETR3": .1, "AXIA3": .1}
        with patch("dashboard.services.capture_analysis.get_ibov_weights", return_value={"weights": weights, "source": "test", "as_of": "test"}), \
             patch("dashboard.services.capture_analysis._external_latest", return_value={}):
            data = build_index_radar(force=True)
        self.assertTrue(data["available"])
        self.assertAlmostEqual(data["stock_pressure"]["weighted_change_percent"], 0.87, places=3)

    def test_empty_capture_is_not_fabricated(self):
        with patch("dashboard.services.capture_analysis.get_ibov_weights", return_value={"weights": {}, "source": "test", "as_of": "test"}), \
             patch("dashboard.services.capture_analysis._external_latest", return_value={}):
            data = build_index_radar(force=True)
        self.assertFalse(data["available"])
        self.assertEqual(data["direction"], "AGUARDAR")
