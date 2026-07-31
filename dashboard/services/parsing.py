from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

_MINUS_CHARS = "−–—"
_MISSING_VALUES = {"", "-", "--", "N/A", "n/a", "null", "None"}


def _normalize_minus(text: str) -> str:
    for char in _MINUS_CHARS:
        text = text.replace(char, "-")
    return text


def parse_number(value: Any) -> float | None:
    """Converte números em formatos pt-BR/en-US preservando o sinal.

    Parênteses sem sinal explícito continuam sendo aceitos como notação
    contábil negativa, por exemplo ``(1.234,56)``. Para percentuais exibidos
    entre parênteses por motivos visuais, use :func:`parse_percent`.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None

    text = _normalize_minus(str(value).strip())
    if text in _MISSING_VALUES:
        return None

    wrapped_in_parentheses = text.startswith("(") and text.endswith(")")
    inner = text[1:-1].strip() if wrapped_in_parentheses else text
    has_explicit_sign = inner.startswith(("+", "-"))
    negative_parentheses = wrapped_in_parentheses and not has_explicit_sign

    text = inner
    text = text.replace("%", "").replace("R$", "").replace("US$", "")
    text = text.replace("$", "").replace("\xa0", "").replace(" ", "")
    text = re.sub(r"[^0-9,\.\-+]", "", text)
    if text in _MISSING_VALUES or text in {"+", "-"}:
        return None

    sign = -1.0 if text.startswith("-") or negative_parentheses else 1.0
    text = text.lstrip("+-")

    if "," in text and "." in text:
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        text = text.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif "," in text:
        parts = text.split(",")
        if len(parts) > 2:
            text = "".join(parts[:-1]) + "." + parts[-1]
        else:
            text = text.replace(",", ".")
    elif text.count(".") > 1:
        parts = text.split(".")
        text = "".join(parts[:-1]) + "." + parts[-1]

    try:
        numeric = sign * float(text)
    except ValueError:
        return None
    return numeric if math.isfinite(numeric) else None


def parse_number_pt_br(value: Any) -> float | None:
    """Converte um número exibido em locale pt-BR.

    O Investing Brasil usa ponto como separador de milhar e vírgula como
    separador decimal. A função evita que ``177.866`` seja interpretado como
    ``177,866`` em vez de ``177866`` pontos do Ibovespa.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None

    text = _normalize_minus(str(value).strip())
    if text in _MISSING_VALUES:
        return None

    wrapped = text.startswith("(") and text.endswith(")")
    inner = text[1:-1].strip() if wrapped else text
    prefix = "-" if wrapped and not inner.startswith(("+", "-")) else ""

    cleaned = inner
    cleaned = cleaned.replace("%", "").replace("R$", "").replace("US$", "")
    cleaned = cleaned.replace("$", "").replace("\xa0", "").replace(" ", "")
    cleaned = re.sub(r"[^0-9,\.\-+]", "", cleaned)
    if cleaned in _MISSING_VALUES or cleaned in {"+", "-"}:
        return None

    sign = ""
    if cleaned.startswith(("+", "-")):
        sign, cleaned = cleaned[0], cleaned[1:]
    elif prefix:
        sign = prefix

    # Em pt-BR, todos os pontos são separadores de milhar e a vírgula é o
    # separador decimal. Isso também cobre 5.133,33 e 177.866.
    cleaned = cleaned.replace(".", "").replace(",", ".")

    try:
        numeric = float(f"{sign}{cleaned}")
    except ValueError:
        return None
    return numeric if math.isfinite(numeric) else None


def parse_percent(value: Any) -> float | None:
    """Converte percentuais sem tratar parênteses visuais como sinal negativo.

    O Investing costuma retornar ``(+2,97%)`` e ``(-0,42%)``. Na versão
    anterior, qualquer valor entre parênteses era considerado negativo, o que
    transformava altas em quedas. Aqui os parênteses são apenas removidos e o
    sinal explícito é preservado.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if math.isfinite(numeric) else None

    text = _normalize_minus(str(value).strip())
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    return parse_number(text)


def calculate_change_percent(
    value: Any,
    previous_close: Any,
) -> float | None:
    """Calcula a variação percentual entre preço atual e fechamento anterior."""
    current = parse_number(value)
    previous = parse_number(previous_close)
    if current is None or previous is None or previous == 0:
        return None
    calculated = ((current / previous) - 1.0) * 100.0
    return calculated if math.isfinite(calculated) else None


def reconcile_change_percent(
    scraped_change: Any,
    value: Any,
    previous_close: Any,
    *,
    absolute_tolerance: float = 0.08,
    relative_tolerance: float = 0.08,
) -> tuple[float | None, dict[str, Any]]:
    """Valida a variação raspada contra os preços disponíveis.

    A cotação informada pela página continua sendo a fonte principal. O valor
    derivado de ``value`` e ``previous_close`` só substitui o scraping quando:

    * a variação raspada está ausente; ou
    * existe conflito de sinal e as magnitudes são praticamente iguais.

    Isso corrige casos como IBOV ``-2,97%`` com preços que implicam ``+2,97%``,
    sem sobrescrever percentuais quando o campo ``previous_close`` da página é
    inconsistente ou representa outro instante.
    """
    scraped = parse_number(scraped_change)
    calculated = calculate_change_percent(value, previous_close)

    metadata: dict[str, Any] = {
        "scraped_change_percent": scraped,
        "calculated_change_percent": round(calculated, 6) if calculated is not None else None,
        "change_corrected": False,
        "validation_status": "not_validated",
        "validation_message": "",
    }

    if calculated is None:
        metadata["validation_message"] = "Preço atual ou fechamento anterior indisponível/inválido."
        return scraped, metadata

    if scraped is None:
        metadata.update(
            {
                "change_corrected": True,
                "validation_status": "calculated_from_prices",
                "validation_message": "Variação ausente; calculada pelo preço atual e fechamento anterior.",
            }
        )
        return calculated, metadata

    magnitude_gap = abs(abs(scraped) - abs(calculated))
    allowed_gap = max(absolute_tolerance, abs(calculated) * relative_tolerance)
    magnitude_matches = magnitude_gap <= allowed_gap
    sign_conflict = (
        abs(scraped) > absolute_tolerance
        and abs(calculated) > absolute_tolerance
        and (scraped > 0) != (calculated > 0)
    )

    if sign_conflict and magnitude_matches:
        metadata.update(
            {
                "change_corrected": True,
                "validation_status": "corrected_sign_from_prices",
                "validation_message": (
                    "Sinal raspado incompatível com preço atual e fechamento anterior; "
                    "magnitudes equivalentes."
                ),
            }
        )
        return calculated, metadata

    if magnitude_matches:
        metadata.update(
            {
                "validation_status": "confirmed_by_prices",
                "validation_message": "Variação compatível com preço atual e fechamento anterior.",
            }
        )
    else:
        metadata.update(
            {
                "validation_status": "price_reference_mismatch",
                "validation_message": (
                    "A variação da página diverge da derivada dos preços; mantido o percentual raspado "
                    "para não usar um fechamento anterior possivelmente incompatível."
                ),
            }
        )

    return scraped, metadata


def parse_epoch(value: Any, *, default: datetime | None = None) -> datetime:
    try:
        timestamp = float(value)
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (TypeError, ValueError, OSError, OverflowError):
        return default or datetime.now(tz=timezone.utc)


def parse_iso_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return datetime.now(tz=timezone.utc)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(tz=timezone.utc)
