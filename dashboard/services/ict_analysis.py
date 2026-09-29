from __future__ import annotations

import io
import math
from collections import defaultdict
from datetime import datetime

import pandas as pd


REQUIRED_COLUMNS = {
    "Ativo": "symbol",
    "Data": "date",
    "Hora": "time",
    "Abertura": "open",
    "Máximo": "high",
    "Mínimo": "low",
    "Fechamento": "close",
}


def _read_csv(uploaded) -> pd.DataFrame:
    raw = uploaded.read()
    if hasattr(uploaded, "seek"):
        uploaded.seek(0)
    last_error = None
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            return pd.read_csv(
                io.BytesIO(raw),
                sep=None,
                engine="python",
                encoding=encoding,
            )
        except Exception as exc:
            last_error = exc
    raise ValueError(f"Não foi possível ler o CSV do Profit: {last_error}")


def _num(value):
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def _price_display(v: float, scale: float) -> float:
    return round(float(v) * scale, 3)


def _round_price(v: float, tick: float) -> float:
    return round(round(v / tick) * tick, 8)


def _fmt(v: float, scale: float) -> str:
    return f"{_price_display(v, scale):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _cluster_levels(levels, tolerance):
    """Cluster swing levels into potential equal-high/equal-low liquidity pools."""
    clusters = []
    for item in sorted(levels, key=lambda x: x["price"]):
        if not clusters or abs(item["price"] - clusters[-1]["price"]) > tolerance:
            clusters.append({
                "price": item["price"],
                "touches": 1,
                "indices": [item["index"]],
                "kind": item["kind"],
            })
        else:
            c = clusters[-1]
            c["price"] = (c["price"] * c["touches"] + item["price"]) / (c["touches"] + 1)
            c["touches"] += 1
            c["indices"].append(item["index"])
    return clusters


def _find_swings(df, left=2, right=2):
    highs, lows = [], []
    h = df["high"].tolist()
    l = df["low"].tolist()
    for i in range(left, len(df) - right):
        high = h[i]
        low = l[i]
        if high >= max(h[i-left:i+right+1]) and high > max(h[i-left:i] + h[i+1:i+right+1]):
            highs.append({"index": i, "price": high, "kind": "swing_high"})
        if low <= min(l[i-left:i+right+1]) and low < min(l[i-left:i] + l[i+1:i+right+1]):
            lows.append({"index": i, "price": low, "kind": "swing_low"})
    return highs, lows


def analyze_ict(uploaded, selected_date: str | None = None) -> dict:
    raw = _read_csv(uploaded)
    raw.columns = [str(c).strip() for c in raw.columns]

    # Accept common Profit aliases as well.
    aliases = {
        "Open": "Abertura", "High": "Máximo", "Low": "Mínimo",
        "Close": "Fechamento", "Date": "Data", "Time": "Hora",
    }
    for src, target in aliases.items():
        if target not in raw.columns and src in raw.columns:
            raw[target] = raw[src]

    missing = [c for c in REQUIRED_COLUMNS if c not in raw.columns]
    if missing:
        raise ValueError("Colunas obrigatórias ausentes: " + ", ".join(missing))

    df = raw.rename(columns=REQUIRED_COLUMNS).copy()
    df["datetime"] = pd.to_datetime(
        df["date"].astype(str).str.strip() + " " + df["time"].astype(str).str.strip(),
        dayfirst=True,
        errors="coerce",
    )
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].map(_num)
    df = df.dropna(subset=["datetime", "open", "high", "low", "close"]).copy()
    df = df.sort_values("datetime").drop_duplicates("datetime", keep="last").reset_index(drop=True)

    if df.empty:
        raise ValueError("O arquivo não contém candles válidos.")

    available_dates = sorted({x.strftime("%Y-%m-%d") for x in df["datetime"]})
    if selected_date and selected_date in available_dates:
        day_key = selected_date
    else:
        day_key = available_dates[-1]

    day = df[df["datetime"].dt.strftime("%Y-%m-%d") == day_key].copy()
    if len(day) < 10:
        raise ValueError(f"O dia {day_key} possui apenas {len(day)} candles; são necessários pelo menos 10.")

    # Normalize index for analysis.
    day = day.reset_index(drop=True)

    # WIN is commonly exported around 184.000 as 184.000; this project has
    # historically used 184,000-style display. If raw prices are 184.69,
    # multiply display only; calculations remain in source units.
    median_close = float(day["close"].median())
    display_scale = 1000.0 if median_close < 1000 else 1.0
    tick = 0.005 if display_scale == 1000 else 5.0
    tolerance = tick * 2

    highs, lows = _find_swings(day, left=2, right=2)

    # FVGs: three-candle imbalance.
    fvgs = []
    for i in range(2, len(day)):
        a, c = day.iloc[i-2], day.iloc[i]
        if c["low"] > a["high"] + 1e-12:
            top, bottom = c["low"], a["high"]
            fvgs.append({
                "id": f"FVG-B-{i}",
                "type": "bullish",
                "index": i,
                "time": day.iloc[i]["datetime"].isoformat(),
                "bottom": bottom,
                "top": top,
                "mitigated": bool(day.iloc[i+1:]["low"].min() <= bottom) if i + 1 < len(day) else False,
            })
        elif c["high"] < a["low"] - 1e-12:
            bottom, top = c["high"], a["low"]
            fvgs.append({
                "id": f"FVG-S-{i}",
                "type": "bearish",
                "index": i,
                "time": day.iloc[i]["datetime"].isoformat(),
                "bottom": bottom,
                "top": top,
                "mitigated": bool(day.iloc[i+1:]["high"].max() >= top) if i + 1 < len(day) else False,
            })

    # Liquidity from swing points + equal high/low clusters.
    high_clusters = _cluster_levels(highs, tolerance)
    low_clusters = _cluster_levels(lows, tolerance)
    liquidity = []

    day_high = float(day["high"].max())
    day_low = float(day["low"].min())
    day_high_i = int(day["high"].idxmax())
    day_low_i = int(day["low"].idxmin())
    liquidity += [
        {"type": "BSL", "kind": "day_high", "price": day_high, "index": day_high_i, "strength": 4, "label": "Máxima do dia"},
        {"type": "SSL", "kind": "day_low", "price": day_low, "index": day_low_i, "strength": 4, "label": "Mínima do dia"},
    ]

    for c in high_clusters:
        if c["touches"] >= 2:
            liquidity.append({
                "type": "BSL", "kind": "equal_highs", "price": c["price"],
                "index": max(c["indices"]), "strength": min(5, 2 + c["touches"]),
                "label": f"Equal Highs ({c['touches']} toques)",
            })
    for c in low_clusters:
        if c["touches"] >= 2:
            liquidity.append({
                "type": "SSL", "kind": "equal_lows", "price": c["price"],
                "index": max(c["indices"]), "strength": min(5, 2 + c["touches"]),
                "label": f"Equal Lows ({c['touches']} toques)",
            })

    # Previous trading day high/low when the CSV contains more than one day.
    prior = df[df["datetime"].dt.strftime("%Y-%m-%d") < day_key]
    if not prior.empty:
        prior_dates = sorted({x.strftime("%Y-%m-%d") for x in prior["datetime"]})
        pday = prior[prior["datetime"].dt.strftime("%Y-%m-%d") == prior_dates[-1]]
        if not pday.empty:
            liquidity.extend([
                {"type": "BSL", "kind": "pdh", "price": float(pday["high"].max()), "index": 0, "strength": 5, "label": "PDH"},
                {"type": "SSL", "kind": "pdl", "price": float(pday["low"].min()), "index": 0, "strength": 5, "label": "PDL"},
            ])

    # Sweeps and structure shifts.
    events = []
    sweeps = []
    for i in range(3, len(day)):
        close = float(day.iloc[i]["close"])
        high = float(day.iloc[i]["high"])
        low = float(day.iloc[i]["low"])
        prior_highs = [x for x in highs if x["index"] < i]
        prior_lows = [x for x in lows if x["index"] < i]
        if prior_highs:
            sh = prior_highs[-1]
            if high > sh["price"] + tolerance and close < sh["price"]:
                sweeps.append({
                    "index": i, "type": "buy_side_sweep", "price": high,
                    "level": sh["price"], "time": day.iloc[i]["datetime"].isoformat(),
                })
                events.append({
                    "index": i, "event": "BSL SWEEP", "direction": "bearish",
                    "price": high, "time": day.iloc[i]["datetime"].isoformat(),
                })
        if prior_lows:
            sl = prior_lows[-1]
            if low < sl["price"] - tolerance and close > sl["price"]:
                sweeps.append({
                    "index": i, "type": "sell_side_sweep", "price": low,
                    "level": sl["price"], "time": day.iloc[i]["datetime"].isoformat(),
                })
                events.append({
                    "index": i, "event": "SSL SWEEP", "direction": "bullish",
                    "price": low, "time": day.iloc[i]["datetime"].isoformat(),
                })

    # MSS: displacement closing beyond a recent opposing swing after a sweep.
    mss = []
    for i in range(3, len(day)):
        close = float(day.iloc[i]["close"])
        recent_sweeps = [s for s in sweeps if 0 < i - s["index"] <= 12]
        if not recent_sweeps:
            continue
        prior_highs = [x for x in highs if x["index"] < i]
        prior_lows = [x for x in lows if x["index"] < i]
        if recent_sweeps[-1]["type"] == "buy_side_sweep" and prior_lows:
            sl = prior_lows[-1]
            if close < sl["price"] - tolerance:
                mss.append({"index": i, "type": "bearish", "price": close, "time": day.iloc[i]["datetime"].isoformat()})
                events.append({"index": i, "event": "MSS", "direction": "bearish", "price": close, "time": day.iloc[i]["datetime"].isoformat()})
        elif recent_sweeps[-1]["type"] == "sell_side_sweep" and prior_highs:
            sh = prior_highs[-1]
            if close > sh["price"] + tolerance:
                mss.append({"index": i, "type": "bullish", "price": close, "time": day.iloc[i]["datetime"].isoformat()})
                events.append({"index": i, "event": "MSS", "direction": "bullish", "price": close, "time": day.iloc[i]["datetime"].isoformat()})

    # Order blocks: last opposite candle before a displacement/MSS.
    obs = []
    for m in mss:
        i = m["index"]
        start = max(0, i - 5)
        candidate = None
        for j in range(i - 1, start - 1, -1):
            row = day.iloc[j]
            if m["type"] == "bullish" and row["close"] < row["open"]:
                candidate = j
                break
            if m["type"] == "bearish" and row["close"] > row["open"]:
                candidate = j
                break
        if candidate is not None:
            r = day.iloc[candidate]
            obs.append({
                "id": f"OB-{m['type'][0].upper()}-{candidate}",
                "type": m["type"],
                "index": candidate,
                "time": r["datetime"].isoformat(),
                "bottom": float(r["low"]),
                "top": float(r["high"]),
                "mitigated": bool(
                    day.iloc[candidate+1:]["low"].min() <= r["low"]
                    if m["type"] == "bullish" and candidate + 1 < len(day)
                    else day.iloc[candidate+1:]["high"].max() >= r["high"]
                    if candidate + 1 < len(day)
                    else False
                ),
                "source_mss_index": i,
            })

    # De-duplicate overlapping OBs.
    unique_obs = {}
    for ob in obs:
        unique_obs[(ob["type"], round(ob["bottom"], 8), round(ob["top"], 8))] = ob
    obs = list(unique_obs.values())

    current = float(day.iloc[-1]["close"])
    last_mss = mss[-1] if mss else None

    def zone_distance(z):
        if z["bottom"] <= current <= z["top"]:
            return 0.0
        return min(abs(current - z["bottom"]), abs(current - z["top"]))

    pois = []
    for z in fvgs + obs:
        z2 = dict(z)
        z2["distance"] = zone_distance(z)
        z2["active"] = not z.get("mitigated", False)
        pois.append(z2)
    pois.sort(key=lambda z: (not z["active"], z["distance"]))

    # Candidate setup is conditional: active POI + compatible last MSS + price
    # at/near the zone. We never label mere proximity as an entry.
    candidates = []
    for z in pois:
        if not z["active"]:
            continue
        compatible = (
            last_mss is not None and
            ((z["type"] == "bearish" and last_mss["type"] == "bearish") or
             (z["type"] == "bullish" and last_mss["type"] == "bullish"))
        )
        near = z["distance"] <= tolerance * 4
        if compatible:
            candidates.append({
                "direction": "VENDA" if z["type"] == "bearish" else "COMPRA",
                "status": "POI ATIVADO — aguardar confirmação" if near else "AGUARDANDO RETORNO AO POI",
                "reason": f"{'FVG' if z['id'].startswith('FVG') else 'OB'} alinhado ao último MSS",
                "zone_bottom": z["bottom"],
                "zone_top": z["top"],
                "distance": z["distance"],
                "type": z["type"],
            })

    # Premium / discount using day's range as a transparent default dealing range.
    eq = (day_high + day_low) / 2
    location = "PREMIUM" if current > eq else "DISCOUNT" if current < eq else "EQUILIBRIUM"

    # Displacement: body/range compared with recent average.
    ranges = (day["high"] - day["low"]).astype(float)
    bodies = (day["close"] - day["open"]).abs().astype(float)
    avg_range = float(ranges.tail(20).mean())
    displacement_count = int(((ranges > avg_range * 1.5) & (bodies > ranges * 0.55)).sum()) if avg_range else 0

    # Chart payload. Plotly uses source units; frontend applies display_scale.
    candles = []
    for _, r in day.iterrows():
        candles.append({
            "time": r["datetime"].isoformat(),
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
        })

    def zone_payload(items):
        return [{
            **{k: _price_display(v, display_scale) if k in ("bottom", "top", "price", "level", "distance") and isinstance(v, (int, float)) else v for k, v in item.items()},
            "index": item.get("index"),
        } for item in items]

    return {
        "ok": True,
        "asset": str(day["symbol"].iloc[0] or "WINFUT"),
        "date": day_key,
        "available_dates": available_dates,
        "candle_count": len(day),
        "display_scale": display_scale,
        "tick_display": _price_display(tick, display_scale),
        "current": _price_display(current, display_scale),
        "day_high": _price_display(day_high, display_scale),
        "day_low": _price_display(day_low, display_scale),
        "equilibrium": _price_display(eq, display_scale),
        "location": location,
        "prior_day": (
            {"high": _price_display(float(pday["high"].max()), display_scale),
             "low": _price_display(float(pday["low"].min()), display_scale)}
            if not prior.empty else None
        ),
        "swings": {
            "highs": [{"index": x["index"], "price": _price_display(x["price"], display_scale),
                       "time": day.iloc[x["index"]]["datetime"].isoformat()} for x in highs],
            "lows": [{"index": x["index"], "price": _price_display(x["price"], display_scale),
                      "time": day.iloc[x["index"]]["datetime"].isoformat()} for x in lows],
        },
        "fvg": zone_payload(fvgs),
        "order_blocks": zone_payload(obs),
        "liquidity": zone_payload(liquidity),
        "sweeps": zone_payload(sweeps),
        "mss": zone_payload(mss),
        "events": events[-30:],
        "pois": zone_payload(pois[:20]),
        "candidates": candidates[:8],
        "stats": {
            "fvg_open": sum(1 for x in fvgs if not x["mitigated"]),
            "fvg_total": len(fvgs),
            "ob_open": sum(1 for x in obs if not x["mitigated"]),
            "ob_total": len(obs),
            "liquidity_pools": sum(1 for x in liquidity if x["kind"] in ("equal_highs", "equal_lows")),
            "sweeps": len(sweeps),
            "mss": len(mss),
            "displacement": displacement_count,
        },
        "methodology": {
            "timeframe": "5 minutos",
            "swing": "2 candles à esquerda + 2 à direita",
            "fvg": "3 candles; gap entre candle 1 e candle 3",
            "liquidity": "swing highs/lows, equal highs/lows, máxima/mínima do dia e PDH/PDL quando disponível",
            "sweep": "varredura de swing com fechamento de volta para dentro",
            "mss": "fechamento além do swing oposto após sweep recente",
            "order_block": "último candle contrário antes do deslocamento/MSS",
            "premium_discount": "50% da máxima/mínima do dia como referência transparente",
        },
        "candles": candles,
    }
