#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Análise rápida dos dados de mercado da B3 para o próximo pregão.
Uso:
    py analise.py
ou:
    python analise.py

O script procura automaticamente por RELATORIO_DADOS_DE_MERCADO.csv
na mesma pasta do script. Também aceita o nome do arquivo como argumento:
    py analise.py outro_arquivo.csv

O segundo argumento opcional informa o CSV de fluxo estrangeiro diário:
    py analise.py RELATORIO_DADOS_DE_MERCADO.csv fluxo-estrangeiro.csv
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path
from statistics import mean


DEFAULT_FILE = "RELATORIO_DADOS_DE_MERCADO.csv"
DEFAULT_FOREIGN_FILE = "fluxo-estrangeiro.csv"
VERSION = "2.1 — valores monetários exibidos em bilhões (bi) + fluxo estrangeiro diário"


def parse_br_number(value: str) -> float:
    """Converte 1.234,56 / 1234,56 / 12.3 para float."""
    if value is None:
        return 0.0
    s = str(value).strip().replace("\xa0", "")
    if not s:
        return 0.0
    s = s.replace("%", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_pct(value: str) -> float:
    return parse_br_number(value)


def load_rows(path: Path) -> list[list[str]]:
    """Lê o CSV B3 tolerando linhas de cabeçalho diferentes."""
    for enc in ("cp1252", "latin1", "utf-8-sig"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                return list(csv.reader(f, delimiter=";"))
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Não consegui ler o arquivo: {path}")


def clean_label(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def find_row(rows: list[list[str]], first_cell_prefix: str) -> list[str] | None:
    prefix = first_cell_prefix.lower()
    for row in rows:
        if row and clean_label(row[0]).lower().startswith(prefix):
            return [clean_label(x) for x in row]
    return None


def find_section_start(rows: list[list[str]], needle: str) -> int:
    needle = needle.lower()
    for i, row in enumerate(rows):
        joined = " ".join(row).lower()
        if needle in joined:
            return i
    return -1


def parse_volume(rows: list[list[str]]) -> dict:
    start = find_section_start(rows, "Volume Total")
    if start < 0:
        raise ValueError("Seção 'Volume Total' não encontrada.")
    months = []
    for row in rows[start + 2 :]:
        if not row:
            continue
        label = clean_label(row[0])
        if re.match(r"^(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)/", label, re.I):
            if len(row) >= 6:
                months.append({"period": label, "total": parse_br_number(row[5])})
        elif label.startswith("2026("):
            if len(row) >= 6:
                ytd = {"period": label, "total": parse_br_number(row[5])}
                return {"months": months, "ytd": ytd}
    return {"months": months, "ytd": None}


def parse_daily_volume(rows: list[list[str]]) -> dict:
    start = find_section_start(rows, "Volume Médio Diário")
    if start < 0:
        raise ValueError("Seção 'Volume Médio Diário' não encontrada.")
    months = []
    ytd = None
    for row in rows[start + 2 :]:
        if not row:
            continue
        label = clean_label(row[0])
        if re.match(r"^(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)/", label, re.I):
            if len(row) >= 3:
                months.append({"period": label, "brl_m": parse_br_number(row[1]), "var_pct": parse_pct(row[2])})
        elif label.startswith("2026("):
            if len(row) >= 3:
                ytd = {"period": label, "brl_m": parse_br_number(row[1]), "var_pct": parse_pct(row[2])}
                break
    return {"months": months, "ytd": ytd}


def parse_trades(rows: list[list[str]]) -> dict:
    start = find_section_start(rows, "Nº de Negócios Total")
    if start < 0:
        # fallback for encoding oddities
        start = find_section_start(rows, "Negócios Total")
    if start < 0:
        raise ValueError("Seção de número de negócios não encontrada.")
    months = []
    ytd = None
    for row in rows[start + 2 :]:
        if not row:
            continue
        label = clean_label(row[0])
        if re.match(r"^(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)/", label, re.I):
            if len(row) >= 6:
                months.append({"period": label, "trades": int(parse_br_number(row[5]))})
        elif label.startswith("2026("):
            if len(row) >= 6:
                ytd = {"period": label, "trades": int(parse_br_number(row[5]))}
                break
    return {"months": months, "ytd": ytd}


def parse_daily_trades(rows: list[list[str]]) -> dict:
    start = find_section_start(rows, "Nº de Negócios Médio Diário")
    if start < 0:
        raise ValueError("Seção de média diária de negócios não encontrada.")
    months = []
    ytd = None
    for row in rows[start + 2 :]:
        if not row:
            continue
        label = clean_label(row[0])
        if re.match(r"^(jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)/", label, re.I):
            if len(row) >= 3:
                months.append({"period": label, "trades_daily": int(parse_br_number(row[1])), "var_pct": parse_pct(row[2])})
        elif label.startswith("2026("):
            if len(row) >= 3:
                ytd = {"period": label, "trades_daily": int(parse_br_number(row[1])), "var_pct": parse_pct(row[2])}
                break
    return {"months": months, "ytd": ytd}


def parse_participation(rows: list[list[str]]) -> dict:
    start = find_section_start(rows, "PARTICIPAÇÃO DOS INVESTIDORES")
    if start < 0:
        raise ValueError("Seção de participação dos investidores não encontrada.")
    months = []
    ytd = None
    for row in rows[start + 3 :]:
        if not row:
            continue
        label = clean_label(row[0])
        if re.match(r"^(Jan|Fev|Mar|Abr|Mai|Jun|Jul|Ago|Set|Out|Nov|Dez)/", label, re.I):
            if len(row) >= 6:
                months.append({
                    "period": label,
                    "individuals": parse_pct(row[1]),
                    "institutions": parse_pct(row[2]),
                    "foreign": parse_pct(row[3]),
                    "financial": parse_pct(row[4]),
                    "others": parse_pct(row[5]),
                })
        elif label.startswith("2026("):
            if len(row) >= 6:
                ytd = {
                    "period": label,
                    "individuals": parse_pct(row[1]),
                    "institutions": parse_pct(row[2]),
                    "foreign": parse_pct(row[3]),
                    "financial": parse_pct(row[4]),
                    "others": parse_pct(row[5]),
                }
                break
    return {"months": months, "ytd": ytd}


def parse_foreign_flow(rows: list[list[str]]) -> dict:
    start = find_section_start(rows, "Movimentação dos Investidores Estrangeiros")
    if start < 0:
        raise ValueError("Seção de fluxo estrangeiro não encontrada.")
    months = []
    ytd = None
    for row in rows[start + 2 :]:
        if not row:
            continue
        label = clean_label(row[0])
        if re.match(r"^(Jan|Fev|Mar|Abr|Mai|Jun|Jul|Ago|Set|Out|Nov|Dez)/", label, re.I):
            if len(row) >= 5:
                months.append({
                    "period": label,
                    "buy": parse_br_number(row[1]),
                    "sell": parse_br_number(row[2]),
                    "ipo": parse_br_number(row[3]),
                    "balance": parse_br_number(row[4]),
                })
        elif label.startswith("2026("):
            if len(row) >= 5:
                ytd = {
                    "period": label,
                    "buy": parse_br_number(row[1]),
                    "sell": parse_br_number(row[2]),
                    "ipo": parse_br_number(row[3]),
                    "balance": parse_br_number(row[4]),
                }
                break
    return {"months": months, "ytd": ytd}



def parse_foreign_daily_file(path: Path) -> dict:
    """
    Lê o CSV diário de fluxo estrangeiro gerado pelo scraping.

    Esperado:
        Data, Estrangeiro, Institucional, Pessoa física, Inst. Financeira, Outros

    Os valores vêm em 'mi', por exemplo:
        -1.195,31 mi
         2.362,18 mi
    """

    if not path.exists():
        raise FileNotFoundError(f"Arquivo de fluxo estrangeiro não encontrado: {path}")

    rows = []

    last_error = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            with path.open("r", encoding=enc, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if not row:
                        continue

                    data_raw = clean_label(row.get("Data", ""))
                    estrangeiro_raw = clean_label(row.get("Estrangeiro", ""))

                    if not data_raw or not estrangeiro_raw:
                        continue

                    try:
                        # O CSV é dd/mm/aaaa.
                        date = __import__("datetime").datetime.strptime(
                            data_raw, "%d/%m/%Y"
                        ).date()
                    except ValueError:
                        continue

                    # Remove "mi" e converte padrão brasileiro.
                    foreign_mi = parse_br_number(
                        estrangeiro_raw.lower().replace("mi", "").strip()
                    )

                    rows.append({
                        "date": date,
                        "foreign_mi": foreign_mi,
                        "raw": row,
                    })

            break
        except UnicodeDecodeError as exc:
            last_error = exc
            continue

    if not rows:
        if last_error:
            raise RuntimeError(f"Não consegui decodificar o arquivo: {path}") from last_error
        raise ValueError(f"Nenhum registro válido encontrado em: {path}")

    rows.sort(key=lambda x: x["date"], reverse=True)

    # Remove duplicidade de data, mantendo a primeira ocorrência.
    seen = set()
    clean_rows = []
    for item in rows:
        if item["date"] in seen:
            continue
        seen.add(item["date"])
        clean_rows.append(item)

    rows = clean_rows

    latest = rows[0]
    last5 = rows[:5]
    last20 = rows[:20]

    latest_date = latest["date"]

    # Mês do último registro disponível.
    month_rows = [
        x for x in rows
        if x["date"].year == latest_date.year
        and x["date"].month == latest_date.month
    ]

    # Acumulados.
    sum5 = sum(x["foreign_mi"] for x in last5)
    sum20 = sum(x["foreign_mi"] for x in last20)
    sum_month = sum(x["foreign_mi"] for x in month_rows)

    # Janela anterior de 5 pregões para avaliar aceleração/desaceleração.
    prev5 = rows[5:10]
    sum_prev5 = sum(x["foreign_mi"] for x in prev5)

    change_5d_vs_prev5 = (
        sum5 - sum_prev5
        if prev5
        else 0.0
    )

    avg20 = (
        sum20 / len(last20)
        if last20
        else 0.0
    )

    positive_days_20 = sum(
        1 for x in last20
        if x["foreign_mi"] > 0
    )

    negative_days_20 = sum(
        1 for x in last20
        if x["foreign_mi"] < 0
    )

    # Sequência atual de entrada/saída.
    latest_sign = (
        1 if latest["foreign_mi"] > 0
        else -1 if latest["foreign_mi"] < 0
        else 0
    )

    streak = 0

    if latest_sign != 0:
        for item in rows:
            sign = (
                1 if item["foreign_mi"] > 0
                else -1 if item["foreign_mi"] < 0
                else 0
            )
            if sign != latest_sign:
                break
            streak += 1

    # Maior entrada/saída dentro dos últimos 20 pregões.
    max_in = max(last20, key=lambda x: x["foreign_mi"]) if last20 else None
    max_out = min(last20, key=lambda x: x["foreign_mi"]) if last20 else None

    # Leitura objetiva do fluxo diário.
    if latest["foreign_mi"] > 1000:
        daily_read = "FORTE ENTRADA"
    elif latest["foreign_mi"] > 0:
        daily_read = "ENTRADA"
    elif latest["foreign_mi"] < -1000:
        daily_read = "FORTE SAÍDA"
    elif latest["foreign_mi"] < 0:
        daily_read = "SAÍDA"
    else:
        daily_read = "NEUTRO"

    if sum5 > 2000:
        last5_read = "ENTRADA FORTE"
    elif sum5 > 0:
        last5_read = "ENTRADA"
    elif sum5 < -2000:
        last5_read = "SAÍDA FORTE"
    elif sum5 < 0:
        last5_read = "SAÍDA"
    else:
        last5_read = "NEUTRO"

    if sum20 > 5000:
        last20_read = "ENTRADA FORTE"
    elif sum20 > 0:
        last20_read = "ENTRADA"
    elif sum20 < -5000:
        last20_read = "SAÍDA FORTE"
    elif sum20 < 0:
        last20_read = "SAÍDA"
    else:
        last20_read = "NEUTRO"

    # Score independente do fluxo diário.
    # Não altera o score original do seu relatório.
    daily_score = 0

    if sum5 > 2000:
        daily_score += 2
    elif sum5 > 0:
        daily_score += 1
    elif sum5 < -2000:
        daily_score -= 2
    elif sum5 < 0:
        daily_score -= 1

    if sum20 > 5000:
        daily_score += 2
    elif sum20 < -5000:
        daily_score -= 2

    if latest["foreign_mi"] > 1000:
        daily_score += 1
    elif latest["foreign_mi"] < -1000:
        daily_score -= 1

    if daily_score >= 4:
        daily_context = "FORTE ENTRADA ESTRANGEIRA"
    elif daily_score >= 2:
        daily_context = "ENTRADA ESTRANGEIRA"
    elif daily_score <= -4:
        daily_context = "FORTE SAÍDA ESTRANGEIRA"
    elif daily_score <= -2:
        daily_context = "SAÍDA ESTRANGEIRA"
    else:
        daily_context = "FLUXO ESTRANGEIRO MISTO/NEUTRO"

    return {
        "path": path,
        "rows": rows,
        "latest": latest,
        "last5": last5,
        "last20": last20,
        "month_rows": month_rows,
        "sum5": sum5,
        "sum20": sum20,
        "sum_month": sum_month,
        "sum_prev5": sum_prev5,
        "change_5d_vs_prev5": change_5d_vs_prev5,
        "avg20": avg20,
        "positive_days_20": positive_days_20,
        "negative_days_20": negative_days_20,
        "streak": streak,
        "streak_direction": (
            "entrada" if latest_sign > 0
            else "saída" if latest_sign < 0
            else "neutro"
        ),
        "max_in": max_in,
        "max_out": max_out,
        "daily_read": daily_read,
        "last5_read": last5_read,
        "last20_read": last20_read,
        "daily_score": daily_score,
        "daily_context": daily_context,
    }


def fmt_brl_bi(v: float) -> str:
    return f"R$ {v/1000:,.2f} bi".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(v: float) -> str:
    sinal = "+" if v > 0 else ""
    return f"{sinal}{v:.2f}%".replace(".", ",")


def fmt_int(v: int) -> str:
    return f"{v:,}".replace(",", ".")


def compute(volume, daily_vol, daily_trades, participation, foreign):
    latest = volume["months"][-1]
    latest_daily = daily_vol["months"][-1]
    prev_daily = daily_vol["months"][-2]
    latest_trade = daily_trades["months"][-1]
    prev_trade = daily_trades["months"][-2]
    foreign_latest = foreign["months"][-1]
    foreign_ytd = foreign["ytd"]

    # Médias simples de referência: últimos 3 meses completos antes do mês atual.
    ref3 = daily_vol["months"][-4:-1] if len(daily_vol["months"]) >= 4 else daily_vol["months"][:-1]
    avg3 = mean(x["brl_m"] for x in ref3) if ref3 else latest_daily["brl_m"]

    trade_ref3 = daily_trades["months"][-4:-1] if len(daily_trades["months"]) >= 4 else daily_trades["months"][:-1]
    avg_trade3 = mean(x["trades_daily"] for x in trade_ref3) if trade_ref3 else latest_trade["trades_daily"]

    vol_vs_3m = (latest_daily["brl_m"] / avg3 - 1) * 100 if avg3 else 0
    trades_vs_3m = (latest_trade["trades_daily"] / avg_trade3 - 1) * 100 if avg_trade3 else 0
    foreign_vs_prev = foreign_latest["balance"] - foreign["months"][-2]["balance"]
    foreign_last3 = sum(x["balance"] for x in foreign["months"][-3:])

    # Score de contexto: não é previsão de mercado; é um termômetro operacional.
    score = 0
    reasons = []
    if vol_vs_3m >= 10:
        score += 2; reasons.append("volume forte")
    elif vol_vs_3m >= 0:
        score += 1; reasons.append("volume normal/aceitável")
    elif vol_vs_3m <= -15:
        score -= 2; reasons.append("volume fraco")
    else:
        score -= 1; reasons.append("volume abaixo da média")

    if trades_vs_3m >= 10:
        score += 1; reasons.append("muitos negócios")
    elif trades_vs_3m <= -10:
        score -= 1; reasons.append("poucos negócios")

    if foreign_latest["balance"] > 5000:
        score += 2; reasons.append("estrangeiro comprador")
    elif foreign_latest["balance"] < -5000:
        score -= 2; reasons.append("estrangeiro vendedor")
    else:
        reasons.append("fluxo estrangeiro neutro")

    if foreign_ytd and foreign_ytd["balance"] > 0:
        reasons.append("ano ainda com entrada líquida estrangeira")
    elif foreign_ytd:
        reasons.append("ano com saída líquida estrangeira")

    if score >= 3:
        context = "FAVORÁVEL"
    elif score >= 1:
        context = "NEUTRO A FAVORÁVEL"
    elif score <= -3:
        context = "CAUTELA / PRESSÃO"
    else:
        context = "NEUTRO"

    return {
        "latest": latest,
        "latest_daily": latest_daily,
        "prev_daily": prev_daily,
        "latest_trade": latest_trade,
        "prev_trade": prev_trade,
        "foreign_latest": foreign_latest,
        "foreign_ytd": foreign_ytd,
        "avg3": avg3,
        "avg_trade3": avg_trade3,
        "vol_vs_3m": vol_vs_3m,
        "trades_vs_3m": trades_vs_3m,
        "foreign_vs_prev": foreign_vs_prev,
        "foreign_last3": foreign_last3,
        "score": score,
        "context": context,
        "reasons": reasons,
        "participation": participation,
    }


def print_report(path: Path, d: dict, foreign_daily: dict | None = None):
    f = d["foreign_latest"]
    fy = d["foreign_ytd"]
    p = d["participation"]["ytd"]

    print("\n" + "=" * 72)
    print("  ANÁLISE DE MERCADO — PREPARAÇÃO PARA O PRÓXIMO PREGÃO")
    print("=" * 72)
    print(f"Arquivo: {path.name}")
    print("Fonte: relatório de dados de mercado da B3")
    print(f"Versão: {VERSION}")
    print("Nota: este relatório mede fluxo/atividade. NÃO prevê sozinho a direção do WIN/IBOV.\n")

    print("[1] FLUXO ESTRANGEIRO — O DADO MAIS IMPORTANTE")
    print(f"  Último mês ({f['period']}): {fmt_brl_bi(f['balance'])} líquidos")
    if f["balance"] > 0:
        print("  Leitura: ESTRANGEIROS COMPRARAM MAIS DO QUE VENDERAM.")
    elif f["balance"] < 0:
        print("  Leitura: ESTRANGEIROS VENDERAM MAIS DO QUE COMPRARAM.")
    else:
        print("  Leitura: fluxo praticamente neutro.")
    print(f"  Compras: {fmt_brl_bi(f['buy'])} | Vendas: {fmt_brl_bi(f['sell'])} | IPO/Follow-on: {fmt_brl_bi(f['ipo'])}")
    if fy:
        print(f"  Acumulado 2026: {fmt_brl_bi(fy['balance'])} líquidos")
        if fy["balance"] > 0:
            print("  Acumulado: ainda há ENTRADA líquida de capital estrangeiro no ano.")
        else:
            print("  Acumulado: há SAÍDA líquida de capital estrangeiro no ano.")
    print(f"  Últimos 3 meses somados: {fmt_brl_bi(d['foreign_last3'])}")

    if foreign_daily:
        fd = foreign_daily
        latest_fd = fd["latest"]

        print("\n[1B] FLUXO ESTRANGEIRO DIÁRIO — DADO DO SCRAPING")
        print(
            f"  Último pregão disponível ({latest_fd['date'].strftime('%d/%m/%Y')}): "
            f"{fmt_brl_bi(latest_fd['foreign_mi'])} líquidos"
        )
        print(f"  Leitura do último dia: {fd['daily_read']}")
        print(f"  Acumulado 5 pregões:  {fmt_brl_bi(fd['sum5'])} | {fd['last5_read']}")
        print(f"  Acumulado 20 pregões: {fmt_brl_bi(fd['sum20'])} | {fd['last20_read']}")
        print(f"  Acumulado no mês:     {fmt_brl_bi(fd['sum_month'])}")
        print(
            f"  Média diária dos últimos 20 pregões: "
            f"{fmt_brl_bi(fd['avg20'])}"
        )
        print(
            f"  Últimos 20 pregões: {fd['positive_days_20']} dias de entrada | "
            f"{fd['negative_days_20']} dias de saída"
        )

        if fd["streak"] > 0:
            print(
                f"  Sequência atual: {fd['streak']} pregões consecutivos de "
                f"{fd['streak_direction']}."
            )

        if fd["sum_prev5"] != 0:
            sinal = "+" if fd["change_5d_vs_prev5"] > 0 else ""
            print(
                f"  Comparação com os 5 pregões anteriores: "
                f"{sinal}{fmt_brl_bi(fd['change_5d_vs_prev5'])}"
            )

        if fd["max_in"]:
            print(
                f"  Maior entrada nos 20D: "
                f"{fmt_brl_bi(fd['max_in']['foreign_mi'])} "
                f"({fd['max_in']['date'].strftime('%d/%m/%Y')})"
            )

        if fd["max_out"]:
            print(
                f"  Maior saída nos 20D: "
                f"{fmt_brl_bi(fd['max_out']['foreign_mi'])} "
                f"({fd['max_out']['date'].strftime('%d/%m/%Y')})"
            )

        print(
            f"  Termômetro do fluxo diário: "
            f"{fd['daily_context']} | score: {fd['daily_score']:+d}"
        )

    print("\n[2] VOLUME — O MERCADO ESTÁ LÍQUIDO OU FRACO?")
    print(f"  Volume médio diário no último mês: {fmt_brl_bi(d['latest_daily']['brl_m'])}")
    print(f"  Média dos 3 meses anteriores:     {fmt_brl_bi(d['avg3'])}")
    print(f"  Diferença: {fmt_pct(d['vol_vs_3m'])}")
    if d["vol_vs_3m"] >= 10:
        print("  Leitura: VOLUME FORTE — ambiente mais favorável para execução/day trade.")
    elif d["vol_vs_3m"] >= 0:
        print("  Leitura: VOLUME OK — liquidez aceitável.")
    else:
        print("  Leitura: VOLUME ABAIXO DA MÉDIA — atenção a movimentos mais pobres/irregulares.")

    print("\n[3] QUANTIDADE DE NEGÓCIOS — ATIVIDADE")
    print(f"  Média diária no último mês: {fmt_int(d['latest_trade']['trades_daily'])}")
    print(f"  Média dos 3 meses anteriores: {fmt_int(round(d['avg_trade3']))}")
    print(f"  Diferença: {fmt_pct(d['trades_vs_3m'])}")
    if d["trades_vs_3m"] >= 10:
        print("  Leitura: ATIVIDADE FORTE.")
    elif d["trades_vs_3m"] <= -10:
        print("  Leitura: ATIVIDADE FRACA.")
    else:
        print("  Leitura: atividade dentro de uma faixa normal.")

    print("\n[4] QUEM ESTÁ MEXENDO NA BOLSA?")
    if p:
        print(f"  Estrangeiros:  {p['foreign']:.1f}%")
        print(f"  Institucionais:{p['institutions']:.1f}%")
        print(f"  Pessoas físicas:{p['individuals']:.1f}%")
    print("  Interpretação: o estrangeiro é o maior participante; portanto, o fluxo estrangeiro merece peso alto na leitura macro do IBOV/WIN.")

    print("\n[5] TERMÔMETRO PARA O PRÓXIMO PREGÃO")
    print(f"  CONTEXTO: {d['context']}  |  score interno: {d['score']:+d}")
    print("  " + "; ".join(d["reasons"]))

    print("\n[6] CHECKLIST DE 20 SEGUNDOS")
    print("  1. Estrangeiro do último mês: " + ("ENTRANDO ✅" if f["balance"] > 5000 else "SAINDO ⚠️" if f["balance"] < -5000 else "NEUTRO ➖"))
    print("  2. Acumulado do ano: " + ("POSITIVO ✅" if fy and fy["balance"] > 0 else "NEGATIVO ⚠️" if fy else "N/D"))
    print("  3. Volume: " + ("FORTE ✅" if d["vol_vs_3m"] >= 10 else "OK ➖" if d["vol_vs_3m"] >= 0 else "FRACO ⚠️"))
    print("  4. Negócios: " + ("FORTE ✅" if d["trades_vs_3m"] >= 10 else "NORMAL ➖" if d["trades_vs_3m"] > -10 else "FRACO ⚠️"))
    print("  5. Regra prática: fluxo estrangeiro + volume + preço/estrutura devem apontar para o mesmo lado antes de aumentar a mão.")
    if foreign_daily:
        print("  6. Fluxo diário 5D: " + (
            "ENTRANDO ✅" if foreign_daily["sum5"] > 0
            else "SAINDO ⚠️" if foreign_daily["sum5"] < 0
            else "NEUTRO ➖"
        ))
        print("  7. Fluxo diário 20D: " + (
            "ENTRANDO ✅" if foreign_daily["sum20"] > 0
            else "SAINDO ⚠️" if foreign_daily["sum20"] < 0
            else "NEUTRO ➖"
        ))
        print("  8. Não confundir fluxo diário com direção intraday: confirme com preço, DXY, juros e estrutura.")

    print("\n" + "=" * 72)
    print("RESUMO PARA DAY TRADER")
    print("=" * 72)
    print(f"Estrangeiro no último mês: {fmt_brl_bi(f['balance'])} | Acumulado 2026: {fmt_brl_bi(fy['balance']) if fy else 'N/D'}")
    print(f"Volume médio diário: {fmt_brl_bi(d['latest_daily']['brl_m'])} ({fmt_pct(d['vol_vs_3m'])} vs. média anterior)")
    print(f"Negócios/dia: {fmt_int(d['latest_trade']['trades_daily'])} ({fmt_pct(d['trades_vs_3m'])} vs. média anterior)")
    if foreign_daily:
        print(
            f"Fluxo estrangeiro diário: "
            f"{fmt_brl_bi(foreign_daily['latest']['foreign_mi'])} | "
            f"5D: {fmt_brl_bi(foreign_daily['sum5'])} | "
            f"20D: {fmt_brl_bi(foreign_daily['sum20'])}"
        )
    print(f"Conclusão de contexto: {d['context']}")
    print("Importante: use isto como filtro de contexto, não como sinal de compra/venda isolado.")
    print("=" * 72 + "\n")


def main():
    base = Path(__file__).resolve().parent
    input_name = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FILE
    path = Path(input_name)
    if not path.is_absolute():
        path = base / path

    # NOVA FONTE: fluxo estrangeiro diário.
    # É opcional: se o arquivo não existir, o código original continua funcionando.
    foreign_daily_path = base / DEFAULT_FOREIGN_FILE
    if len(sys.argv) > 2:
        foreign_daily_path = Path(sys.argv[2])
        if not foreign_daily_path.is_absolute():
            foreign_daily_path = base / foreign_daily_path

    if not path.exists():
        print(f"ERRO: arquivo não encontrado: {path}")
        print(f"Coloque o CSV na mesma pasta do script ou execute: py analise.py caminho\\arquivo.csv")
        sys.exit(1)

    try:
        rows = load_rows(path)
        volume = parse_volume(rows)
        daily_vol = parse_daily_volume(rows)
        daily_trades = parse_daily_trades(rows)
        participation = parse_participation(rows)
        foreign = parse_foreign_flow(rows)
        d = compute(volume, daily_vol, daily_trades, participation, foreign)

        # Fluxo estrangeiro diário do scraping.
        # Falha aqui NÃO derruba a análise principal.
        foreign_daily = None
        if foreign_daily_path.exists():
            try:
                foreign_daily = parse_foreign_daily_file(foreign_daily_path)
            except Exception as flow_exc:
                print(f"AVISO: não consegui analisar {foreign_daily_path.name}: {flow_exc}")
        else:
            print(
                f"AVISO: {foreign_daily_path.name} não encontrado. "
                "A análise original da B3 continuará normalmente."
            )

        print_report(path, d, foreign_daily)
    except Exception as exc:
        print(f"ERRO AO ANALISAR: {exc}")
        sys.exit(2)


if __name__ == "__main__":
    main()
