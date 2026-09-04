from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup
from django.conf import settings
from django.utils import timezone as django_timezone

from .http import build_session, get_json
from .investing_http import InvestingCircuitOpen, InvestingHttpClient
from .parsing import (
    parse_epoch,
    parse_iso_datetime,
    parse_number,
    parse_number_pt_br,
    parse_percent,
    reconcile_change_percent,
)
from .types import Quote, SourceResult

logger = logging.getLogger(__name__)


class AwesomeApiSource:
    name = "awesomeapi"
    base_url = "https://economia.awesomeapi.com.br"

    def fetch(self) -> SourceResult:
        started = time.monotonic()
        fetched_at = django_timezone.now()
        session = build_session()
        if settings.AWESOME_API_KEY:
            session.headers["x-api-key"] = settings.AWESOME_API_KEY
        history_error = ""
        try:
            latest = get_json(session, f"{self.base_url}/json/last/USD-BRL")
            item = latest.get("USDBRL", {})
            value = parse_number(item.get("bid"))
            if value is None:
                raise ValueError("AwesomeAPI não retornou bid para USD/BRL.")

            observed_at = parse_epoch(item.get("timestamp"))
            quote = Quote(
                symbol="USD_BRL",
                name="Dólar comercial USD/BRL",
                category="currency",
                source=self.name,
                observed_at=observed_at,
                value=value,
                change_percent=parse_percent(item.get("pctChange")),
                high=parse_number(item.get("high")),
                low=parse_number(item.get("low")),
                currency="BRL",
                source_url=f"{self.base_url}/json/last/USD-BRL",
                raw={"code": item.get("code"), "codein": item.get("codein")},
            )

            intraday_rows: list[dict[str, Any]] = []
            try:
                history = get_json(session, f"{self.base_url}/USD-BRL/200")
                for row in history if isinstance(history, list) else []:
                    row_value = parse_number(row.get("bid"))
                    if row_value is None:
                        continue
                    intraday_rows.append(
                        {
                            "symbol": "USD_BRL",
                            "name": "Dólar comercial USD/BRL",
                            "category": "currency",
                            "source": self.name,
                            "observed_at": parse_epoch(row.get("timestamp")).isoformat(),
                            "value": row_value,
                            "change_percent": parse_percent(row.get("pctChange")),
                            "high": parse_number(row.get("high")),
                            "low": parse_number(row.get("low")),
                        }
                    )
            except Exception as exc:  # A cotação atual continua válida.
                history_error = f"Histórico intradiário: {exc}"
                logger.warning("Histórico intradiário da AwesomeAPI indisponível: %s", exc)

            return SourceResult(
                name=self.name,
                ok=True,
                complete=not history_error,
                fetched_at=fetched_at,
                quotes=[quote],
                groups={"intraday": intraday_rows},
                error=history_error,
                metadata={
                    "provider": "AwesomeAPI",
                    "pair": "USD-BRL",
                    "authenticated": bool(settings.AWESOME_API_KEY),
                },
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:
            return SourceResult(
                name=self.name,
                ok=False,
                complete=False,
                fetched_at=fetched_at,
                error=str(exc),
                duration_ms=int((time.monotonic() - started) * 1000),
                metadata={"provider": "AwesomeAPI"},
            )


class BancoCentralSource:
    name = "bcb"
    sgs_url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.1178/dados/ultimos/5"
    ptax_base = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata"

    def fetch(self) -> SourceResult:
        started = time.monotonic()
        fetched_at = django_timezone.now()
        session = build_session()
        quotes: list[Quote] = []
        errors: list[str] = []

        try:
            rows = get_json(session, self.sgs_url, params={"formato": "json"})
            if rows:
                latest = rows[-1]
                value = parse_number(latest.get("valor"))
                if value is not None:
                    quotes.append(
                        Quote(
                            symbol="SELIC_252",
                            name="Selic anualizada base 252",
                            category="interest_rate",
                            source=self.name,
                            observed_at=fetched_at,
                            value=value,
                            currency="% a.a.",
                            source_url=f"{self.sgs_url}?formato=json",
                            raw={"data_referencia": latest.get("data"), "serie": 1178},
                        )
                    )
        except Exception as exc:
            errors.append(f"Selic: {exc}")

        try:
            end = datetime.now().date()
            start = end - timedelta(days=12)
            endpoint = f"{self.ptax_base}/CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
            params = {
                "@dataInicial": f"'{start:%m-%d-%Y}'",
                "@dataFinalCotacao": f"'{end:%m-%d-%Y}'",
                "$format": "json",
            }
            payload = get_json(session, endpoint, params=params)
            values = payload.get("value", []) if isinstance(payload, dict) else []
            if values:
                latest = max(
                    values,
                    key=lambda item: parse_iso_datetime(item.get("dataHoraCotacao")),
                )
                buy = parse_number(latest.get("cotacaoCompra"))
                sell = parse_number(latest.get("cotacaoVenda"))
                midpoint = (buy + sell) / 2 if buy is not None and sell is not None else sell or buy
                if midpoint is not None:
                    bulletin_rows = []
                    for item in values:
                        try:
                            item_dt = parse_iso_datetime(item.get("dataHoraCotacao"))
                        except Exception:
                            continue
                        item_buy = parse_number(item.get("cotacaoCompra"))
                        item_sell = parse_number(item.get("cotacaoVenda"))
                        item_mid = (item_buy + item_sell) / 2 if item_buy is not None and item_sell is not None else item_sell or item_buy
                        if item_mid is not None:
                            bulletin_rows.append({
                                "observed_at": item_dt.isoformat(),
                                "hour": item_dt.hour,
                                "tipo_boletim": item.get("tipoBoletim"),
                                "buy": item_buy,
                                "sell": item_sell,
                                "midpoint": item_mid,
                            })
                    bulletin_rows.sort(key=lambda row: row["observed_at"])
                    today_rows = [row for row in bulletin_rows if row["observed_at"][:10] == end.isoformat()]
                    previous_rows = [row for row in bulletin_rows if row["observed_at"][:10] < end.isoformat()]
                    previous_ptax = previous_rows[-1]["midpoint"] if previous_rows else None
                    intra_day = {}
                    for row in today_rows:
                        if row["hour"] in (10, 11, 12, 13):
                            intra_day[row["hour"]] = row
                    quotes.append(
                        Quote(
                            symbol="PTAX_USD_BRL",
                            name="PTAX USD/BRL",
                            category="currency_reference",
                            source=self.name,
                            observed_at=parse_iso_datetime(latest.get("dataHoraCotacao")),
                            value=midpoint,
                            high=max(v for v in (buy, sell) if v is not None),
                            low=min(v for v in (buy, sell) if v is not None),
                            currency="BRL",
                            source_url=endpoint,
                            raw={
                                "cotacao_compra": buy,
                                "cotacao_venda": sell,
                                "tipo_boletim": latest.get("tipoBoletim"),
                                "previous_ptax_midpoint": previous_ptax,
                                "today_bulletins": [intra_day[key] for key in sorted(intra_day)],
                            },
                        )
                    )
        except Exception as exc:
            errors.append(f"PTAX: {exc}")

        return SourceResult(
            name=self.name,
            ok=bool(quotes),
            complete=len(quotes) == 2 and not errors,
            fetched_at=fetched_at,
            quotes=quotes,
            error=" | ".join(errors),
            metadata={"provider": "Banco Central do Brasil", "series": [1178, "PTAX"]},
            duration_ms=int((time.monotonic() - started) * 1000),
        )


class InvestingSource:
    name = "investing"
    base_url = "https://br.investing.com"

    instrument_pages = [
        ("DOL_FUT", "Dólar comercial futuro B3", "future", "/currencies/usd-brl-bmf-futures", "BRL"),
        ("DXY", "Índice Dólar DXY", "currency_index", "/indices/usdollar", "points"),
        ("IBOV", "Ibovespa Futures", "future", "https://www.investing.com/indices/ibovespa-futures", "points"),
        ("SP500", "S&P 500", "index", "/indices/us-spx-500", "points"),
        ("NASDAQ", "Nasdaq Composite", "index", "/indices/nasdaq-composite", "points"),
        ("VIX", "Índice de Volatilidade VIX", "volatility", "/indices/volatility-s-p-500", "points"),
        ("BRENT", "Petróleo Brent", "commodity", "/commodities/brent-oil", "USD"),
        ("IRON_ORE", "Minério de ferro 62% CFR", "commodity", "/commodities/iron-ore-62-cfr-futures", "USD"),
        ("EWZ", "iShares MSCI Brazil ETF", "etf", "/etfs/ishares-brazil-index", "USD"),
        ("EEM", "iShares MSCI Emerging Markets ETF", "etf", "/etfs/ishares-msci-emg-markets", "USD"),
        ("EUR_USD", "Euro / Dólar Americano", "currency", "/currencies/eur-usd", "USD"),
        ("EUR_BRL", "Euro / Real Brasileiro", "currency", "/currencies/eur-brl", "BRL"),
    ]

    # Instrumentos complementares usados apenas no novo card de cálculo macro.
    # Uma falha nestas páginas não transforma toda a fonte Investing em falha,
    # mas o card informa explicitamente o componente ausente.
    optional_instrument_pages = [
        ("WTI", "Petróleo WTI (CL1)", "commodity", "/commodities/crude-oil", "USD"),
        ("DJI", "Dow Jones Industrial Average", "index", "/indices/us-30", "points"),
    ]

    adr_symbol_map = {
        "itau-unibanco": "ITUB",
        "itauunibanco": "ITUB",
        "vale-s.a.": "VALE",
        "vale-sa": "VALE",
        "petroleo-brasileiro": "PBR",
        "petroleobras": "PBR",
        "bradesco": "BBD",
        "gerdau": "GGB",
        "ambev": "ABEV",
        "sabesp": "SBS",
        "suzano": "SUZ",
        "embraer": "ERJ",
        "braskem": "BAK",
        "ultrapar": "UGP",
        "pagseguro": "PAGS",
        "stoneco": "STNE",
        "xp-inc": "XP",
    }

    def __init__(self) -> None:
        self.http = InvestingHttpClient(base_url=self.base_url)

    def _get_html(self, url: str, *, cache_ttl: int = 0) -> str:
        return self.http.get_html(url, cache_ttl=cache_ttl)

    @staticmethod
    def _instrument_quote(
        html: str,
        *,
        symbol: str,
        name: str,
        category: str,
        source_url: str,
        currency: str,
        observed_at: datetime,
    ) -> Quote:
        soup = BeautifulSoup(html, "lxml")
        price_node = soup.select_one('[data-test="instrument-price-last"]')
        if price_node is None:
            raise ValueError(f"Preço não encontrado para {symbol}.")

        def text(selector: str) -> str | None:
            node = soup.select_one(selector)
            return node.get_text(" ", strip=True) if node else None

        raw_value = price_node.get_text(" ", strip=True)
        raw_change = text('[data-test="instrument-price-change-percent"]')
        raw_previous_close = text('[data-test="prevClose"]')

        value = parse_number_pt_br(raw_value)
        previous_close = parse_number_pt_br(raw_previous_close)
        scraped_change = parse_percent(raw_change)
        if value is None:
            raise ValueError(f"Preço inválido para {symbol}.")

        change_percent, validation = reconcile_change_percent(
            scraped_change=scraped_change,
            value=value,
            previous_close=previous_close,
        )

        return Quote(
            symbol=symbol,
            name=name,
            category=category,
            source="investing",
            observed_at=observed_at,
            value=value,
            change_percent=change_percent,
            high=parse_number_pt_br(text('[data-test="instrument-high"]')),
            low=parse_number_pt_br(text('[data-test="instrument-low"]')),
            previous_close=previous_close,
            currency=currency,
            source_url=source_url,
            raw={
                "provider_value_text": raw_value,
                "provider_change_percent_text": raw_change,
                "provider_previous_close_text": raw_previous_close,
                "validation": validation,
            },
        )

    def _fetch_instruments(
        self,
        observed_at: datetime,
    ) -> tuple[list[Quote], list[str], list[str]]:
        quotes: list[Quote] = []
        errors: list[str] = []
        optional_warnings: list[str] = []

        def fetch_rows(rows, *, required: bool) -> None:
            for symbol, name, category, path, currency in rows:
                url = path if str(path).startswith(("http://", "https://")) else f"{self.base_url}{path}"
                try:
                    html = self._get_html(url)
                    quotes.append(
                        self._instrument_quote(
                            html,
                            symbol=symbol,
                            name=name,
                            category=category,
                            source_url=url,
                            currency=currency,
                            observed_at=observed_at,
                        )
                    )
                except InvestingCircuitOpen as exc:
                    target = errors if required else optional_warnings
                    target.append(f"{symbol}: {exc}")
                    break
                except Exception as exc:
                    target = errors if required else optional_warnings
                    target.append(f"{symbol}: {exc}")

        fetch_rows(self.instrument_pages, required=True)
        fetch_rows(self.optional_instrument_pages, required=False)
        return quotes, errors, optional_warnings

    @staticmethod
    def _find_market_table(soup: BeautifulSoup, required_text: str) -> Any | None:
        for table in soup.find_all("table"):
            compact = " ".join(table.get_text(" ", strip=True).split()).lower()
            if required_text.lower() in compact and ("var" in compact or "yield" in compact or "rendimento" in compact):
                return table
        return None

    def _fetch_adrs(self, observed_at: datetime) -> tuple[list[Quote], str]:
        url = f"{self.base_url}/equities/brazil-adrs"
        html = self._get_html(url, cache_ttl=settings.INVESTING_ADR_CACHE_SECONDS)
        soup = BeautifulSoup(html, "lxml")
        table = self._find_market_table(soup, "último") or self._find_market_table(soup, "last")
        if table is None:
            return [], "Tabela de ADRs não encontrada."

        quotes: list[Quote] = []
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 7:
                continue
            link = row.find("a", href=re.compile(r"/equities/"))
            if link is None:
                continue
            name = link.get_text(" ", strip=True)
            href = str(link.get("href", "")).lower()
            symbol = ""
            for token, mapped in self.adr_symbol_map.items():
                if token in href:
                    symbol = mapped
                    break
            if not symbol:
                slug = href.rstrip("/").split("/")[-1]
                symbol = re.sub(r"[^A-Z0-9]", "", slug.upper())[:12]
            value = parse_number_pt_br(cells[2].get_text(" ", strip=True))
            change_pct = parse_percent(cells[6].get_text(" ", strip=True))
            if value is None and change_pct is None:
                continue
            quotes.append(
                Quote(
                    symbol=symbol,
                    name=name,
                    category="adr",
                    source=self.name,
                    observed_at=observed_at,
                    value=value,
                    high=parse_number_pt_br(cells[3].get_text(" ", strip=True)),
                    low=parse_number_pt_br(cells[4].get_text(" ", strip=True)),
                    change_percent=change_pct,
                    currency="USD",
                    source_url=url,
                )
            )
        return quotes, "" if quotes else "Nenhuma ADR pôde ser normalizada."

    def _fetch_bonds(self, observed_at: datetime) -> tuple[list[Quote], list[str]]:
        definitions = [
            ("BR", "/rates-bonds/brazil-government-bonds"),
            ("US", "/rates-bonds/usa-government-bonds"),
        ]
        quotes: list[Quote] = []
        errors: list[str] = []
        for country, path in definitions:
            url = f"{self.base_url}{path}"
            try:
                soup = BeautifulSoup(
                    self._get_html(url, cache_ttl=settings.INVESTING_BONDS_CACHE_SECONDS),
                    "lxml",
                )
                table = self._find_market_table(soup, "rendimento") or self._find_market_table(soup, "yield")
                if table is None:
                    raise ValueError("Tabela de títulos não encontrada.")
                for row in table.find_all("tr"):
                    cells = row.find_all("td")
                    if len(cells) < 3:
                        continue
                    link = row.find("a")
                    name = link.get_text(" ", strip=True) if link else cells[1].get_text(" ", strip=True)
                    lowered = name.lower()
                    tenor = None
                    if any(token in lowered for token in ("1 ano", "1-year", "1 year")):
                        tenor = "1Y"
                    elif any(token in lowered for token in ("2 anos", "2-year", "2 year")):
                        tenor = "2Y"
                    elif any(token in lowered for token in ("10 anos", "10-year", "10 year")):
                        tenor = "10Y"
                    if tenor is None:
                        continue
                    value = parse_number_pt_br(cells[2].get_text(" ", strip=True))
                    if value is None:
                        continue
                    quotes.append(
                        Quote(
                            symbol=f"{country}_{tenor}_YIELD",
                            name=name,
                            category="bond_yield",
                            source=self.name,
                            observed_at=observed_at,
                            value=value,
                            currency="% a.a.",
                            source_url=url,
                        )
                    )
            except Exception as exc:
                errors.append(f"{country} bonds: {exc}")
        return quotes, errors

    def fetch(self) -> SourceResult:
        started = time.monotonic()
        fetched_at = django_timezone.now()
        if not settings.INVESTING_ENABLED:
            return SourceResult(
                name=self.name,
                ok=False,
                complete=False,
                fetched_at=fetched_at,
                error="Fonte desabilitada por INVESTING_ENABLED=False.",
                metadata={"provider": "Investing.com"},
            )

        quotes, errors, optional_warnings = self._fetch_instruments(fetched_at)
        try:
            adr_quotes, adr_error = self._fetch_adrs(fetched_at)
            quotes.extend(adr_quotes)
            if adr_error:
                errors.append(f"ADRs: {adr_error}")
        except Exception as exc:
            errors.append(f"ADRs: {exc}")

        bond_quotes, bond_errors = self._fetch_bonds(fetched_at)
        quotes.extend(bond_quotes)
        errors.extend(bond_errors)

        groups = {
            "adrs": [quote.as_dict() for quote in quotes if quote.category == "adr"],
            "bonds": [quote.as_dict() for quote in quotes if quote.category == "bond_yield"],
        }
        validation_rows = {
            quote.symbol: quote.raw.get("validation", {})
            for quote in quotes
            if isinstance(quote.raw, dict) and isinstance(quote.raw.get("validation"), dict)
        }
        corrected_symbols = [
            symbol for symbol, validation in validation_rows.items()
            if validation.get("change_corrected")
        ]
        validation_warnings = [
            symbol for symbol, validation in validation_rows.items()
            if validation.get("validation_status") == "price_reference_mismatch"
        ]
        return SourceResult(
            name=self.name,
            ok=bool(quotes),
            complete=bool(quotes) and not errors,
            fetched_at=fetched_at,
            quotes=quotes,
            groups=groups,
            error=" | ".join(errors),
            metadata={
                "provider": "Investing.com",
                "requested_instruments": [
                    row[0] for row in (*self.instrument_pages, *self.optional_instrument_pages)
                ],
                "optional_instrument_warnings": optional_warnings,
                "corrected_change_symbols": corrected_symbols,
                "price_reference_mismatch_symbols": validation_warnings,
                "validation_method": (
                    "Percentual da página preservado; sinal corrigido apenas quando preço atual e "
                    "fechamento anterior confirmam a mesma magnitude."
                ),
                "http_diagnostics": self.http.diagnostics.as_dict(),
            },
            duration_ms=int((time.monotonic() - started) * 1000),
        )
