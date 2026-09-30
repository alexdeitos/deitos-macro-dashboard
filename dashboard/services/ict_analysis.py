from __future__ import annotations

import io
from pathlib import Path
from typing import Iterable

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
PRICE_COLUMNS = ("open", "high", "low", "close")


def _read_csv(uploaded) -> pd.DataFrame:
    raw = uploaded.read()
    if hasattr(uploaded, "seek"):
        uploaded.seek(0)
    last_error = None
    for encoding in ("utf-8-sig", "cp1252", "latin1"):
        try:
            return pd.read_csv(io.BytesIO(raw), sep=None, engine="python", encoding=encoding)
        except Exception as exc:
            last_error = exc
    raise ValueError(f"Não foi possível ler o CSV do Profit: {last_error}")


def _parse_number(value):
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("\xa0", "")
    if not s:
        return None
    try:
        if "," in s and "." in s:
            # The last separator is treated as the decimal separator.
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            s = s.replace(".", "").replace(",", ".")
        return float(s)
    except (TypeError, ValueError):
        return None


def _normalize_price_scale(df: pd.DataFrame) -> float:
    """Normalize WIN exports to operational points (e.g. 184.690 -> 184690)."""
    median = float(df["close"].median())
    if median < 1000:
        for column in PRICE_COLUMNS:
            df[column] = df[column] * 1000.0
        return 1000.0
    return 1.0


def _price_display(v: float, scale: float = 1.0) -> float:
    return round(float(v) / scale, 6)


def _to_display(v: float) -> float:
    return round(float(v), 3)


def _fmt(v: float) -> str:
    return f"{_to_display(v):,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _dedupe(items: Iterable[dict], keys: tuple[str, ...]) -> list[dict]:
    out = []
    seen = set()
    for item in items:
        key = tuple(item.get(k) for k in keys)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _find_swings(df: pd.DataFrame, left: int = 2, right: int = 2) -> tuple[list[dict], list[dict]]:
    highs, lows = [], []
    h = df["high"].tolist()
    l = df["low"].tolist()
    for i in range(left, len(df) - right):
        window_h = h[i - left : i + right + 1]
        window_l = l[i - left : i + right + 1]
        is_high = h[i] == max(window_h) and h[i] > max(h[i - left : i], default=float("-inf")) and h[i] >= max(
            h[i + 1 : i + right + 1], default=float("-inf")
        )
        is_low = l[i] == min(window_l) and l[i] < min(l[i - left : i], default=float("inf")) and l[i] <= min(
            l[i + 1 : i + right + 1], default=float("inf")
        )
        if is_high:
            highs.append({"index": i, "price": float(h[i]), "kind": "swing_high"})
        if is_low:
            lows.append({"index": i, "price": float(l[i]), "kind": "swing_low"})
    return highs, lows


def _cluster_swings(swings: list[dict], tolerance: float, minimum_touches: int = 2) -> list[dict]:
    """Group swing prices into equal-high/equal-low style liquidity pools."""
    clusters: list[dict] = []
    for swing in sorted(swings, key=lambda x: (x["price"], x["index"])):
        if not clusters or abs(swing["price"] - clusters[-1]["price"]) > tolerance:
            clusters.append({
                "price": swing["price"],
                "touches": 1,
                "indices": [swing["index"]],
            })
        else:
            c = clusters[-1]
            c["indices"].append(swing["index"])
            c["touches"] += 1
            c["price"] = (c["price"] * (c["touches"] - 1) + swing["price"]) / c["touches"]
    return [c for c in clusters if c["touches"] >= minimum_touches]


def _zone_state(day: pd.DataFrame, index: int, bottom: float, top: float, direction: str, invalidation_by_close: bool = False) -> tuple[str, int | None]:
    """OPEN -> first touch -> PARTIAL/FILLED or INVALIDATED, with first-touch index."""
    touched_index = None
    state = "OPEN"
    if index + 1 >= len(day):
        return state, touched_index
    for j in range(index + 1, len(day)):
        row = day.iloc[j]
        intersects = float(row["low"]) <= top and float(row["high"]) >= bottom
        if intersects and touched_index is None:
            touched_index = j
            state = "PARTIAL"
        if direction == "bullish":
            if invalidation_by_close and float(row["close"]) < bottom:
                return "INVALIDATED", touched_index
            if float(row["low"]) <= bottom:
                return "FILLED", touched_index
        else:
            if invalidation_by_close and float(row["close"]) > top:
                return "INVALIDATED", touched_index
            if float(row["high"]) >= top:
                return "FILLED", touched_index
    return state, touched_index


def _in_zone(price: float, z: dict) -> bool:
    return float(z["bottom"]) <= price <= float(z["top"])


def _distance_to_zone(price: float, z: dict) -> float:
    if _in_zone(price, z):
        return 0.0
    return min(abs(price - float(z["bottom"])), abs(price - float(z["top"])))


def _nearest_liquidity(liquidity: list[dict], current: float, direction: str) -> dict | None:
    candidates = []
    for item in liquidity:
        price = float(item["price"])
        if direction == "bullish" and price > current:
            candidates.append(item)
        elif direction == "bearish" and price < current:
            candidates.append(item)
    if not candidates:
        return None
    return min(candidates, key=lambda x: abs(float(x["price"]) - current))


def _format_event(row, name: str, direction: str, price: float, index: int, reference: float | None = None) -> dict:
    return {
        "index": int(index),
        "event": name,
        "direction": direction,
        "price": float(price),
        "time": row["datetime"].isoformat(),
        "reference": float(reference) if reference is not None else None,
    }


def analyze_ict(uploaded, selected_date: str | None = None) -> dict:
    raw = _read_csv(uploaded)
    raw.columns = [str(c).strip() for c in raw.columns]

    aliases = {
        "Open": "Abertura",
        "High": "Máximo",
        "Low": "Mínimo",
        "Close": "Fechamento",
        "Date": "Data",
        "Time": "Hora",
        "Symbol": "Ativo",
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
    for column in PRICE_COLUMNS:
        df[column] = df[column].map(_parse_number)
    if "volume" in raw.columns:
        df["volume"] = raw["volume"].map(_parse_number)
    df = df.dropna(subset=["datetime", *PRICE_COLUMNS]).copy()
    df = df.sort_values("datetime").drop_duplicates("datetime", keep="last").reset_index(drop=True)
    if df.empty:
        raise ValueError("O arquivo não contém candles válidos.")

    normalize_factor = _normalize_price_scale(df)
    # Calculations below are always in operational WIN points.
    tick = 5.0
    tolerance = tick * 2.0

    available_dates = sorted({x.strftime("%Y-%m-%d") for x in df["datetime"]})
    day_key = selected_date if selected_date in available_dates else available_dates[-1]
    day = df[df["datetime"].dt.strftime("%Y-%m-%d") == day_key].copy().reset_index(drop=True)
    if len(day) < 10:
        raise ValueError(f"O dia {day_key} possui apenas {len(day)} candles; são necessários pelo menos 10.")

    # ──────────────────────────────────────────────────────────────────────
    # Core ICT-style structure: confirmed swings, displacement, sweeps, MSS/BOS
    # ──────────────────────────────────────────────────────────────────────
    swing_highs, swing_lows = _find_swings(day, left=2, right=2)
    all_swings = [("high", x) for x in swing_highs] + [("low", x) for x in swing_lows]
    all_swings.sort(key=lambda x: x[1]["index"])

    ranges = (day["high"] - day["low"]).astype(float)
    bodies = (day["close"] - day["open"]).abs().astype(float)
    body_ratio = bodies.div(ranges.replace(0, pd.NA)).fillna(0.0)
    avg_range_series = ranges.rolling(20, min_periods=5).mean()
    displacement = []
    for i in range(len(day)):
        avg_range = float(avg_range_series.iloc[i]) if pd.notna(avg_range_series.iloc[i]) else float(ranges.iloc[: max(1, i)].mean())
        r = float(ranges.iloc[i])
        br = float(body_ratio.iloc[i])
        if avg_range > 0 and r >= avg_range * 1.35 and br >= 0.55:
            displacement.append({
                "index": i,
                "direction": "bullish" if day.iloc[i]["close"] > day.iloc[i]["open"] else "bearish",
                "range": r,
                "body": float(bodies.iloc[i]),
                "time": day.iloc[i]["datetime"].isoformat(),
            })

    # Liquidity pools from equal highs/lows + day extremes + PDH/PDL.
    liquidity: list[dict] = []
    day_high = float(day["high"].max())
    day_low = float(day["low"].min())
    day_high_i = int(day["high"].idxmax())
    day_low_i = int(day["low"].idxmin())
    liquidity.extend([
        {"type": "BSL", "kind": "day_high", "price": day_high, "index": day_high_i, "strength": 4, "label": "Máxima do dia", "status": "FUTURA"},
        {"type": "SSL", "kind": "day_low", "price": day_low, "index": day_low_i, "strength": 4, "label": "Mínima do dia", "status": "FUTURA"},
    ])

    prior_day = None
    prior = df[df["datetime"].dt.strftime("%Y-%m-%d") < day_key]
    if not prior.empty:
        prior_date = sorted({x.strftime("%Y-%m-%d") for x in prior["datetime"]})[-1]
        pday = prior[prior["datetime"].dt.strftime("%Y-%m-%d") == prior_date]
        if not pday.empty:
            prior_day = {
                "date": prior_date,
                "high": float(pday["high"].max()),
                "low": float(pday["low"].min()),
            }
            liquidity.extend([
                {"type": "BSL", "kind": "pdh", "price": prior_day["high"], "index": 0, "strength": 5, "label": "PDH", "status": "EXTERNAL"},
                {"type": "SSL", "kind": "pdl", "price": prior_day["low"], "index": 0, "strength": 5, "label": "PDL", "status": "EXTERNAL"},
            ])

    eq_highs = _cluster_swings(swing_highs, tolerance=tolerance, minimum_touches=2)
    eq_lows = _cluster_swings(swing_lows, tolerance=tolerance, minimum_touches=2)
    for cluster in eq_highs:
        liquidity.append({
            "type": "BSL",
            "kind": "equal_highs",
            "price": float(cluster["price"]),
            "index": max(cluster["indices"]),
            "strength": min(5, 2 + cluster["touches"]),
            "label": f"Equal Highs ({cluster['touches']} toques)",
            "status": "INTERNAL",
        })
    for cluster in eq_lows:
        liquidity.append({
            "type": "SSL",
            "kind": "equal_lows",
            "price": float(cluster["price"]),
            "index": max(cluster["indices"]),
            "strength": min(5, 2 + cluster["touches"]),
            "label": f"Equal Lows ({cluster['touches']} toques)",
            "status": "INTERNAL",
        })

    # Keep the pools distinct by level/type and sort by strength.
    liquidity = _dedupe(
        sorted(liquidity, key=lambda x: (-x["strength"], abs(x["price"] - float(day.iloc[-1]["close"])))),
        ("type", "kind", "price"),
    )

    sweeps: list[dict] = []
    swept_keys = set()
    # Build a compact pool list that can actually be swept during the session.
    sweepable = [q for q in liquidity if q["kind"] not in {"day_high", "day_low"}]
    for i in range(len(day)):
        row = day.iloc[i]
        high = float(row["high"])
        low = float(row["low"])
        close = float(row["close"])
        for pool in sweepable:
            if i <= int(pool["index"]):
                continue
            key = (pool["type"], round(pool["price"], 4), int(pool["index"]))
            if key in swept_keys:
                continue
            level = float(pool["price"])
            if pool["type"] == "BSL" and high > level + tolerance and close < level:
                sweeps.append({
                    "index": i,
                    "type": "buy_side_sweep",
                    "price": high,
                    "level": level,
                    "time": row["datetime"].isoformat(),
                    "liquidity_label": pool["label"],
                    "direction": "bearish",
                })
                swept_keys.add(key)
            elif pool["type"] == "SSL" and low < level - tolerance and close > level:
                sweeps.append({
                    "index": i,
                    "type": "sell_side_sweep",
                    "price": low,
                    "level": level,
                    "time": row["datetime"].isoformat(),
                    "liquidity_label": pool["label"],
                    "direction": "bullish",
                })
                swept_keys.add(key)

    # Structure state. MSS occurs when the post-sweep break is opposite the prior bias.
    events: list[dict] = []
    structure_events: list[dict] = []
    mss: list[dict] = []
    bos: list[dict] = []
    bias = "neutral"
    last_sweep = None

    for i in range(len(day)):
        recent_sweeps = [s for s in sweeps if s["index"] < i and i - s["index"] <= 12]
        if recent_sweeps:
            last_sweep = recent_sweeps[-1]

        prior_highs = [x for x in swing_highs if x["index"] < i]
        prior_lows = [x for x in swing_lows if x["index"] < i]
        close = float(day.iloc[i]["close"])
        is_displacement = any(d["index"] == i for d in displacement)

        if last_sweep and last_sweep["type"] == "sell_side_sweep" and prior_highs:
            ref = prior_highs[-1]
            if close > float(ref["price"]) + tolerance:
                event_type = "MSS" if bias in {"neutral", "bearish"} else "BOS"
                event = _format_event(day.iloc[i], event_type, "bullish", close, i, ref["price"])
                structure_events.append(event)
                (mss if event_type == "MSS" else bos).append({
                    "index": i, "type": "bullish", "price": close, "time": day.iloc[i]["datetime"].isoformat(),
                    "reference": ref["price"], "displacement": is_displacement,
                })
                events.append(event)
                bias = "bullish"
                last_sweep = None
        elif last_sweep and last_sweep["type"] == "buy_side_sweep" and prior_lows:
            ref = prior_lows[-1]
            if close < float(ref["price"]) - tolerance:
                event_type = "MSS" if bias in {"neutral", "bullish"} else "BOS"
                event = _format_event(day.iloc[i], event_type, "bearish", close, i, ref["price"])
                structure_events.append(event)
                (mss if event_type == "MSS" else bos).append({
                    "index": i, "type": "bearish", "price": close, "time": day.iloc[i]["datetime"].isoformat(),
                    "reference": ref["price"], "displacement": is_displacement,
                })
                events.append(event)
                bias = "bearish"
                last_sweep = None

    # ──────────────────────────────────────────────────────────────────────
    # FVG: keep only meaningful imbalances as first-class POIs.
    # ──────────────────────────────────────────────────────────────────────
    fvg_all = []
    avg_range_global = max(float(ranges.tail(20).mean()), tick)
    for i in range(2, len(day)):
        a, c = day.iloc[i - 2], day.iloc[i]
        direction = None
        bottom = top = None
        if float(c["low"]) > float(a["high"]) + tick / 2:
            direction = "bullish"
            bottom, top = float(a["high"]), float(c["low"])
        elif float(c["high"]) < float(a["low"]) - tick / 2:
            direction = "bearish"
            bottom, top = float(c["high"]), float(a["low"])
        if not direction:
            continue

        state, first_touch = _zone_state(day, i, bottom, top, direction, invalidation_by_close=False)
        gap_size = top - bottom
        disp = next((d for d in displacement if d["index"] == i and d["direction"] == direction), None)
        related_mss = [m for m in mss if 0 <= i - m["index"] <= 4 and m["type"] == direction]
        related_sweep = [s for s in sweeps if 0 <= i - s["index"] <= 6 and s["direction"] == direction]
        meaningful = bool(disp or related_mss or related_sweep or gap_size >= avg_range_global * 0.18)
        if not meaningful:
            continue
        fvg_all.append({
            "id": f"FVG-{ 'B' if direction == 'bullish' else 'S' }-{i}",
            "type": direction,
            "index": i,
            "time": day.iloc[i]["datetime"].isoformat(),
            "bottom": bottom,
            "top": top,
            "size": gap_size,
            "state": state,
            "first_touch_index": first_touch,
            "mitigated": state == "FILLED",
            "active": state in {"OPEN", "PARTIAL"},
            "displacement": bool(disp),
            "linked_mss": bool(related_mss),
            "linked_sweep": bool(related_sweep),
        })

    # ──────────────────────────────────────────────────────────────────────
    # Order Block: the last opposite candle immediately before a structural
    # displacement, not any arbitrary opposite candle five bars away.
    # ──────────────────────────────────────────────────────────────────────
    order_blocks = []
    structural_triggers = sorted(mss + [x for x in bos if x.get("displacement")], key=lambda x: x["index"])
    for trigger in structural_triggers:
        i = int(trigger["index"])
        direction = trigger["type"]
        candidate = None
        for j in range(i - 1, max(-1, i - 5), -1):
            r = day.iloc[j]
            bearish_candle = float(r["close"]) < float(r["open"])
            bullish_candle = float(r["close"]) > float(r["open"])
            if direction == "bullish" and bearish_candle:
                candidate = j
                break
            if direction == "bearish" and bullish_candle:
                candidate = j
                break
        if candidate is None:
            continue
        r = day.iloc[candidate]
        bottom, top = float(r["low"]), float(r["high"])
        state, first_touch = _zone_state(day, candidate, bottom, top, direction, invalidation_by_close=True)
        # Do not duplicate an unchanged zone created by consecutive BOS/MSS events.
        order_blocks.append({
            "id": f"OB-{ 'B' if direction == 'bullish' else 'S' }-{candidate}",
            "type": direction,
            "index": candidate,
            "time": r["datetime"].isoformat(),
            "bottom": bottom,
            "top": top,
            "state": state,
            "first_touch_index": first_touch,
            "mitigated": state in {"PARTIAL", "FILLED"},
            "invalidated": state == "INVALIDATED",
            "active": state == "OPEN",
            "source_event_index": i,
            "source_event": "MSS" if any(m["index"] == i for m in mss) else "BOS",
        })
    order_blocks = _dedupe(reversed(order_blocks), ("type", "bottom", "top"))
    order_blocks = list(reversed(order_blocks))

    current = float(day.iloc[-1]["close"])
    eq = (day_high + day_low) / 2.0
    location = "PREMIUM" if current > eq + tolerance else "DISCOUNT" if current < eq - tolerance else "EQUILIBRIUM"

    # External liquidity used only as context/targets. Day high/low are future pools.
    active_liquidity = []
    for pool in liquidity:
        p = float(pool["price"])
        pool = dict(pool)
        pool["distance"] = abs(current - p)
        pool["relative"] = "ACIMA" if p > current else "ABAIXO" if p < current else "NO PREÇO"
        active_liquidity.append(pool)
    active_liquidity.sort(key=lambda x: (-x["strength"], x["distance"]))

    last_mss = mss[-1] if mss else None
    last_event = structure_events[-1] if structure_events else None
    structure_bias = last_mss["type"] if last_mss else bias

    # Candidate POIs: prioritize zones that are fresh/unmitigated and tied to a recent
    # liquidity event + structural shift. Old standalone FVGs are deliberately de-emphasized.
    zones = []
    for source in (fvg_all, order_blocks):
        for z in source:
            if z.get("state") == "INVALIDATED" or z.get("state") == "FILLED":
                continue
            age = len(day) - 1 - int(z["index"])
            distance = _distance_to_zone(current, z)
            pd_aligned = (z["type"] == "bullish" and location == "DISCOUNT") or (z["type"] == "bearish" and location == "PREMIUM")
            related_mss = z.get("linked_mss", False) or z.get("source_event") == "MSS"
            related_sweep = z.get("linked_sweep", False)
            related_displacement = z.get("displacement", False) or z.get("source_event") in {"MSS", "BOS"}
            freshness = max(0.0, 1.0 - age / max(1.0, len(day)))
            confluences = []
            if related_sweep:
                confluences.append("Sweep")
            if related_mss:
                confluences.append("MSS")
            if related_displacement:
                confluences.append("Displacement")
            if pd_aligned:
                confluences.append("Premium/Discount")
            if z.get("state") == "OPEN":
                confluences.append("Fresh")
            priority_score = (
                (3 if related_sweep else 0)
                + (3 if related_mss else 0)
                + (2 if related_displacement else 0)
                + (2 if pd_aligned else 0)
                + (2 if z.get("state") == "OPEN" else 1)
                + freshness
                - min(distance / 2500.0, 1.0)
            )
            z2 = dict(z)
            z2.update({
                "age": age,
                "distance": distance,
                "pd_aligned": pd_aligned,
                "confluences": confluences,
                "priority": round(priority_score, 2),
                "in_zone": _in_zone(current, z),
                "plot": bool(z.get("active")) and priority_score >= 4.0,
            })
            zones.append(z2)

    zones.sort(key=lambda z: (-z["priority"], z["distance"], z["index"]))
    priority_pois = zones[:12]

    candidates = []
    for z in priority_pois:
        direction = z["type"]
        directional_structure = structure_bias == direction
        near = z["distance"] <= max(10 * tick, 50.0)
        if not directional_structure or len(z["confluences"]) < 2:
            continue
        target = _nearest_liquidity(active_liquidity, current, direction)
        invalidation = (float(z["bottom"]) - tick * 2) if direction == "bullish" else (float(z["top"]) + tick * 2)
        status = "POI ATIVADO — aguardar confirmação" if z["in_zone"] or near else "AGUARDANDO RETORNO AO POI"
        trigger = (
            "Retorno à zona + reação + novo deslocamento/MSS no microcontexto"
            if z["in_zone"] or near
            else "Aguardar retorno à zona; não antecipar entrada"
        )
        candidates.append({
            "direction": "COMPRA" if direction == "bullish" else "VENDA",
            "status": status,
            "reason": "+ ".join(z["confluences"]),
            "zone_bottom": z["bottom"],
            "zone_top": z["top"],
            "distance": z["distance"],
            "type": direction,
            "zone_id": z["id"],
            "target": target["price"] if target else None,
            "target_label": target["label"] if target else None,
            "invalidation": invalidation,
            "trigger": trigger,
            "fresh": z.get("state") == "OPEN",
            "confluence_count": len(z["confluences"]),
        })
        if len(candidates) >= 8:
            break

    # Important map levels: only a small, ranked subset is plotted so the chart remains readable.
    ranked_liquidity = sorted(active_liquidity, key=lambda x: (-x["strength"], x["distance"]))
    plotted_liquidity = ranked_liquidity[:10]

    candles = [
        {
            "time": row["datetime"].isoformat(),
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]) if "volume" in row and pd.notna(row["volume"]) else None,
        }
        for _, row in day.iterrows()
    ]

    def public_zone(item: dict) -> dict:
        output = dict(item)
        for key in ("bottom", "top", "price", "level", "distance", "reference", "size", "invalidation", "target"):
            if key in output and isinstance(output[key], (int, float)):
                output[key] = _to_display(output[key])
        return output

    # Mark only fresh/high-quality liquidity pools for display, but expose all in table/API.
    for pool in liquidity:
        pool["plot"] = pool in plotted_liquidity or pool["kind"] in {"pdh", "pdl", "day_high", "day_low"}

    latest_sweep = sweeps[-1] if sweeps else None
    latest_mss = mss[-1] if mss else None
    latest_displacement = displacement[-1] if displacement else None

    structure_label = {
        "bullish": "BULLISH",
        "bearish": "BEARISH",
        "neutral": "NEUTRO",
    }[structure_bias]

    return {
        "ok": True,
        "asset": str(day["symbol"].iloc[0] or "WINFUT"),
        "date": day_key,
        "available_dates": available_dates,
        "candle_count": len(day),
        "source_normalize_factor": normalize_factor,
        "display_scale": 1.0,
        "tick_display": tick,
        "current": _to_display(current),
        "day_high": _to_display(day_high),
        "day_low": _to_display(day_low),
        "equilibrium": _to_display(eq),
        "location": location,
        "structure_bias": structure_bias,
        "structure_label": structure_label,
        "last_structure_event": public_zone(last_event) if last_event else None,
        "last_sweep": public_zone(latest_sweep) if latest_sweep else None,
        "last_mss": public_zone(latest_mss) if latest_mss else None,
        "last_displacement": public_zone(latest_displacement) if latest_displacement else None,
        "prior_day": (
            {
                "date": prior_day["date"],
                "high": _to_display(prior_day["high"]),
                "low": _to_display(prior_day["low"]),
            }
            if prior_day else None
        ),
        "swings": {
            "highs": [
                {"index": x["index"], "price": _to_display(x["price"]), "time": day.iloc[x["index"]]["datetime"].isoformat()}
                for x in swing_highs
            ],
            "lows": [
                {"index": x["index"], "price": _to_display(x["price"]), "time": day.iloc[x["index"]]["datetime"].isoformat()}
                for x in swing_lows
            ],
        },
        "fvg": [public_zone(z) for z in fvg_all],
        "order_blocks": [public_zone(z) for z in order_blocks],
        "liquidity": [public_zone(z) for z in liquidity],
        "plotted_liquidity": [public_zone(z) for z in plotted_liquidity],
        "sweeps": [public_zone(s) for s in sweeps],
        "mss": [public_zone(m) for m in mss],
        "bos": [public_zone(b) for b in bos],
        "displacement": [public_zone(d) for d in displacement],
        "events": [public_zone(e) for e in events[-40:]],
        "pois": [public_zone(z) for z in priority_pois],
        "candidates": [public_zone(c) for c in candidates],
        "stats": {
            "fvg_fresh": sum(1 for x in fvg_all if x["state"] == "OPEN"),
            "fvg_partial": sum(1 for x in fvg_all if x["state"] == "PARTIAL"),
            "fvg_total": len(fvg_all),
            "ob_fresh": sum(1 for x in order_blocks if x["state"] == "OPEN"),
            "ob_mitigated": sum(1 for x in order_blocks if x["mitigated"]),
            "ob_total": len(order_blocks),
            "liquidity_pools": sum(1 for x in liquidity if x["kind"] in {"equal_highs", "equal_lows"}),
            "external_liquidity": sum(1 for x in liquidity if x["kind"] in {"pdh", "pdl", "day_high", "day_low"}),
            "sweeps": len(sweeps),
            "mss": len(mss),
            "bos": len(bos),
            "displacement": len(displacement),
            "priority_pois": len(priority_pois),
            "conditional_setups": len(candidates),
        },
        "methodology": {
            "timeframe": "5 minutos — leitura principal",
            "estrutura": "Swing confirmado por 2 candles à esquerda + 2 à direita; MSS após sweep e quebra do swing oposto; BOS quando a quebra segue o viés estrutural vigente",
            "displacement": "Range >= 1,35x a média recente e corpo >= 55% do range",
            "fvg": "Imbalance de 3 candles; zonas pequenas/isoladas são filtradas; prioridade para FVG ligado a displacement, sweep ou MSS",
            "order_block": "Último candle contrário imediatamente anterior a MSS ou BOS com displacement; invalidado por fechamento além do limite da zona",
            "liquidez": "Equal Highs/Equal Lows, PDH/PDL quando o arquivo contém o dia anterior e extremos do dia; níveis são possíveis pools, não prova de ordens stop",
            "sweep": "Pavio atravessa o nível de liquidez e o fechamento retorna para dentro do nível",
            "premium_discount": "50% da máxima/mínima do dia como dealing range operacional da sessão selecionada",
            "poi_filter": "Prioriza zonas não preenchidas, recentes e relacionadas a Sweep/MSS/Displacement; zonas antigas permanecem na tabela mas não dominam o mapa",
            "setup": "POI + contexto estrutural compatível + confluências; retorno à zona não é entrada automática e exige confirmação de preço",
            "pdh_pdl": "Só calculados quando o CSV traz pelo menos um pregão anterior; nenhum valor é inventado",
        },
        "candles": candles,
    }


def analyze_ict_path(path: str | Path, selected_date: str | None = None) -> dict:
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Arquivo ICT não encontrado: {path}")
    with path.open("rb") as handle:
        return analyze_ict(handle, selected_date=selected_date)
