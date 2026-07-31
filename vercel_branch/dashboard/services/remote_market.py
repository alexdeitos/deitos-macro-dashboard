from __future__ import annotations

import os
import time
from datetime import datetime, timezone as dt_timezone
from typing import Any

import requests
from django.utils.dateparse import parse_datetime


class RemoteMarketError(RuntimeError):
    """Erro ao consultar ou validar o snapshot remoto."""


def remote_market_enabled() -> bool:
    return os.getenv("USE_REMOTE_MARKET_JSON", "False").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _snapshot_age_seconds(payload: dict[str, Any]) -> float | None:
    collected_at = parse_datetime(str(payload.get("collected_at", "")))
    if collected_at is None:
        return None
    if collected_at.tzinfo is None:
        collected_at = collected_at.replace(tzinfo=dt_timezone.utc)
    return max(0.0, (datetime.now(dt_timezone.utc) - collected_at).total_seconds())


def _unwrap_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise RemoteMarketError("O endpoint remoto não retornou um objeto JSON.")

    # Aceita tanto /api/raw/ (payload direto) quanto wrappers comuns.
    if isinstance(data.get("data"), dict) and (
        "quotes" in data["data"] or "quote_list" in data["data"]
    ):
        data = data["data"]
    elif isinstance(data.get("payload"), dict) and (
        "quotes" in data["payload"] or "quote_list" in data["payload"]
    ):
        data = data["payload"]

    if data.get("available") is False:
        raise RemoteMarketError("O projeto local ainda não possui snapshot disponível.")

    if not isinstance(data.get("quotes"), dict):
        raise RemoteMarketError("JSON remoto inválido: campo 'quotes' ausente.")
    if not isinstance(data.get("quote_list"), list):
        # Reconstrói quote_list a partir do mapa para manter a persistência funcional.
        data = dict(data)
        data["quote_list"] = [row for row in data["quotes"].values() if isinstance(row, dict)]

    return data


def fetch_remote_market_snapshot() -> dict[str, Any]:
    url = os.getenv("REMOTE_MARKET_JSON_URL", "").strip()
    token = os.getenv("REMOTE_MARKET_JSON_TOKEN", "").strip()
    if not url:
        raise RemoteMarketError("REMOTE_MARKET_JSON_URL não configurada.")

    connect_timeout = float(os.getenv("REMOTE_MARKET_CONNECT_TIMEOUT_SECONDS", "5"))
    read_timeout = float(os.getenv("REMOTE_MARKET_READ_TIMEOUT_SECONDS", "30"))
    max_age = int(os.getenv("REMOTE_MARKET_MAX_AGE_SECONDS", "900"))

    headers = {
        "Accept": "application/json",
        "User-Agent": "MacroDashboard-Vercel/1.0",
    }
    if token:
        headers["X-Market-Token"] = token

    started = time.monotonic()
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=(connect_timeout, read_timeout),
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RemoteMarketError(f"Falha ao consultar o projeto local: {exc}") from exc

    try:
        payload = _unwrap_payload(response.json())
    except ValueError as exc:
        raise RemoteMarketError("O endpoint remoto não retornou JSON válido.") from exc

    age_seconds = _snapshot_age_seconds(payload)
    if max_age > 0 and age_seconds is not None and age_seconds > max_age:
        raise RemoteMarketError(
            f"Snapshot remoto desatualizado: {int(age_seconds)}s; limite {max_age}s."
        )

    result = dict(payload)
    source_status = result.get("source_status")
    if not isinstance(source_status, dict):
        source_status = {}
    else:
        source_status = dict(source_status)

    source_status["remote_project"] = {
        "ok": True,
        "complete": True,
        "partial": False,
        "fetched_at": datetime.now(dt_timezone.utc).isoformat(),
        "quote_count": len(result.get("quote_list", [])),
        "error": "",
        "duration_ms": int((time.monotonic() - started) * 1000),
        "metadata": {
            "transport": "remote_json",
            "snapshot_age_seconds": int(age_seconds) if age_seconds is not None else None,
        },
    }
    result["source_status"] = source_status
    result["remote_source"] = {
        "enabled": True,
        "transport": "remote_json",
        "fetched_at": datetime.now(dt_timezone.utc).isoformat(),
        "snapshot_age_seconds": int(age_seconds) if age_seconds is not None else None,
    }
    # Mantém collected_at original: ele representa o horário real da coleta local.
    result.setdefault("schema_version", 5)
    result.setdefault("duration_ms", source_status["remote_project"]["duration_ms"])
    result.setdefault("is_complete", True)
    result.setdefault("successful_sources", 1)
    result.setdefault("complete_sources", 1)
    result.setdefault("total_sources", 1)
    return result
