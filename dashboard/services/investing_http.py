from __future__ import annotations

import hashlib
import logging
import random
import time
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.core.cache import cache

from .http import build_session

logger = logging.getLogger(__name__)

# Ao usar impersonate="chrome", o curl_cffi já injeta os headers coerentes com
# a versão de navegador emulada. Não sobrescreva User-Agent, sec-ch-ua ou outros
# headers de fingerprint: isso pode criar uma combinação TLS/HTTP incoerente.
CURL_EXTRA_HEADERS = {
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://br.investing.com/",
}

CIRCUIT_CACHE_KEY = "market-dashboard:investing-http-circuit"
HTML_CACHE_PREFIX = "market-dashboard:investing-html"


@dataclass(slots=True)
class InvestingHttpDiagnostics:
    network_requests: int = 0
    retries: int = 0
    cache_hits: int = 0
    blocked_responses: int = 0
    session_resets: int = 0
    fallback_requests: int = 0
    circuit_opened: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "network_requests": self.network_requests,
            "retries": self.retries,
            "cache_hits": self.cache_hits,
            "blocked_responses": self.blocked_responses,
            "session_resets": self.session_resets,
            "fallback_requests": self.fallback_requests,
            "circuit_opened": self.circuit_opened,
        }


class InvestingHttpError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        cf_ray: str | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.cf_ray = cf_ray
        self.url = url


class InvestingCircuitOpen(InvestingHttpError):
    pass


class InvestingHttpClient:
    """Cliente conservador para páginas públicas do Investing.

    Objetivos:
    - manter fingerprint do curl_cffi coerente;
    - espaçar requisições de uma mesma coleta;
    - recuperar sessão uma vez após 403/429;
    - parar o lote quando o bloqueio persiste;
    - evitar repetir páginas lentas dentro do TTL configurado.
    """

    def __init__(self, base_url: str = "https://br.investing.com") -> None:
        self.base_url = base_url.rstrip("/")
        self.requests_session = build_session()
        self._curl_requests = None
        self._curl_session = None
        self._last_network_request_at: float | None = None
        self.diagnostics = InvestingHttpDiagnostics()
        self._build_curl_session()

    @staticmethod
    def _cache_key(url: str) -> str:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return f"{HTML_CACHE_PREFIX}:{digest}"

    @staticmethod
    def _circuit_message() -> str | None:
        state = cache.get(CIRCUIT_CACHE_KEY)
        if not state:
            return None
        if isinstance(state, dict):
            reason = state.get("reason") or "bloqueio temporário"
            status = state.get("status_code")
            cf_ray = state.get("cf_ray")
            details = [str(reason)]
            if status:
                details.append(f"HTTP {status}")
            if cf_ray:
                details.append(f"CF-RAY {cf_ray}")
            return "; ".join(details)
        return str(state)

    def _build_curl_session(self) -> None:
        try:
            from curl_cffi import requests as curl_requests

            self._curl_requests = curl_requests
            self._curl_session = curl_requests.Session()
        except Exception as exc:
            self._curl_requests = None
            self._curl_session = None
            logger.info("curl_cffi indisponível; fallback requests será usado: %s", exc)

    def _reset_curl_session(self) -> None:
        old_session = self._curl_session
        if old_session is not None:
            try:
                old_session.close()
            except Exception:
                pass
        self.diagnostics.session_resets += 1
        self._build_curl_session()

    def _pace_request(self) -> None:
        minimum = max(0.0, float(settings.INVESTING_REQUEST_MIN_DELAY_SECONDS))
        maximum = max(minimum, float(settings.INVESTING_REQUEST_MAX_DELAY_SECONDS))
        if self._last_network_request_at is None:
            return
        target_delay = random.uniform(minimum, maximum)
        elapsed = time.monotonic() - self._last_network_request_at
        remaining = target_delay - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _record_network_request(self) -> None:
        self._last_network_request_at = time.monotonic()
        self.diagnostics.network_requests += 1

    @staticmethod
    def _is_challenge(response: Any, body: str) -> bool:
        mitigated = str(response.headers.get("cf-mitigated", "")).lower()
        if mitigated == "challenge":
            return True
        prefix = body[:4000].lower()
        markers = (
            "<title>just a moment",
            "challenge-platform",
            "cf-chl-",
            "attention required! | cloudflare",
        )
        return any(marker in prefix for marker in markers)

    def _open_circuit(
        self,
        *,
        reason: str,
        status_code: int | None,
        cf_ray: str | None,
    ) -> None:
        cooldown = max(60, int(settings.INVESTING_CIRCUIT_COOLDOWN_SECONDS))
        cache.set(
            CIRCUIT_CACHE_KEY,
            {
                "reason": reason,
                "status_code": status_code,
                "cf_ray": cf_ray,
                "opened_at": time.time(),
            },
            timeout=cooldown,
        )
        self.diagnostics.circuit_opened = True

    def _warm_up(self) -> None:
        if self._curl_session is None:
            return
        try:
            self._pace_request()
            response = self._curl_session.get(
                f"{self.base_url}/",
                headers=CURL_EXTRA_HEADERS,
                timeout=settings.HTTP_TIMEOUT_SECONDS,
                impersonate="chrome",
                allow_redirects=True,
            )
            self._record_network_request()
            logger.debug(
                "Warm-up Investing: HTTP %s, cf-ray=%s",
                response.status_code,
                response.headers.get("cf-ray"),
            )
        except Exception as exc:
            logger.debug("Warm-up Investing não concluído: %s", exc)

    def _get_with_curl(self, url: str) -> str:
        attempts = max(1, int(settings.INVESTING_HTTP_ATTEMPTS))
        last_error: InvestingHttpError | None = None

        for attempt in range(attempts):
            if attempt:
                self.diagnostics.retries += 1
                base = max(0.5, float(settings.INVESTING_RETRY_BACKOFF_SECONDS))
                time.sleep(base * (2 ** (attempt - 1)) + random.uniform(0.25, 0.9))

            self._pace_request()
            try:
                response = self._curl_session.get(
                    url,
                    headers=CURL_EXTRA_HEADERS,
                    timeout=settings.HTTP_TIMEOUT_SECONDS,
                    impersonate="chrome",
                    allow_redirects=True,
                )
                self._record_network_request()
            except Exception as exc:
                last_error = InvestingHttpError(
                    f"Falha de transporte do curl_cffi em {url}: {exc}",
                    url=url,
                )
                if attempt + 1 < attempts:
                    self._reset_curl_session()
                    continue
                raise last_error from exc

            status = int(response.status_code)
            body = response.text or ""
            cf_ray = response.headers.get("cf-ray")
            challenged = self._is_challenge(response, body)

            if status == 200 and not challenged:
                if len(body) < int(settings.INVESTING_MIN_HTML_BYTES):
                    last_error = InvestingHttpError(
                        f"HTML inesperadamente pequeno ({len(body)} bytes) em {url}",
                        status_code=status,
                        cf_ray=cf_ray,
                        url=url,
                    )
                else:
                    return body
            elif status in {403, 429} or challenged:
                self.diagnostics.blocked_responses += 1
                label = "desafio antibot" if challenged and status == 200 else f"HTTP {status}"
                last_error = InvestingHttpError(
                    f"Investing recusou a requisição ({label}); cf-ray={cf_ray or 'ausente'}",
                    status_code=status,
                    cf_ray=cf_ray,
                    url=url,
                )
                if attempt + 1 < attempts:
                    self._reset_curl_session()
                    self._warm_up()
                    continue
                self._open_circuit(
                    reason="proteção antibot/rate limit",
                    status_code=status,
                    cf_ray=cf_ray,
                )
                raise last_error
            else:
                last_error = InvestingHttpError(
                    f"Investing retornou HTTP {status}; cf-ray={cf_ray or 'ausente'}",
                    status_code=status,
                    cf_ray=cf_ray,
                    url=url,
                )

            if attempt + 1 < attempts:
                continue

        if last_error is None:
            last_error = InvestingHttpError(f"Falha desconhecida ao acessar {url}", url=url)
        raise last_error

    def _get_with_requests(self, url: str) -> str:
        self.diagnostics.fallback_requests += 1
        self._pace_request()
        response = self.requests_session.get(
            url,
            timeout=settings.HTTP_TIMEOUT_SECONDS,
            allow_redirects=True,
        )
        self._record_network_request()
        status = int(response.status_code)
        cf_ray = response.headers.get("cf-ray")
        if status in {403, 429}:
            self.diagnostics.blocked_responses += 1
            self._open_circuit(
                reason="fallback requests bloqueado",
                status_code=status,
                cf_ray=cf_ray,
            )
            raise InvestingHttpError(
                f"Fallback requests bloqueado com HTTP {status}; cf-ray={cf_ray or 'ausente'}",
                status_code=status,
                cf_ray=cf_ray,
                url=url,
            )
        try:
            response.raise_for_status()
        except Exception as exc:
            raise InvestingHttpError(
                f"Fallback requests retornou HTTP {status}; cf-ray={cf_ray or 'ausente'}",
                status_code=status,
                cf_ray=cf_ray,
                url=url,
            ) from exc
        body = response.text or ""
        if len(body) < int(settings.INVESTING_MIN_HTML_BYTES):
            raise InvestingHttpError(
                f"Fallback retornou HTML pequeno ({len(body)} bytes) em {url}",
                status_code=status,
                cf_ray=cf_ray,
                url=url,
            )
        return body

    def get_html(self, url: str, *, cache_ttl: int = 0) -> str:
        full_url = url if url.startswith("http") else f"{self.base_url}{url}"
        cache_key = self._cache_key(full_url)

        if cache_ttl > 0:
            cached_html = cache.get(cache_key)
            if isinstance(cached_html, str) and cached_html:
                self.diagnostics.cache_hits += 1
                return cached_html

        circuit_message = self._circuit_message()
        if circuit_message:
            raise InvestingCircuitOpen(
                f"Circuit breaker ativo para Investing: {circuit_message}",
                url=full_url,
            )

        if self._curl_session is not None:
            try:
                html = self._get_with_curl(full_url)
            except InvestingHttpError as exc:
                # Não duplique a tentativa com requests quando o servidor já
                # respondeu 403/429 ou apresentou challenge. Isso só piora o lote.
                if exc.status_code in {403, 429, 200}:
                    raise
                logger.warning(
                    "curl_cffi falhou por transporte em %s: %s; usando requests.",
                    full_url,
                    exc,
                )
                html = self._get_with_requests(full_url)
        else:
            html = self._get_with_requests(full_url)

        if cache_ttl > 0:
            cache.set(cache_key, html, timeout=max(1, int(cache_ttl)))
        return html
