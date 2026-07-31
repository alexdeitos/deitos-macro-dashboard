from __future__ import annotations

import hashlib
import logging
import random
import re
import time
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone as dt_timezone
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, Tag
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from dashboard.models import EconomicEvent

logger = logging.getLogger(__name__)

CALENDAR_URL = "https://tradingeconomics.com/calendar"
CALENDAR_STATUS_CACHE_KEY = "market-dashboard:economic-calendar:last-status"
CALENDAR_CIRCUIT_CACHE_KEY = "market-dashboard:economic-calendar:circuit"

COUNTRY_CODES = {
    "brazil": "BR",
    "brasil": "BR",
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "china": "CN",
    "euro area": "EA",
    "eurozone": "EA",
    "zona do euro": "EA",
}

COUNTRY_LABELS = {
    "BR": "Brasil",
    "US": "Estados Unidos",
    "CN": "China",
    "EA": "Zona do Euro",
}

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


class CalendarUnavailable(RuntimeError):
    pass


@dataclass(slots=True)
class CalendarDiagnostics:
    network_requests: int = 0
    retries: int = 0
    blocked_responses: int = 0
    fallback_requests: int = 0
    parsed_rows: int = 0
    selected_rows: int = 0
    circuit_opened: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "network_requests": self.network_requests,
            "retries": self.retries,
            "blocked_responses": self.blocked_responses,
            "fallback_requests": self.fallback_requests,
            "parsed_rows": self.parsed_rows,
            "selected_rows": self.selected_rows,
            "circuit_opened": self.circuit_opened,
        }


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    value = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(value.lower().split())


def clean_text(value: str | None) -> str:
    return " ".join((value or "").replace("\xa0", " ").split())


def parse_date_header(value: str) -> date | None:
    text = clean_text(value)
    normalized = normalize_text(text)
    # Ex.: Friday July 17 2026. O dia da semana é opcional.
    match = re.search(
        r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)?\s*"
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+"
        r"(\d{1,2})\s+(\d{4})",
        normalized,
    )
    if not match:
        return None
    return date(int(match.group(3)), MONTHS[match.group(1)], int(match.group(2)))


def parse_time_text(value: str) -> dt_time | None:
    text = clean_text(value).upper().replace(".", "")
    if not text or text in {"ALL DAY", "TENTATIVE", ""}:
        return None
    for pattern in ("%I:%M %p", "%I %p", "%H:%M"):
        try:
            return datetime.strptime(text, pattern).time()
        except ValueError:
            continue
    return None


def _country_from_row(row: Tag) -> tuple[str, str]:
    candidates: list[str] = []
    if row.get("data-country"):
        candidates.append(str(row.get("data-country")))

    flag = row.select_one('[class^="flag"], [class*=" flag"], [title][class*="flag"]')
    if flag:
        candidates.extend([str(flag.get("title") or ""), str(flag.get("aria-label") or "")])

    code_cell = row.select_one("td.calendar-country, td[data-country], [data-country-code]")
    if code_cell:
        candidates.extend([clean_text(code_cell.get_text(" ", strip=True)), str(code_cell.get("data-country-code") or "")])

    for candidate in candidates:
        normalized = normalize_text(candidate).replace("-", " ")
        if normalized in COUNTRY_CODES:
            code = COUNTRY_CODES[normalized]
            return code, COUNTRY_LABELS[code]
        upper = clean_text(candidate).upper()
        if upper in COUNTRY_LABELS:
            return upper, COUNTRY_LABELS[upper]
    return "", ""


def _field_text(row: Tag, name: str) -> str:
    selectors = (
        f'span[id="{name}"]',
        f'[data-field="{name}"]',
        f'.calendar-{name}',
        f'td.{name}',
        f'[class*="calendar-{name}"]',
    )
    for selector in selectors:
        node = row.select_one(selector)
        if node:
            value = clean_text(node.get_text(" ", strip=True))
            if value:
                return value
    return ""


def _importance(row: Tag) -> int:
    for attribute in ("data-importance", "data-impact", "importance"):
        raw = clean_text(str(row.get(attribute) or ""))
        match = re.search(r"([1-3])", raw)
        if match:
            return int(match.group(1))

    time_node = row.select_one('span[class^="calendar-date"], span[class*=" calendar-date"]')
    if time_node:
        class_text = " ".join(time_node.get("class") or [])
        match = re.search(r"calendar-date[-_ ]?([1-3])", class_text)
        if match:
            return int(match.group(1))

    class_text = " ".join(row.get("class") or [])
    for word, level in (("high", 3), ("medium", 2), ("low", 1)):
        if word in class_text.lower():
            return level

    icons = row.select('[class*="importance"] i, [class*="importance"] svg, [title*="importance" i]')
    if icons:
        return min(len(icons), 3)
    return 1


def _event_node(row: Tag) -> Tag | None:
    preferred = (
        row.select_one("a.calendar-event")
        or row.select_one('a[data-event], a[href^="/"][href*="-"]')
        or row.select_one("td.calendar-event")
    )
    if preferred:
        return preferred
    for anchor in row.select("a[href]"):
        href = clean_text(str(anchor.get("href") or ""))
        text = clean_text(anchor.get_text(" ", strip=True))
        if href and text and not href.startswith(("#", "javascript:")):
            return anchor
    return None


def _time_node(row: Tag) -> Tag | None:
    preferred = (
        row.select_one('span[class^="calendar-date"]')
        or row.select_one('span[class*=" calendar-date"]')
        or row.select_one("td.calendar-time")
        or row.select_one("time")
    )
    if preferred:
        return preferred
    for node in row.select("span, td"):
        if parse_time_text(node.get_text(" ", strip=True)) is not None:
            return node
    return None


def _row_date(row: Tag, current_date: date | None) -> date | None:
    for attribute in ("data-date", "data-datetime", "datetime"):
        raw = clean_text(str(row.get(attribute) or ""))
        if not raw:
            continue
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            parsed = parse_date_header(raw)
            if parsed:
                return parsed
    return current_date


def _event_datetime(event_date: date, event_time: dt_time | None) -> datetime:
    source_tz_name = str(getattr(settings, "ECONOMIC_CALENDAR_SOURCE_TIMEZONE", "UTC"))
    target_tz_name = str(getattr(settings, "TIME_ZONE", "America/Sao_Paulo"))
    source_tz = ZoneInfo(source_tz_name)
    target_tz = ZoneInfo(target_tz_name)
    value = datetime.combine(event_date, event_time or dt_time(0, 0), tzinfo=source_tz)
    return value.astimezone(target_tz)


def _external_id(row: Tag, event_at: datetime, country_code: str, event: str) -> str:
    row_id = row.get("data-id") or row.get("id")
    row_url = row.get("data-url") or ""
    stable = row_id or f"{event_at.isoformat()}|{country_code}|{event}|{row_url}"
    return hashlib.sha256(str(stable).encode("utf-8", errors="ignore")).hexdigest()


def parse_calendar_html(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    tables = soup.find_all("table")
    calendar_table = None
    for table in tables:
        if table.select_one("a.calendar-event") or table.select_one('span[id="actual"]') or table.select_one("tr[data-country]"):
            calendar_table = table
            break
    root: Tag | BeautifulSoup = calendar_table or soup

    events: list[dict[str, Any]] = []
    current_date: date | None = None

    for row in root.select("tr"):
        header = row.select_one("th[colspan], td[colspan]")
        if header:
            parsed_header = parse_date_header(header.get_text(" ", strip=True))
            if parsed_header:
                current_date = parsed_header
                continue

        country_code, country_label = _country_from_row(row)
        if not country_code:
            continue

        node = _event_node(row)
        event = clean_text(node.get_text(" ", strip=True) if node else "")
        if not event:
            continue

        row_date = _row_date(row, current_date)
        if row_date is None:
            continue

        time_node = _time_node(row)
        time_text = clean_text(time_node.get_text(" ", strip=True) if time_node else "")
        event_time = parse_time_text(time_text)
        event_at = _event_datetime(row_date, event_time)

        raw_url = ""
        if node and node.name == "a":
            raw_url = clean_text(str(node.get("href") or ""))
        raw_url = raw_url or clean_text(str(row.get("data-url") or ""))
        url = urljoin(CALENDAR_URL, raw_url) if raw_url else CALENDAR_URL

        reference = _field_text(row, "reference")
        if not reference:
            # Referência costuma aparecer como texto curto ao lado do título.
            ref_node = row.select_one("span.calendar-reference, small.calendar-reference, td.calendar-reference")
            reference = clean_text(ref_node.get_text(" ", strip=True) if ref_node else "")

        events.append(
            {
                "external_id": _external_id(row, event_at, country_code, event),
                "event_at": event_at,
                "country": country_label,
                "country_code": country_code,
                "category": clean_text(str(row.get("data-category") or "")),
                "event": event,
                "reference": reference,
                "importance": _importance(row),
                "actual": _field_text(row, "actual"),
                "previous": _field_text(row, "previous"),
                "revised": _field_text(row, "revised"),
                "consensus": _field_text(row, "consensus"),
                "forecast": _field_text(row, "forecast"),
                "url": url,
                "metadata": {
                    "source_timezone": str(getattr(settings, "ECONOMIC_CALENDAR_SOURCE_TIMEZONE", "UTC")),
                    "source_time_text": time_text,
                    "source_row_id": clean_text(str(row.get("id") or row.get("data-id") or "")),
                    "source_country": clean_text(str(row.get("data-country") or "")),
                },
            }
        )

    return events


class TradingEconomicsCalendarCollector:
    def __init__(self, session: Any | None = None) -> None:
        self.session = session
        self.diagnostics = CalendarDiagnostics()
        self._curl_session = None
        if session is None:
            try:
                from curl_cffi import requests as curl_requests

                self._curl_session = curl_requests.Session()
            except Exception as exc:
                logger.info("curl_cffi indisponível para Trading Economics: %s", exc)
                self.session = requests.Session()
        if self.session is not None and hasattr(self.session, "headers"):
            self.session.headers.update(
                {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://tradingeconomics.com/",
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
                }
            )

    @staticmethod
    def _challenge(status: int, headers: Any, html: str) -> bool:
        if status in {403, 429}:
            return True
        prefix = (html or "")[:5000].lower()
        markers = ("just a moment", "cf-chl-", "captcha", "access denied", "challenge-platform")
        return any(marker in prefix for marker in markers)

    def _open_circuit(self, status: int | None, reason: str) -> None:
        ttl = max(60, int(getattr(settings, "ECONOMIC_CALENDAR_CIRCUIT_SECONDS", 300)))
        cache.set(
            CALENDAR_CIRCUIT_CACHE_KEY,
            {"status": status, "reason": reason, "opened_at": time.time()},
            timeout=ttl,
        )
        self.diagnostics.circuit_opened = True

    def _fetch_with_curl(self) -> str:
        attempts = max(1, int(getattr(settings, "ECONOMIC_CALENDAR_HTTP_ATTEMPTS", 2)))
        for attempt in range(attempts):
            if attempt:
                self.diagnostics.retries += 1
                time.sleep((2 ** (attempt - 1)) + random.uniform(0.2, 0.8))
            response = self._curl_session.get(
                CALENDAR_URL,
                headers={
                    "Accept-Language": "en-US,en;q=0.9",
                    "Referer": "https://tradingeconomics.com/",
                },
                timeout=(
                    int(getattr(settings, "HTTP_CONNECT_TIMEOUT_SECONDS", 5)),
                    int(getattr(settings, "ECONOMIC_CALENDAR_HTTP_TIMEOUT_SECONDS", 25)),
                ),
                impersonate="chrome",
                allow_redirects=True,
            )
            self.diagnostics.network_requests += 1
            status = int(response.status_code)
            html = response.text or ""
            if status == 200 and not self._challenge(status, response.headers, html):
                return html
            if self._challenge(status, response.headers, html):
                self.diagnostics.blocked_responses += 1
                if attempt + 1 >= attempts:
                    self._open_circuit(status, "proteção antibot/rate limit")
                    raise CalendarUnavailable(f"Trading Economics bloqueou a coleta (HTTP {status}).")
                continue
            response.raise_for_status()
        raise CalendarUnavailable("Falha ao acessar o calendário da Trading Economics.")

    def _fetch_with_requests(self) -> str:
        self.diagnostics.fallback_requests += 1
        response = self.session.get(
            CALENDAR_URL,
            timeout=(
                int(getattr(settings, "HTTP_CONNECT_TIMEOUT_SECONDS", 5)),
                int(getattr(settings, "ECONOMIC_CALENDAR_HTTP_TIMEOUT_SECONDS", 25)),
            ),
            allow_redirects=True,
        )
        self.diagnostics.network_requests += 1
        status = int(response.status_code)
        html = response.text or ""
        if self._challenge(status, response.headers, html):
            self.diagnostics.blocked_responses += 1
            self._open_circuit(status, "fallback bloqueado")
            raise CalendarUnavailable(f"Trading Economics bloqueou a coleta (HTTP {status}).")
        response.raise_for_status()
        return html

    def fetch_html(self) -> str:
        circuit = cache.get(CALENDAR_CIRCUIT_CACHE_KEY)
        if circuit:
            raise CalendarUnavailable(f"Circuit breaker ativo para o calendário: {circuit}")
        if self._curl_session is not None:
            try:
                return self._fetch_with_curl()
            except CalendarUnavailable:
                raise
            except Exception as exc:
                logger.warning("curl_cffi falhou no calendário: %s; usando requests.", exc)
                self.session = self.session or requests.Session()
                return self._fetch_with_requests()
        return self._fetch_with_requests()

    def collect(self) -> dict[str, Any]:
        if not bool(getattr(settings, "ECONOMIC_CALENDAR_ENABLED", True)):
            result = {"status": "disabled", "created": 0, "updated": 0}
            cache.set(CALENDAR_STATUS_CACHE_KEY, result, timeout=None)
            return result

        started = time.monotonic()
        try:
            html = self.fetch_html()
            if len(html) < int(getattr(settings, "ECONOMIC_CALENDAR_MIN_HTML_BYTES", 5000)):
                raise CalendarUnavailable(f"HTML do calendário muito pequeno: {len(html)} bytes")
            parsed = parse_calendar_html(html)
            self.diagnostics.parsed_rows = len(parsed)
            selected_codes = set(getattr(settings, "ECONOMIC_CALENDAR_COUNTRIES", ["BR", "US", "CN", "EA"]))
            selected = [item for item in parsed if item["country_code"] in selected_codes]
            self.diagnostics.selected_rows = len(selected)
            if not selected:
                raise CalendarUnavailable("Nenhum evento selecionado foi encontrado no HTML da Trading Economics.")

            created = 0
            updated = 0
            with transaction.atomic():
                for item in selected:
                    external_id = item.pop("external_id")
                    _, was_created = EconomicEvent.objects.update_or_create(
                        external_id=external_id,
                        defaults=item,
                    )
                    created += int(was_created)
                    updated += int(not was_created)

            retention_days = max(2, int(getattr(settings, "ECONOMIC_CALENDAR_RETENTION_DAYS", 14)))
            deleted, _ = EconomicEvent.objects.filter(
                event_at__lt=timezone.now() - timedelta(days=retention_days)
            ).delete()

            result = {
                "status": "success",
                "source": "Trading Economics Calendar",
                "url": CALENDAR_URL,
                "created": created,
                "updated": updated,
                "events": len(selected),
                "deleted": deleted,
                "collected_at": timezone.now().isoformat(),
                "duration_ms": int((time.monotonic() - started) * 1000),
                "diagnostics": self.diagnostics.as_dict(),
            }
        except Exception as exc:
            logger.exception("Falha na coleta do calendário econômico")
            result = {
                "status": "failed",
                "source": "Trading Economics Calendar",
                "url": CALENDAR_URL,
                "error": str(exc),
                "collected_at": timezone.now().isoformat(),
                "duration_ms": int((time.monotonic() - started) * 1000),
                "diagnostics": self.diagnostics.as_dict(),
            }
        cache.set(CALENDAR_STATUS_CACHE_KEY, result, timeout=None)
        return result


def calendar_payload(*, days: int = 7, country: str = "", min_importance: int = 1) -> dict[str, Any]:
    days = min(max(int(days), 1), 14)
    min_importance = min(max(int(min_importance), 1), 3)
    now = timezone.now()
    local_now = timezone.localtime(now)
    start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)
    queryset = EconomicEvent.objects.filter(
        event_at__gte=start,
        event_at__lte=end,
        importance__gte=min_importance,
    )
    country = clean_text(country).upper()
    if country and country != "ALL":
        queryset = queryset.filter(country_code=country)

    items = [
        {
            "external_id": item.external_id,
            "event_at": item.event_at.isoformat(),
            "country": item.country,
            "country_code": item.country_code,
            "category": item.category,
            "event": item.event,
            "reference": item.reference,
            "importance": item.importance,
            "actual": item.actual,
            "previous": item.previous,
            "revised": item.revised,
            "consensus": item.consensus,
            "forecast": item.forecast,
            "released": bool(item.actual),
            "url": item.url,
            "updated_at": item.updated_at.isoformat(),
        }
        for item in queryset.order_by("event_at", "-importance", "country_code")[:300]
    ]
    last_update = EconomicEvent.objects.aggregate(value=Max("updated_at"))["value"]
    status = cache.get(CALENDAR_STATUS_CACHE_KEY) or {}
    return {
        "available": bool(items),
        "count": len(items),
        "items": items,
        "countries": COUNTRY_LABELS,
        "source": "Trading Economics Calendar",
        "source_url": CALENDAR_URL,
        "last_collected_at": last_update.isoformat() if last_update else None,
        "collector_status": status,
    }
