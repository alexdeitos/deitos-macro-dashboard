from __future__ import annotations

import logging
from typing import Any

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.7,en;q=0.6",
}


def build_session() -> requests.Session:
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def get_json(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    response = session.get(url, params=params, timeout=settings.HTTP_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()
