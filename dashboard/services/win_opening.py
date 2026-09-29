from __future__ import annotations

from typing import Any


def calculate_win_opening(winfut_points: float | None, sp500_futures_change_percent: float | None) -> dict[str, Any]:
    """Calculate the dashboard's simple WIN opening reference.

    Formula requested for the top dashboard card:
        WIN opening = current WINFUT × (1 + S&P 500 Futures variation / 100)

    Therefore a positive S&P 500 Futures variation is added and a negative
    variation is subtracted. The result is a directional reference, not a
    statistically calibrated forecast.
    """
    if winfut_points is None or sp500_futures_change_percent is None:
        return {
            "available": False,
            "value": None,
            "winfut_points": winfut_points,
            "sp500_futures_change_percent": sp500_futures_change_percent,
            "formula": "WINFUT × (1 + S&P 500 Fut % / 100)",
        }

    win = float(winfut_points)
    sp_change = float(sp500_futures_change_percent)
    value = win * (1.0 + sp_change / 100.0)

    return {
        "available": True,
        "value": round(value, 3),
        "winfut_points": round(win, 3),
        "sp500_futures_change_percent": round(sp_change, 4),
        "direction": "alta" if sp_change > 0 else "baixa" if sp_change < 0 else "neutra",
        "formula": "WINFUT × (1 + S&P 500 Fut % / 100)",
        "interpretation": (
            f"WINFUT {win:.3f} {'+' if sp_change >= 0 else ''}{sp_change:.4f}% do S&P 500 Futuro"
        ),
    }
