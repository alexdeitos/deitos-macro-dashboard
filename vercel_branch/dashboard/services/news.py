from __future__ import annotations

import calendar
import hashlib
import logging
import random
import time
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any

import feedparser
import requests
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from dashboard.models import MarketNews

logger = logging.getLogger(__name__)

NEWS_STATUS_CACHE_KEY = "market-dashboard:news:last-status"

INVESTING_RSS_FEEDS: dict[str, str] = {
    "moedas": "https://br.investing.com/rss/news_1.rss",
    "commodities": "https://br.investing.com/rss/news_11.rss",
    "acoes": "https://br.investing.com/rss/news_25.rss",
    "indicadores": "https://br.investing.com/rss/news_95.rss",
    "economia": "https://br.investing.com/rss/news_14.rss",
    "politica": "https://br.investing.com/rss/news_289.rss",
}

CATEGORY_LABELS = {
    "moedas": "Moedas",
    "commodities": "Commodities",
    "acoes": "Ações",
    "indicadores": "Indicadores",
    "economia": "Economia",
    "politica": "Política",
}

EXCLUDED_PHRASES = (
    "insider trading",
    "diretor vende",
    "executivo vende",
    "ceo vende",
    "presidente vende",
    "vende acoes",
    "compra acoes",
    "documentos da sec",
    "transcricao de resultados",
    "teleconferencia de resultados",
)

# tópico, termos, pontos WIN, pontos WDO
TOPIC_RULES: tuple[tuple[str, tuple[str, ...], int, int], ...] = (
    ("Fed e juros EUA", ("fed", "fomc", "powell", "treasury", "juros dos eua", "taxa de juros dos eua"), 18, 28),
    ("Inflação EUA", ("cpi", "pce", "ppi", "inflacao dos eua", "inflacao americana"), 16, 26),
    ("Emprego EUA", ("payroll", "nonfarm", "desemprego nos eua", "pedidos de seguro-desemprego"), 15, 24),
    ("Dólar e real", ("dolar", "real brasileiro", "usd/brl", "dxy", "indice dolar", "cambio"), 10, 32),
    ("Banco Central e Selic", ("banco central", "copom", "selic", "galipolo", "bc brasileiro"), 20, 28),
    ("Fiscal Brasil", ("fiscal", "arcabouco", "deficit", "divida publica", "fazenda", "haddad"), 28, 28),
    ("Ibovespa e B3", ("ibovespa", "b3", "bolsa brasileira", "acoes brasileiras"), 34, 8),
    ("Petrobras e petróleo", ("petrobras", "petroleo", "brent", "wti", "opep"), 28, 8),
    ("Vale e minério", ("vale", "minerio de ferro", "siderurgia"), 32, 5),
    ("China", ("china", "pequim", "economia chinesa", "pib chines"), 26, 12),
    ("Bancos brasileiros", ("itau", "bradesco", "banco do brasil", "santander brasil", "bancos brasileiros"), 26, 4),
    ("Emergentes", ("mercados emergentes", "emergentes", "fluxo estrangeiro"), 20, 20),
    ("Tarifas e sanções", ("tarifa", "tarifaco", "sancao", "guerra comercial"), 24, 24),
    ("Risco geopolítico", ("guerra", "conflito", "ataque", "oriente medio", "geopolit"), 18, 20),
    ("Brasil", ("brasil", "brasileiro", "lula", "congresso", "stf"), 16, 16),
)

BASE_RELEVANCE = {
    "moedas": (8, 28),
    "commodities": (18, 5),
    "acoes": (5, 0),
    "indicadores": (22, 24),
    "economia": (16, 18),
    "politica": (10, 12),
}


@dataclass(frozen=True)
class NewsClassification:
    relevance_score: int
    win_relevance: int
    wdo_relevance: int
    markets: list[str]
    topics: list[str]


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(without_accents.lower().split())


def classify_news(title: str, category: str) -> NewsClassification:
    normalized = normalize_text(title)
    if any(phrase in normalized for phrase in EXCLUDED_PHRASES):
        return NewsClassification(0, 0, 0, [], [])

    win_score, wdo_score = BASE_RELEVANCE.get(category, (0, 0))
    topics: list[str] = []

    for topic, aliases, win_points, wdo_points in TOPIC_RULES:
        if any(alias in normalized for alias in aliases):
            topics.append(topic)
            win_score += win_points
            wdo_score += wdo_points

    win_score = min(max(win_score, 0), 100)
    wdo_score = min(max(wdo_score, 0), 100)
    relevance = min(max(max(win_score, wdo_score), 0), 100)

    markets: list[str] = []
    if win_score >= 20:
        markets.append("WIN")
    if wdo_score >= 20:
        markets.append("WDO")
    if category in {"indicadores", "economia", "politica"}:
        markets.append("MACRO")

    return NewsClassification(
        relevance_score=relevance,
        win_relevance=win_score,
        wdo_relevance=wdo_score,
        markets=markets,
        topics=topics[:5],
    )


def clean_summary(value: str, max_length: int = 420) -> str:
    if not value:
        return ""
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    text = " ".join(text.split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"


def entry_datetime(entry: Any) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=dt_timezone.utc)
    return timezone.now()


def entry_external_id(entry: Any, category: str) -> str:
    stable_value = entry.get("id") or entry.get("guid") or entry.get("link")
    if not stable_value:
        stable_value = f"{category}|{entry.get('title', '')}|{entry.get('published', '')}"
    return hashlib.sha256(str(stable_value).encode("utf-8", errors="ignore")).hexdigest()


class InvestingNewsCollector:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.7",
                "User-Agent": "feedparser/6.0 (+https://github.com/kurtmckee/feedparser/)",
            }
        )

    @staticmethod
    def _cache_key(category: str, field: str) -> str:
        return f"market-dashboard:news:{category}:{field}"

    def _conditional_headers(self, category: str) -> dict[str, str]:
        headers: dict[str, str] = {}
        etag = cache.get(self._cache_key(category, "etag"))
        modified = cache.get(self._cache_key(category, "last-modified"))
        if etag:
            headers["If-None-Match"] = str(etag)
        if modified:
            headers["If-Modified-Since"] = str(modified)
        return headers

    def _remember_response_headers(self, category: str, response: requests.Response) -> None:
        ttl = max(int(getattr(settings, "NEWS_CACHE_METADATA_SECONDS", 86400)), 300)
        etag = response.headers.get("ETag")
        modified = response.headers.get("Last-Modified")
        if etag:
            cache.set(self._cache_key(category, "etag"), etag, ttl)
        if modified:
            cache.set(self._cache_key(category, "last-modified"), modified, ttl)

    def collect_feed(self, category: str, url: str) -> dict[str, Any]:
        response = self.session.get(
            url,
            headers=self._conditional_headers(category),
            timeout=(
                int(getattr(settings, "HTTP_CONNECT_TIMEOUT_SECONDS", 5)),
                int(getattr(settings, "NEWS_HTTP_TIMEOUT_SECONDS", 15)),
            ),
            allow_redirects=True,
        )

        if response.status_code == 304:
            return {"status": "not_modified", "created": 0, "updated": 0, "entries": 0}

        if response.status_code in {403, 429}:
            return {
                "status": "blocked",
                "http_status": response.status_code,
                "created": 0,
                "updated": 0,
                "entries": 0,
            }

        response.raise_for_status()
        self._remember_response_headers(category, response)

        parsed = feedparser.parse(response.content)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise ValueError(f"RSS inválido em {category}: {getattr(parsed, 'bozo_exception', 'erro desconhecido')}")

        created = 0
        updated = 0
        with transaction.atomic():
            for entry in parsed.entries:
                title = " ".join(str(entry.get("title", "")).split())
                url_value = str(entry.get("link", "")).strip()
                if not title or not url_value:
                    continue

                classification = classify_news(title, category)
                defaults = {
                    "source": "Investing RSS",
                    "title": title,
                    "summary": clean_summary(entry.get("summary", "")),
                    "url": url_value,
                    "category": category,
                    "published_at": entry_datetime(entry),
                    "relevance_score": classification.relevance_score,
                    "win_relevance": classification.win_relevance,
                    "wdo_relevance": classification.wdo_relevance,
                    "markets": classification.markets,
                    "topics": classification.topics,
                    "metadata": {
                        "feed_url": url,
                        "feed_category_label": CATEGORY_LABELS.get(category, category.title()),
                    },
                }
                _, was_created = MarketNews.objects.update_or_create(
                    external_id=entry_external_id(entry, category),
                    defaults=defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        return {
            "status": "ok",
            "http_status": response.status_code,
            "created": created,
            "updated": updated,
            "entries": len(parsed.entries),
        }

    def collect(self) -> dict[str, Any]:
        started_at = timezone.now()
        if not getattr(settings, "NEWS_ENABLED", True):
            result = {"status": "disabled", "started_at": started_at.isoformat(), "feeds": {}}
            cache.set(NEWS_STATUS_CACHE_KEY, result, timeout=3600)
            return result

        feed_status: dict[str, Any] = {}
        created = 0
        updated = 0
        successful = 0

        feed_items = list(INVESTING_RSS_FEEDS.items())
        for index, (category, url) in enumerate(feed_items):
            if index:
                time.sleep(random.uniform(0.35, 0.75))
            try:
                result = self.collect_feed(category, url)
            except Exception as exc:
                logger.warning("Falha no RSS da Investing (%s): %s", category, exc)
                result = {"status": "error", "error": str(exc), "created": 0, "updated": 0, "entries": 0}

            feed_status[category] = result
            created += int(result.get("created", 0))
            updated += int(result.get("updated", 0))
            if result.get("status") in {"ok", "not_modified"}:
                successful += 1

            error_text = normalize_text(str(result.get("error", "")))
            stop_reason = ""
            if result.get("status") == "blocked":
                stop_reason = f"HTTP {result.get('http_status')} no host da Investing"
            elif any(marker in error_text for marker in ("failed to resolve", "name resolution", "temporary failure in name resolution")):
                stop_reason = "falha de DNS/conectividade com o host da Investing"

            if stop_reason:
                for remaining_category, _ in feed_items[index + 1 :]:
                    feed_status[remaining_category] = {
                        "status": "skipped",
                        "reason": stop_reason,
                        "created": 0,
                        "updated": 0,
                        "entries": 0,
                    }
                break

        cutoff = timezone.now() - timedelta(days=max(int(getattr(settings, "NEWS_RETENTION_DAYS", 7)), 1))
        deleted, _ = MarketNews.objects.filter(published_at__lt=cutoff).delete()

        status = "success" if successful == len(INVESTING_RSS_FEEDS) else "partial" if successful else "failed"
        result = {
            "status": status,
            "started_at": started_at.isoformat(),
            "finished_at": timezone.now().isoformat(),
            "created": created,
            "updated": updated,
            "deleted": deleted,
            "successful_feeds": successful,
            "total_feeds": len(INVESTING_RSS_FEEDS),
            "feeds": feed_status,
        }
        cache.set(NEWS_STATUS_CACHE_KEY, result, timeout=max(int(getattr(settings, "NEWS_REFRESH_SECONDS", 300)) * 3, 900))
        return result


def news_payload(*, limit: int = 50, market: str = "", category: str = "") -> dict[str, Any]:
    max_limit = min(max(int(limit), 1), 100)
    minimum_relevance = max(int(getattr(settings, "NEWS_MIN_RELEVANCE", 20)), 0)
    hours = max(int(getattr(settings, "NEWS_DISPLAY_HOURS", 72)), 1)
    cutoff = timezone.now() - timedelta(hours=hours)

    queryset = MarketNews.objects.filter(
        published_at__gte=cutoff,
        relevance_score__gte=minimum_relevance,
    )

    normalized_market = market.upper().strip()
    if normalized_market == "WIN":
        queryset = queryset.filter(win_relevance__gte=20)
    elif normalized_market == "WDO":
        queryset = queryset.filter(wdo_relevance__gte=20)
    elif normalized_market == "MACRO":
        queryset = queryset.filter(category__in=["indicadores", "economia", "politica"])

    normalized_category = category.lower().strip()
    if normalized_category in INVESTING_RSS_FEEDS:
        queryset = queryset.filter(category=normalized_category)

    items = list(queryset.order_by("-published_at", "-relevance_score")[:max_limit])
    latest = MarketNews.objects.aggregate(latest=Max("collected_at"))["latest"]
    status = cache.get(NEWS_STATUS_CACHE_KEY) or {}

    return {
        "available": bool(items),
        "count": len(items),
        "last_collected_at": latest.isoformat() if latest else None,
        "collector_status": status,
        "minimum_relevance": minimum_relevance,
        "items": [
            {
                "id": item.pk,
                "source": item.source,
                "title": item.title,
                "summary": item.summary,
                "url": item.url,
                "category": item.category,
                "category_label": CATEGORY_LABELS.get(item.category, item.category.title()),
                "published_at": item.published_at.isoformat(),
                "relevance_score": item.relevance_score,
                "win_relevance": item.win_relevance,
                "wdo_relevance": item.wdo_relevance,
                "markets": item.markets,
                "topics": item.topics,
            }
            for item in items
        ],
    }
