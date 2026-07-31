from __future__ import annotations

import os
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from dashboard.services.remote_market import RemoteMarketError, fetch_remote_market_snapshot


class RemoteMarketTests(SimpleTestCase):
    @patch("dashboard.services.remote_market.requests.get")
    def test_fetches_direct_payload_and_preserves_collected_at(self, mocked_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "collected_at": "2099-07-30T13:00:00+00:00",
            "quotes": {"DXY": {"symbol": "DXY", "value": 100.0}},
            "quote_list": [{"symbol": "DXY", "value": 100.0}],
            "source_status": {},
        }
        mocked_get.return_value = response

        with patch.dict(
            os.environ,
            {
                "REMOTE_MARKET_JSON_URL": "https://example.test/api/raw/",
                "REMOTE_MARKET_JSON_TOKEN": "secret",
                "REMOTE_MARKET_MAX_AGE_SECONDS": "0",
            },
            clear=False,
        ):
            payload = fetch_remote_market_snapshot()

        self.assertEqual(payload["collected_at"], "2099-07-30T13:00:00+00:00")
        self.assertTrue(payload["source_status"]["remote_project"]["ok"])
        self.assertEqual(mocked_get.call_args.kwargs["headers"]["X-Market-Token"], "secret")

    @patch("dashboard.services.remote_market.requests.get")
    def test_rebuilds_quote_list_from_quotes(self, mocked_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "collected_at": "2099-07-30T13:00:00+00:00",
            "quotes": {"DXY": {"symbol": "DXY", "value": 100.0}},
        }
        mocked_get.return_value = response
        with patch.dict(
            os.environ,
            {
                "REMOTE_MARKET_JSON_URL": "https://example.test/api/raw/",
                "REMOTE_MARKET_MAX_AGE_SECONDS": "0",
            },
            clear=False,
        ):
            payload = fetch_remote_market_snapshot()
        self.assertEqual(len(payload["quote_list"]), 1)

    @patch("dashboard.services.remote_market.requests.get")
    def test_rejects_payload_without_quotes(self, mocked_get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"available": True}
        mocked_get.return_value = response
        with patch.dict(
            os.environ,
            {"REMOTE_MARKET_JSON_URL": "https://example.test/api/raw/"},
            clear=False,
        ):
            with self.assertRaises(RemoteMarketError):
                fetch_remote_market_snapshot()
