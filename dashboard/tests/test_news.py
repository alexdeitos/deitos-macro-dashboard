from unittest.mock import Mock

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings

from dashboard.models import MarketNews
from dashboard.services.news import InvestingNewsCollector, classify_news, news_payload


class NewsClassifierTests(SimpleTestCase):
    def test_macro_dollar_headline_is_relevant_to_wdo(self):
        result = classify_news("Fed sinaliza juros altos e dólar avança contra o real", "indicadores")
        self.assertGreaterEqual(result.wdo_relevance, 70)
        self.assertIn("WDO", result.markets)
        self.assertIn("MACRO", result.markets)

    def test_brazilian_commodity_headline_is_relevant_to_win(self):
        result = classify_news("Vale sobe com minério de ferro e impulsiona o Ibovespa", "commodities")
        self.assertGreaterEqual(result.win_relevance, 70)
        self.assertIn("WIN", result.markets)

    def test_insider_sale_is_discarded(self):
        result = classify_news("Diretor vende US$ 10 milhões em ações da empresa", "acoes")
        self.assertEqual(result.relevance_score, 0)
        self.assertEqual(result.markets, [])


class FakeResponse:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.text = content.decode("utf-8", errors="ignore")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


RSS = b'''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Teste</title>
<item><guid>news-1</guid><title>Fed mantem juros e dolar avanca contra o real</title>
<link>https://br.investing.com/news/teste-1</link><pubDate>Thu, 16 Jul 2026 23:40:00 GMT</pubDate>
<description>Resumo da noticia.</description></item>
</channel></rss>'''


@override_settings(
    NEWS_RETENTION_DAYS=7,
    NEWS_REFRESH_SECONDS=300,
    NEWS_MIN_RELEVANCE=20,
    HTTP_CONNECT_TIMEOUT_SECONDS=1,
    NEWS_HTTP_TIMEOUT_SECONDS=1,
)
class NewsCollectorTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_feed_is_saved_without_duplication(self):
        session = FakeSession([FakeResponse(content=RSS), FakeResponse(content=RSS)])
        collector = InvestingNewsCollector(session=session)

        first = collector.collect_feed("indicadores", "https://example.test/feed.rss")
        second = collector.collect_feed("indicadores", "https://example.test/feed.rss")

        self.assertEqual(first["created"], 1)
        self.assertEqual(second["created"], 0)
        self.assertEqual(MarketNews.objects.count(), 1)
        item = MarketNews.objects.get()
        self.assertIn("WDO", item.markets)

    def test_not_modified_does_not_write(self):
        session = FakeSession([FakeResponse(status_code=304)])
        result = InvestingNewsCollector(session=session).collect_feed(
            "economia", "https://example.test/feed.rss"
        )
        self.assertEqual(result["status"], "not_modified")
        self.assertEqual(MarketNews.objects.count(), 0)

    def test_blocked_feed_stops_remaining_requests(self):
        session = FakeSession([FakeResponse(status_code=403)])
        result = InvestingNewsCollector(session=session).collect()
        self.assertEqual(len(session.calls), 1)
        self.assertEqual(result["feeds"]["moedas"]["status"], "blocked")
        self.assertEqual(result["feeds"]["commodities"]["status"], "skipped")

    def test_payload_returns_only_relevant_recent_news(self):
        collector = InvestingNewsCollector(session=FakeSession([FakeResponse(content=RSS)]))
        collector.collect_feed("indicadores", "https://example.test/feed.rss")
        payload = news_payload(limit=10)
        self.assertTrue(payload["available"])
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["source"], "Investing RSS")
