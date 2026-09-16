from __future__ import annotations

from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from dashboard.services.bcb import fetch_selic_recent
from dashboard.services.sources import BancoCentralSource


class BCBSourceTests(SimpleTestCase):
    @patch("dashboard.services.bcb._session")
    def test_selic_uses_date_filtered_sgs_endpoint(self, mocked_session):
        session = Mock()
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = [{"data": "16/09/2026", "valor": "14.900000"}]
        response.url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1178/dados?dataInicial=07%2F09%2F2026&dataFinal=16%2F09%2F2026&formato=json"
        session.get.return_value = response
        mocked_session.return_value = session

        rows, diagnostics = fetch_selic_recent()
        self.assertEqual(rows[-1]["valor"], "14.900000")
        self.assertEqual(diagnostics["method"], "sgs_date_range")
        params = session.get.call_args.kwargs["params"]
        self.assertIn("dataInicial", params)
        self.assertIn("dataFinal", params)
        self.assertEqual(params["formato"], "json")

    @patch("dashboard.services.bcb._session")
    def test_selic_falls_back_to_official_portal_resource(self, mocked_session):
        session = Mock()
        primary = Mock()
        primary.raise_for_status.side_effect = RuntimeError("502")
        fallback = Mock()
        fallback.raise_for_status.return_value = None
        fallback.json.return_value = [{"data": "16/09/2026", "valor": "14.900000"}]
        fallback.url = "https://dadosabertos.bcb.gov.br/.../download"
        session.get.side_effect = [primary, fallback]
        mocked_session.return_value = session

        rows, diagnostics = fetch_selic_recent()
        self.assertEqual(rows[-1]["valor"], "14.900000")
        self.assertEqual(diagnostics["method"], "portal_resource_json")
        self.assertTrue(diagnostics["fallback"]["ok"])

    @patch("dashboard.services.sources.fetch_selic_recent")
    @patch("dashboard.services.sources.get_json")
    def test_bcb_source_retains_ptax_when_selic_fails(self, mocked_get_json, mocked_selic):
        mocked_selic.side_effect = RuntimeError("SGS indisponível")
        mocked_get_json.side_effect = [
            {"value": [{
                "dataHoraCotacao": "2026-09-16T13:00:00-03:00",
                "cotacaoCompra": 5.10,
                "cotacaoVenda": 5.11,
                "tipoBoletim": "Fechamento",
            }]}
        ]
        result = BancoCentralSource().fetch()
        self.assertFalse(any(q.symbol == "SELIC_252" for q in result.quotes))
        self.assertTrue(any(q.symbol == "PTAX_USD_BRL" for q in result.quotes))
        self.assertFalse(result.complete)
        self.assertIn("Selic:", result.error)
