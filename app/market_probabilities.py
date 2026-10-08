"""Market probability layer for the full football market set.

This module generates model probabilities and fair odds even when bookmaker
prices are unavailable. It never invents a market price; value decisions still
require a concrete odds input.
"""
from __future__ import annotations

from typing import Any

MARKETS = (
    "home_win", "draw", "away_win",
    "first_half_home", "first_half_draw", "first_half_away",
    "btts_yes", "btts_no",
    "over_2_5", "under_2_5",
    "btts_over_2_5",
    "corners_over_8_5", "corners_under_8_5",
    "cards_over_4_5", "cards_under_4_5",
)


def _clamp(p: float, lo: float = 0.02, hi: float = 0.98) -> float:
    return max(lo, min(hi, float(p)))


def _avg_pair(home: dict[str, Any], away: dict[str, Any], key: str, default: float = 0.5) -> float:
    values = []
    for src in (home, away):
        value = src.get(key)
        if value is not None:
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                pass
    return sum(values) / len(values) if values else default


def _ht_probabilities(home: dict[str, Any], away: dict[str, Any]) -> tuple[float, float, float]:
    # Venue-aware history is preferred; recent_form is already shrunk toward
    # neutral priors when samples are sparse.
    h1 = _avg_pair(home, away, "ht_home_rate", 0.33)
    hx = _avg_pair(home, away, "ht_draw_rate", 0.34)
    h2 = _avg_pair(home, away, "ht_away_rate", 0.33)
    total = max(h1 + hx + h2, 1e-9)
    return h1 / total, hx / total, h2 / total


def _score_matrix_combo(dc: dict[str, Any], predicate) -> float | None:
    matrix = dc.get("score_matrix")
    if not matrix:
        return None
    total = sum(sum(row) for row in matrix)
    if total <= 0:
        return None
    value = 0.0
    for i, row in enumerate(matrix):
        for j, p in enumerate(row):
            if predicate(i, j):
                value += float(p)
    return value / total


def build_market_probabilities(
    home_form: dict[str, Any],
    away_form: dict[str, Any],
    dc: dict[str, Any],
) -> dict[str, tuple[float, float, float]]:
    """Return (stat, prediction, bounded-intel) probabilities per market."""
    dc_home = float(dc.get("home_win", 0.50))
    dc_draw = float(dc.get("draw", 0.25))
    dc_away = float(dc.get("away_win", 0.25))
    dc_btts = float(dc.get("btts_yes", 0.50))
    dc_over = float(dc.get("over_2_5", 0.50))

    h1, hx, h2 = _ht_probabilities(home_form, away_form)
    dc_h1 = _score_matrix_combo(dc, lambda i, j: (i * 0.5) > (j * 0.5))
    # A pure FT score matrix cannot determine the exact half-time result, so
    # first-half probabilities are history-led rather than falsely inferred.
    if dc_h1 is not None:
        pass

    bt_over = _score_matrix_combo(dc, lambda i, j: i > 0 and j > 0 and i + j >= 3)
    if bt_over is None:
        bt_over = max(0.02, min(dc_btts, dc_over) * 0.65)

    corner_over = _avg_pair(home_form, away_form, "corners_over8_5_rate", 0.50)
    card_over = _avg_pair(home_form, away_form, "cards_over4_5_rate", 0.50)

    form_edge = max(-1.0, min(1.0,
        (float(home_form.get("points_per_game", 1.0)) -
         float(away_form.get("points_per_game", 1.0))) / 3.0
    ))
    goal_signal = _avg_pair(home_form, away_form, "over25_rate", 0.50)
    btts_signal = _avg_pair(home_form, away_form, "btts_rate", 0.50)

    def trio(stat: float, pred: float, intel: float | None = None) -> tuple[float, float, float]:
        i = 0.50 if intel is None else float(intel)
        return _clamp(stat), _clamp(pred), _clamp(i)

    first_half_intel = _clamp(0.50 + 0.10 * form_edge)
    # Independent statistical/prediction views are intentionally conservative.
    first_half = {
        "first_half_home": trio(h1, _clamp(0.70 * h1 + 0.30 * (0.33 + 0.08 * form_edge)), first_half_intel),
        "first_half_draw": trio(hx, _clamp(0.70 * hx + 0.30 * 0.34), _clamp(0.50 - 0.05 * abs(form_edge))),
        "first_half_away": trio(h2, _clamp(0.70 * h2 + 0.30 * (0.33 - 0.06 * form_edge)), _clamp(0.50 - 0.08 * form_edge)),
    }
    # Normalize each engine's three first-half outcomes so the 1/X/2 set is
    # coherent even after conservative shrinkage.
    for engine_index in range(3):
        total = sum(first_half[k][engine_index] for k in first_half)
        for k in first_half:
            values = list(first_half[k])
            values[engine_index] = values[engine_index] / total
            first_half[k] = tuple(values)

    out = {
        "home_win": trio(dc_home * 0.75 + 0.25 * (0.50 + 0.15 * form_edge),
                          dc_home * 0.85 + 0.15 * (0.50 + 0.12 * form_edge)),
        "draw": trio(dc_draw * 0.85 + 0.15 * 0.26, dc_draw),
        "away_win": trio(dc_away * 0.75 + 0.25 * (0.50 - 0.12 * form_edge),
                          dc_away * 0.85 + 0.15 * (0.50 - 0.10 * form_edge)),
        "btts_yes": trio(dc_btts, dc_btts * 0.90 + 0.10 * btts_signal),
        "btts_no": trio(1.0 - dc_btts, 1.0 - (dc_btts * 0.90 + 0.10 * btts_signal)),
        "over_2_5": trio(dc_over, dc_over * 0.90 + 0.10 * goal_signal),
        "under_2_5": trio(1.0 - dc_over, 1.0 - (dc_over * 0.90 + 0.10 * goal_signal)),
        "btts_over_2_5": trio(bt_over, bt_over * 0.92 + 0.08 * min(btts_signal, goal_signal), None),
        "corners_over_8_5": trio(corner_over, corner_over, None),
        "corners_under_8_5": trio(1.0 - corner_over, 1.0 - corner_over, None),
        "cards_over_4_5": trio(card_over, card_over, None),
        "cards_under_4_5": trio(1.0 - card_over, 1.0 - card_over, None),
    }
    out.update(first_half)
    return out


def as_model_market_rows(probabilities: dict[str, tuple[float, float, float]]) -> list[dict[str, Any]]:
    labels = {
        "home_win": "MS 1", "draw": "MS X", "away_win": "MS 2",
        "first_half_home": "İY 1", "first_half_draw": "İY X", "first_half_away": "İY 2",
        "btts_yes": "KG VAR", "btts_no": "KG YOK",
        "over_2_5": "ÜST 2.5", "under_2_5": "ALT 2.5",
        "btts_over_2_5": "KG VAR + ÜST 2.5",
        "corners_over_8_5": "Korner ÜST 8.5", "corners_under_8_5": "Korner ALT 8.5",
        "cards_over_4_5": "Kart ÜST 4.5", "cards_under_4_5": "Kart ALT 4.5",
    }
    rows = []
    for market, trio_probs in probabilities.items():
        model = max(0.02, min(0.98, sum(trio_probs) / 3.0))
        rows.append({
            "market_key": market,
            "market": labels.get(market, market),
            "model_probability": round(model, 6),
            "model_probability_pct": round(model * 100, 2),
            "fair_odds": round(1.0 / model, 2),
            "odds_required_for_value": round(1.0 / model * 1.03, 2),
        })
    return sorted(rows, key=lambda x: x["model_probability"], reverse=True)
