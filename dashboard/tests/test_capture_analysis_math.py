from django.test import TestCase
from django.utils import timezone

from dashboard.models import CapturePoint
from dashboard.services.capture_analysis import _weighted_stocks, _latest_capture_map


class CaptureAnalysisMathTests(TestCase):
    def test_petr4_contribution_is_raw_change_times_weight(self):
        now = timezone.now()
        point = CapturePoint.objects.create(
            observed_at=now,
            sheet_name="CONFIG_CAPTURA",
            symbol="PETR4",
            value=49.24,
            change_percent=-2.359706524,
            metadata={"source": "profit_excel_com"},
        )
        result = _weighted_stocks(
            {"PETR4": point},
            {"PETR4": 0.07999},
        )
        row = result["all"][0]
        self.assertAlmostEqual(row["change_percent"], -2.35971, places=4)
        self.assertAlmostEqual(row["weight_percent"], 7.999, places=3)
        self.assertAlmostEqual(row["contribution_percent"], -0.188751, places=5)
        self.assertAlmostEqual(result["index_contribution_percent"], -0.18875, places=4)

    def test_other_sheets_cannot_replace_config_capture(self):
        now = timezone.now()
        CapturePoint.objects.create(
            observed_at=now,
            sheet_name="OUTRA_ABA",
            symbol="PETR4",
            value=100,
            change_percent=50.0,
        )
        CapturePoint.objects.create(
            observed_at=now,
            sheet_name="CONFIG_CAPTURA",
            symbol="PETR4",
            value=49.24,
            change_percent=-2.0,
        )
        latest = _latest_capture_map()
        self.assertEqual(latest["PETR4"].sheet_name, "CONFIG_CAPTURA")
        self.assertEqual(latest["PETR4"].change_percent, -2.0)

    def test_config_capture_prefers_rtd_var_stored_in_metadata(self):
        now = timezone.now()
        point = CapturePoint.objects.create(
            observed_at=now,
            sheet_name="CONFIG_CAPTURA",
            symbol="PETR4",
            value=49.24,
            change_percent=0.05,  # legacy interval return (wrong for radar)
            metadata={"source": "CONFIG_CAPTURA", "rtD_field_c": "-2.280838658", "variation_source": "profit_rtd_var"},
        )
        result = _weighted_stocks({"PETR4": point}, {"PETR4": 0.08})
        self.assertAlmostEqual(result["all"][0]["change_percent"], -2.28084, places=4)
        self.assertAlmostEqual(result["all"][0]["contribution_percent"], -0.182467, places=5)
