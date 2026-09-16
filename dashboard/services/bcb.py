from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.utils import timezone

logger = logging.getLogger(__name__)

BCB_SGS_BASE_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados"
BCB_SELIC_SERIES = 1178
BCB_RESOURCE_DOWNLOAD = (
    "https://dadosabertos.bcb.gov.br/dataset/"
    "1178-taxa-de-juros---selic-anualizada-base-252/resource/"
    "e7fe6edb-d6c3-49b1-a7ef-6e0e98b63270/download"
)
BCB_PTAX_BASE = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata"


def _session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "User-Agent": (
                "MacroDashboard/1.0 (Django; BCB market-data client) "
                "Mozilla/5.0"
            ),
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.7,en;q=0.6",
            "Connection": "keep-alive",
        }
    )
    return session


def fetch_sgs_recent(
    series: int = BCB_SELIC_SERIES,
    *,
    days_back: int = 10,
    session: requests.Session | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Fetch a small, date-filtered SGS window.

    Since 26 Mar 2025 the BCB limits unfiltered JSON/CSV historical-series
    responses and requires filters. The old /ultimos/N endpoint is therefore
    avoided here in favour of a bounded date range.
    """
    owns_session = session is None
    session = session or _session()
    end = timezone.localdate()
    start = end - timedelta(days=max(1, min(days_back, 10)))
    url = BCB_SGS_BASE_URL.format(series=series)
    params = {
        "dataInicial": start.strftime("%d/%m/%Y"),
        "dataFinal": end.strftime("%d/%m/%Y"),
        "formato": "json",
    }
    try:
        response = session.get(
            url,
            params=params,
            timeout=(
                float(getattr(settings, "BCB_CONNECT_TIMEOUT_SECONDS", 5)),
                float(getattr(settings, "BCB_READ_TIMEOUT_SECONDS", 20)),
            ),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("SGS não retornou uma lista JSON.")
        return payload, response.url
    finally:
        if owns_session:
            session.close()


def fetch_sgs_resource_fallback(
    *, session: requests.Session | None = None
) -> tuple[list[dict[str, Any]], str]:
    """Fallback oficial para o recurso JSON do Portal de Dados Abertos do BCB."""
    owns_session = session is None
    session = session or _session()
    try:
        response = session.get(
            BCB_RESOURCE_DOWNLOAD,
            timeout=(
                float(getattr(settings, "BCB_CONNECT_TIMEOUT_SECONDS", 5)),
                float(getattr(settings, "BCB_READ_TIMEOUT_SECONDS", 20)),
            ),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("Recurso JSON do BCB não retornou uma lista.")
        return payload, response.url
    finally:
        if owns_session:
            session.close()


def fetch_selic_recent() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Primary + fallback fetch for SGS series 1178, with diagnostics."""
    started = time.monotonic()
    diagnostics: dict[str, Any] = {
        "series": BCB_SELIC_SERIES,
        "primary": {"ok": False, "url": BCB_SGS_BASE_URL.format(series=BCB_SELIC_SERIES)},
        "fallback": {"ok": False, "url": BCB_RESOURCE_DOWNLOAD},
    }
    session = _session()
    try:
        try:
            rows, final_url = fetch_sgs_recent(session=session)
            if not rows:
                raise ValueError("SGS retornou lista vazia para a janela consultada.")
            diagnostics["primary"].update({"ok": True, "url": final_url, "rows": len(rows)})
            return rows, {
                **diagnostics,
                "method": "sgs_date_range",
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        except Exception as exc:
            diagnostics["primary"]["error"] = str(exc)
            logger.warning("BCB SGS %s date-range falhou: %s", BCB_SELIC_SERIES, exc)

        try:
            rows, final_url = fetch_sgs_resource_fallback(session=session)
            if not rows:
                raise ValueError("Recurso JSON do BCB retornou lista vazia.")
            diagnostics["fallback"].update({"ok": True, "url": final_url, "rows": len(rows)})
            return rows, {
                **diagnostics,
                "method": "portal_resource_json",
                "duration_ms": int((time.monotonic() - started) * 1000),
            }
        except Exception as exc:
            diagnostics["fallback"]["error"] = str(exc)
            logger.warning("BCB SGS fallback falhou: %s", exc)
            raise RuntimeError(
                "BCB SGS indisponível nas duas rotas oficiais. "
                f"Primária: {diagnostics['primary'].get('error', '')}; "
                f"fallback: {diagnostics['fallback'].get('error', '')}"
            ) from exc
    finally:
        session.close()
