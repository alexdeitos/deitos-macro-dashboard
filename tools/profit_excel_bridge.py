"""
Profit/Excel -> Django live bridge (Windows only).

This bridge reads the live in-memory Excel workbook through COM. It does NOT
read the .xlsm file from disk, so RTD values do not need to be saved first.

Run on the same Windows machine where Profit and Excel are running.
Default workbook: COTACOES(2).xlsm next to this script.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

EXCEL_ERROR_CODES = {
    2000: "#NULL!",
    2007: "#DIV/0!",
    2015: "#VALUE!",
    2023: "#REF!",
    2029: "#NAME?",
    2036: "#NUM!",
    2042: "#N/A",
    2043: "#GETTING_DATA",
    2047: "#SPILL!",
    2048: "#UNKNOWN!",
    2049: "#FIELD!",
}


def is_excel_error(value: Any) -> str | None:
    if isinstance(value, int) and value in EXCEL_ERROR_CODES:
        return EXCEL_ERROR_CODES[value]
    text = str(value).strip() if value is not None else ""
    if text.startswith("#") and "N/A" in text.upper():
        return "#N/A"
    if text.startswith("#"):
        return text
    return None


def number(value: Any) -> float | None:
    err = is_excel_error(value)
    if err:
        return None
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_excel_application():
    import win32com.client as win32

    try:
        return win32.GetActiveObject("Excel.Application"), False
    except Exception:
        app = win32.DispatchEx("Excel.Application")
        app.Visible = False
        return app, True


def find_or_open_workbook(excel, workbook_path: Path):
    target = str(workbook_path.resolve()).lower()

    for wb in excel.Workbooks:
        try:
            if str(wb.FullName).lower() == target:
                return wb, False
        except Exception:
            continue

    if not workbook_path.exists():
        raise FileNotFoundError(f"Workbook não encontrado: {workbook_path}")

    wb = excel.Workbooks.Open(
        str(workbook_path.resolve()),
        UpdateLinks=0,
        ReadOnly=False,
        AddToMru=False,
    )
    return wb, True


def read_config_capture(workbook):
    try:
        ws = workbook.Worksheets("CONFIG_CAPTURA")
    except Exception as exc:
        raise RuntimeError("Aba CONFIG_CAPTURA não encontrada.") from exc

    last_row = ws.Cells(ws.Rows.Count, 1).End(-4162).Row  # xlUp
    if last_row < 10:
        return [], {"last_row": last_row, "error_cells": 0}

    values = ws.Range(f"A10:E{last_row}").Value2

    # COM returns a scalar for a one-cell range and tuples otherwise.
    if last_row == 10:
        values = (values,)

    rows = []
    error_cells = 0
    for row in values:
        row = list(row) if isinstance(row, (tuple, list)) else [row]
        while len(row) < 5:
            row.append(None)

        symbol = str(row[0] or "").strip().upper()
        if not symbol:
            continue

        err = is_excel_error(row[1])
        if err:
            error_cells += 1
            continue

        value = number(row[1])
        if value is None:
            continue

        rows.append(
            {
                "symbol": symbol,
                "sheet": "CONFIG_CAPTURA",
                "value": value,
                "change_percent": number(row[2]),
                "trades": number(row[3]),
                "volume": number(row[4]),
                "source": "profit_excel_com",
            }
        )

    return rows, {"last_row": last_row, "error_cells": error_cells}


def post_snapshot(url: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%S-03:00"),
        "source": "profit_excel_com",
        "rows": rows,
    }
    response = requests.post(url, json=payload, timeout=15)
    response.raise_for_status()
    return response.json()


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    workbook_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    api_url = os.getenv(
        "DJANGO_CAPTURE_URL",
        "http://127.0.0.1:8000/api/capturas/ingest/",
    )
    interval = int(os.getenv("BRIDGE_INTERVAL_SECONDS", "60"))

    workbook_path = Path(workbook_arg) if workbook_arg else script_dir.parent / "COTACOES(2).xlsm"
    workbook_path = workbook_path.expanduser()

    print("=== Profit Excel Live Bridge ===")
    print(f"Workbook: {workbook_path}")
    print(f"Django:   {api_url}")
    print(f"Intervalo: {interval}s")
    print("Deixe o Profit aberto e a planilha com CONFIG_CAPTURA carregada.")
    print("Pressione Ctrl+C para parar.")

    excel = None
    excel_started_here = False
    opened_here = False
    workbook = None

    try:
        excel, excel_started_here = get_excel_application()
        workbook, opened_here = find_or_open_workbook(excel, workbook_path)

        while True:
            try:
                # Ask Excel to process pending RTD updates before reading.
                try:
                    excel.Calculate()
                except Exception:
                    pass

                rows, diagnostics = read_config_capture(workbook)
                if not rows:
                    print(
                        f"[{time.strftime('%H:%M:%S')}] SEM DADOS LIVE. "
                        f"Células com erro: {diagnostics['error_cells']}. "
                        "Verifique o RTDTrading.RTDServer no Excel."
                    )
                else:
                    result = post_snapshot(api_url, rows)
                    print(
                        f"[{time.strftime('%H:%M:%S')}] OK: "
                        f"{len(rows)} ativos enviados ao Django."
                    )
                    if diagnostics["error_cells"]:
                        print(
                            f"  Aviso: {diagnostics['error_cells']} células RTD "
                            "estão retornando erro e foram ignoradas."
                        )
                    if result.get("ok") is False:
                        print(f"  Resposta Django: {result}")
            except Exception as exc:
                print(f"[{time.strftime('%H:%M:%S')}] ERRO: {exc}")

            time.sleep(max(1, interval))
    except KeyboardInterrupt:
        print("\nBridge encerrada.")
        return 0
    finally:
        # Do not close a workbook/Excel instance that belongs to the user.
        try:
            if opened_here and workbook is not None:
                workbook.Close(SaveChanges=False)
        except Exception:
            pass
        try:
            if excel_started_here and excel is not None:
                excel.Quit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
