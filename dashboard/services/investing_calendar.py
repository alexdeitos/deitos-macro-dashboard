from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, time as dt_time
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from dashboard.models import EconomicEvent

from .investing_http import InvestingHttpClient
from .economic_calendar import parse_time_text, normalize_text, clean_text

logger = logging.getLogger(__name__)

INVESTING_CALENDAR_URL = "https://www.investing.com/economic-calendar"
CACHE_STATUS_KEY = "macro-dashboard:investing-daytrade-calendar:status"
CACHE_PAYLOAD_KEY = "macro-dashboard:investing-daytrade-calendar:payload"
CACHE_TTL = 55
ALLOWED_COUNTRIES = {"BR": "Brasil", "US": "Estados Unidos", "CN": "China"}
COUNTRY_NAMES = {
    "br": "BR", "brazil": "BR", "brasil": "BR",
    "us": "US", "usa": "US", "united states": "US", "united states of america": "US",
    "cn": "CN", "china": "CN", "cny": "CN",
}


def _country_from_row(row: Tag) -> str:
    candidates: list[str] = []
    for attr in ("data-country", "data-country-code", "data-currency", "currency"):
        if row.get(attr):
            candidates.append(str(row.get(attr)))
    for node in row.select('[title], [aria-label], [data-country], [data-country-code], [class*="country"], [class*="flag"]'):
        candidates.extend([str(node.get("title") or ""), str(node.get("aria-label") or ""), str(node.get("data-country") or ""), str(node.get("data-country-code") or "")])
        txt = clean_text(node.get_text(" ", strip=True))
        if txt:
            candidates.append(txt)
    for cell in row.find_all(["td", "th"], limit=4):
        candidates.append(clean_text(cell.get_text(" ", strip=True)))

    for candidate in candidates:
        normalized = normalize_text(candidate).replace("-", " ")
        if normalized in COUNTRY_NAMES:
            code = COUNTRY_NAMES[normalized]
            if code in ALLOWED_COUNTRIES:
                return code
        upper = clean_text(candidate).upper()
        if upper in ALLOWED_COUNTRIES:
            return upper
        if re.search(r"\b(?:USD|BRL)\b", upper):
            return "US" if "USD" in upper else "BR"
        if re.search(r"\bCNY\b", upper):
            return "CN"
    return ""


def _importance(row: Tag) -> int:
    for attr in ("data-importance", "data-impact", "importance", "data-volatility", "data-event-impact"):
        raw = clean_text(str(row.get(attr) or ""))
        if raw:
            match = re.search(r"([1-3])", raw)
            if match:
                return int(match.group(1))
            lowered = normalize_text(raw)
            if any(word in lowered for word in ("high", "alta", "alto")):
                return 3
            if any(word in lowered for word in ("medium", "moderate", "moderada", "moderado")):
                return 2
            if any(word in lowered for word in ("low", "baixa", "baixo")):
                return 1

    class_text = " ".join(row.get("class") or [])
    for pattern, level in (
        (r"(?:impact|importance|volatility)[-_ ]?3", 3),
        (r"(?:impact|importance|volatility)[-_ ]?2", 2),
        (r"(?:impact|importance|volatility)[-_ ]?1", 1),
        (r"high", 3),
        (r"medium|moderate", 2),
        (r"low", 1),
    ):
        if re.search(pattern, class_text, flags=re.I):
            return level

    # O Investing também representa a importância por três ícones/estrelas.
    star_nodes = row.select(
        '[class*="bullish"], [class*="importance"], [class*="impact"] i, [class*="impact"] svg, '
        '[title*="high" i], [title*="alta" i], [aria-label*="high" i], [aria-label*="alta" i]'
    )
    if len(star_nodes) >= 3:
        return 3
    if len(star_nodes) == 2:
        return 2
    if len(star_nodes) == 1:
        return 1
    return 1


def _text_by_field(row: Tag, names: tuple[str, ...]) -> str:
    for name in names:
        selectors = (
            f'[data-field="{name}"]',
            f'[id="{name}"]',
            f'[class*="{name}"]',
            f'td[data-test*="{name}"]',
        )
        for selector in selectors:
            node = row.select_one(selector)
            if node:
                value = clean_text(node.get_text(" ", strip=True))
                if value and value not in {"-", "—", "N/A"}:
                    return value
    return ""


def _event_name(row: Tag) -> tuple[str, str]:
    for selector in (
        'a[href*="economic-calendar"], a[href*="/economic-calendar/"], a[data-event-name]',
        '[data-event-name]',
    ):
        node = row.select_one(selector)
        if node:
            name = clean_text(str(node.get("data-event-name") or node.get_text(" ", strip=True)))
            href = clean_text(str(node.get("href") or ""))
            if name:
                return name, urljoin(INVESTING_CALENDAR_URL, href) if href else INVESTING_CALENDAR_URL

    # Fallback: o primeiro link textual substancial do row costuma ser o evento.
    for anchor in row.select("a[href]"):
        text = clean_text(anchor.get_text(" ", strip=True))
        href = clean_text(str(anchor.get("href") or ""))
        if len(text) >= 4 and href and not href.startswith(("#", "javascript:")):
            return text, urljoin(INVESTING_CALENDAR_URL, href)
    return "", INVESTING_CALENDAR_URL


def _row_date(row: Tag, fallback: date) -> date | None:
    for attr in ("data-date", "data-event-date", "data-datetime", "data-event-datetime", "datetime"):
        raw = clean_text(str(row.get(attr) or ""))
        if not raw:
            continue
        for candidate in (raw, raw.replace("Z", "+00:00")):
            try:
                return datetime.fromisoformat(candidate).date()
            except ValueError:
                pass
        match = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", raw)
        if match:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    return fallback


def _event_time(row: Tag) -> dt_time | None:
    for selector in (
        '[data-event-time]', '[data-field="time"]', '[class*="time"]', '[class*="date"]', 'time'
    ):
        node = row.select_one(selector)
        if node:
            raw = clean_text(str(node.get("data-event-time") or node.get_text(" ", strip=True)))
            parsed = parse_time_text(raw)
            if parsed:
                return parsed
    for cell in row.find_all(["td", "span"], limit=8):
        parsed = parse_time_text(cell.get_text(" ", strip=True))
        if parsed:
            return parsed
    return None


def _external_id(row: Tag, country: str, event_name: str, event_at: datetime) -> str:
    stable = str(row.get("data-event-id") or row.get("data-id") or row.get("id") or "")
    if not stable:
        stable = f"{country}|{event_at.isoformat()}|{event_name}|{row.get('data-url') or ''}"
    return "INV-" + hashlib.sha256(stable.encode("utf-8", errors="ignore")).hexdigest()


def parse_investing_calendar(html: str, *, target_date: date | None = None) -> list[dict[str, Any]]:
    target_date = target_date or timezone.localdate()
    soup = BeautifulSoup(html, "lxml")
    events: list[dict[str, Any]] = []
    current_date = target_date

    # Prefer rows that look like economic calendar events. If the site changes a
    # class name, the generic TR fallback keeps the parser usable.
    rows = soup.select('tr[data-event-id], tr[data-id], tr[class*="economic"], tr')
    seen: set[str] = set()
    for row in rows:
        header = row.select_one("th[colspan], td[colspan]")
        if header:
            text = clean_text(header.get_text(" ", strip=True))
            match = re.search(r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})\s+(20\d{2})", text, flags=re.I)
            if match:
                months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
                prefix = text.strip().lower()[:3]
                if prefix in months:
                    current_date = date(int(match.group(2)), months[prefix], int(match.group(1)))
            continue
        country = _country_from_row(row)
        if country not in ALLOWED_COUNTRIES:
            continue
        name, url = _event_name(row)
        if not name:
            continue
        event_date = _row_date(row, current_date)
        if event_date != target_date:
            continue
        event_time = _event_time(row)
        if event_time is None:
            continue
        event_at = datetime.combine(event_date, event_time, tzinfo=ZoneInfo(settings.TIME_ZONE))
        importance = _importance(row)
        if importance != 3:
            continue

        actual = _text_by_field(row, ("actual", "actualValue", "actual-value"))
        forecast = _text_by_field(row, ("forecast", "consensus", "consensusValue"))
        previous = _text_by_field(row, ("previous", "previousValue", "prev"))
        revised = _text_by_field(row, ("revised", "revisedValue"))
        reference = _text_by_field(row, ("reference",))
        category = _text_by_field(row, ("category", "event-category"))
        ext_id = _external_id(row, country, name, event_at)
        if ext_id in seen:
            continue
        seen.add(ext_id)
        events.append(
            {
                "external_id": ext_id,
                "event_at": event_at,
                "country": ALLOWED_COUNTRIES[country],
                "country_code": country,
                "category": category,
                "event": name,
                "reference": reference,
                "importance": importance,
                "actual": actual,
                "previous": previous,
                "revised": revised,
                "consensus": forecast,
                "forecast": forecast,
                "url": url,
                "metadata": {
                    "source": "Investing.com",
                    "target_date": target_date.isoformat(),
                    "importance_filter": 3,
                },
            }
        )
    events.sort(key=lambda item: item["event_at"])
    return events


def _upsert_events(events: list[dict[str, Any]]) -> int:
    created_or_updated = 0
    with transaction.atomic():
        for item in events:
            defaults = {key: value for key, value in item.items() if key != "external_id"}
            EconomicEvent.objects.update_or_create(external_id=item["external_id"], defaults=defaults)
            created_or_updated += 1
    return created_or_updated


def collect_investing_daytrade_calendar(*, force: bool = False) -> dict[str, Any]:
    if not force:
        cached = cache.get(CACHE_PAYLOAD_KEY)
        if cached:
            return cached
    if not getattr(settings, "INVESTING_ENABLED", True):
        payload = {"status": "disabled", "source": "Investing.com", "events": [], "date": timezone.localdate().isoformat()}
        cache.set(CACHE_PAYLOAD_KEY, payload, timeout=CACHE_TTL)
        return payload

    today = timezone.localdate()
    try:
        client = InvestingHttpClient()
        # A single current-day page is preferable to seven-day scraping: lower request
        # frequency, less rate-limit pressure, and exactly the user-requested scope.
        html = client.get_html(INVESTING_CALENDAR_URL, cache_ttl=0)
        events = parse_investing_calendar(html, target_date=today)
        saved = _upsert_events(events)
        status = {
            "status": "success",
            "date": today.isoformat(),
            "events_found": len(events),
            "events_saved": saved,
            "source": "Investing.com",
            "countries": ["BR", "US", "CN"],
            "importance": 3,
            "updated_at": timezone.now().isoformat(),
            "http_diagnostics": client.diagnostics.as_dict(),
        }
        cache.set(CACHE_STATUS_KEY, status, timeout=max(CACHE_TTL, 120))
        cache.set(CACHE_PAYLOAD_KEY, status, timeout=CACHE_TTL)
        return status
    except Exception as exc:
        logger.exception("Falha na coleta do calendário Investing para Daytrade")
        payload = {
            "status": "failed",
            "date": today.isoformat(),
            "events_found": 0,
            "events_saved": 0,
            "source": "Investing.com",
            "countries": ["BR", "US", "CN"],
            "importance": 3,
            "message": str(exc),
            "updated_at": timezone.now().isoformat(),
        }
        cache.set(CACHE_STATUS_KEY, payload, timeout=300)
        # Não apaga o último conjunto bom. A página pode continuar usando o cache/DB.
        return payload


def investing_daytrade_events(*, target_date: date | None = None) -> list[dict[str, Any]]:
    target_date = target_date or timezone.localdate()
    start = datetime.combine(target_date, dt_time.min, tzinfo=ZoneInfo(settings.TIME_ZONE))
    end = datetime.combine(target_date, dt_time.max, tzinfo=ZoneInfo(settings.TIME_ZONE))
    rows = EconomicEvent.objects.filter(
        event_at__gte=start,
        event_at__lte=end,
        country_code__in=["BR", "US", "CN"],
        importance=3,
        external_id__startswith="INV-",
    ).order_by("event_at", "country_code", "event")
    return [
        {
            "id": row.pk,
            "external_id": row.external_id,
            "event_at": timezone.localtime(row.event_at).isoformat(),
            "country": row.country,
            "country_code": row.country_code,
            "event": row.event,
            "category": row.category,
            "previous": row.previous,
            "forecast": row.forecast or row.consensus,
            "actual": row.actual,
            "revised": row.revised,
            "url": row.url,
            "importance": row.importance,
        }
        for row in rows
    ]
