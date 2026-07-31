from unittest.mock import Mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from dashboard.services.investing_http import (
    InvestingCircuitOpen,
    InvestingHttpClient,
    InvestingHttpError,
)


class FakeResponse:
    def __init__(self, status_code: int, text: str, headers: dict | None = None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("Nenhuma resposta fake restante")
        return self.responses.pop(0)

    def close(self):
        return None


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    INVESTING_HTTP_ATTEMPTS=2,
    INVESTING_REQUEST_MIN_DELAY_SECONDS=0,
    INVESTING_REQUEST_MAX_DELAY_SECONDS=0,
    INVESTING_RETRY_BACKOFF_SECONDS=0,
    INVESTING_CIRCUIT_COOLDOWN_SECONDS=300,
    INVESTING_MIN_HTML_BYTES=100,
)
class InvestingHttpClientTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_curl_uses_browser_headers_without_overriding_user_agent(self):
        html = "<html>" + ("x" * 200) + "</html>"
        session = FakeSession([FakeResponse(200, html, {"cf-ray": "test-GRU"})])
        client = InvestingHttpClient()
        client._curl_session = session

        result = client.get_html("https://br.investing.com/indices/bovespa")

        self.assertEqual(result, html)
        _, kwargs = session.calls[0]
        self.assertEqual(kwargs["impersonate"], "chrome")
        self.assertNotIn("User-Agent", kwargs["headers"])
        self.assertNotIn("sec-ch-ua", kwargs["headers"])

    def test_persistent_403_opens_circuit_and_stops_next_network_call(self):
        blocked = FakeResponse(403, "blocked", {"cf-ray": "blocked-GRU"})
        session = FakeSession([blocked, blocked])
        client = InvestingHttpClient()
        client._curl_session = session
        client._reset_curl_session = Mock()
        client._warm_up = Mock()

        with self.assertRaises(InvestingHttpError):
            client.get_html("https://br.investing.com/indices/bovespa")

        calls_after_block = len(session.calls)
        with self.assertRaises(InvestingCircuitOpen):
            client.get_html("https://br.investing.com/indices/us-spx-500")

        self.assertEqual(len(session.calls), calls_after_block)
        self.assertTrue(client.diagnostics.circuit_opened)
        self.assertEqual(client.diagnostics.blocked_responses, 2)

    def test_html_cache_avoids_second_request(self):
        html = "<html>" + ("cached" * 40) + "</html>"
        session = FakeSession([FakeResponse(200, html)])
        client = InvestingHttpClient()
        client._curl_session = session
        url = "https://br.investing.com/rates-bonds/usa-government-bonds"

        first = client.get_html(url, cache_ttl=600)
        second = client.get_html(url, cache_ttl=600)

        self.assertEqual(first, second)
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(client.diagnostics.cache_hits, 1)
