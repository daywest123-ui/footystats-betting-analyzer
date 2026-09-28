"""Advanced half-market calibration and opportunity scoring.

Keyless, deterministic layer. It does not invent bookmaker odds.
It adds:
- venue-specific HT/FT evidence
- recency/sample shrinkage
- market disagreement penalties
- fair-price/value checks
- explicit NO_OPPORTUNITY states for weak or conflicting evidence
"""
from __future__ import annotations

import math
from typing import Any

HTFT_OUTCOMES = ("X/X", "X/1", "X/2", "1/X", "2/X", "1/1", "1/2", "2/1", "2/2")
SECOND_HALF_RESULTS = ("1", "X", "2")


def _clip(p: float, lo: float = 0.001, hi: float = 0.999) -> float:
    return max(lo, min(hi, float(p)))


def _smoothed_rates(raw: dict[str, Any] | None, outcomes: tuple[str, ...]) -> dict[str, float]:
    """Laplace/Dirichlet smoothing prevents tiny samples becoming extreme."""
    raw = raw or {}
    n = max(0, int(raw.get("sample", 0)))
    alpha = 1.0
    denom = n + alpha * len(outcomes)
    counts = {k: float(raw.get("htft", {}).get(k, 0.0)) * n for k in outcomes}
    return {k: (counts[k] + alpha) / denom for k in outcomes}


def _weighted_mix(parts: list[tuple[float, float]]) -> float:
    valid = [(float(v), max(0.0, float(w))) for v, w in parts if v is not None and w > 0]
    if not valid:
        return 0.0
    total = sum(w for _, w in valid)
    return sum(v * w for v, w in valid) / total


def _reliability(sample: int, max_sample: int = 30) -> float:
    return _clip(math.sqrt(max(0.0, min(sample, max_sample)) / max_sample), 0.05, 1.0)


def htft_probabilities(
    home_venue: dict[str, Any] | None,
    away_venue: dict[str, Any] | None,
    h2h: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Estimate HT/FT probabilities with venue-aware evidence.

    Home venue and away venue dominate. H2H contributes at most 10%.
    The result is intentionally conservative for small samples.
    """
    home_venue = home_venue or {}
    away_venue = away_venue or {}
    h2h = h2h or {}

    hp = _smoothed_rates(home_venue, HTFT_OUTCOMES)
    ap = _smoothed_rates(away_venue, HTFT_OUTCOMES)
    h2hp = _smoothed_rates(h2h, HTFT_OUTCOMES)

    hs = int(home_venue.get("sample", 0))
    aas = int(away_venue.get("sample", 0))
    h2hs = int(h2h.get("sample", 0))

    # Down-weight tiny samples automatically.
    hw = 0.45 * _reliability(hs)
    aw = 0.45 * _reliability(aas)
    h2w = 0.10 * _reliability(h2hs) if h2hs else 0.0

    probs = {
        k: _clip(_weighted_mix([(hp[k], hw), (ap[k], aw), (h2hp[k], h2w)]))
        for k in HTFT_OUTCOMES
    }
    total = sum(probs.values())
    if total:
        probs = {k: v / total for k, v in probs.items()}

    return {
        "probabilities": probs,
        "samples": {"home_venue": hs, "away_venue": aas, "h2h": h2hs},
        "weights": {"home_venue": round(hw, 4), "away_venue": round(aw, 4), "h2h": round(h2w, 4)},
    }


def second_half_result_probabilities(
    home_venue: dict[str, Any] | None,
    away_venue: dict[str, Any] | None,
    h2h: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Estimate second-half 1/X/2 using venue-specific historical results."""
    home_venue = home_venue or {}
    away_venue = away_venue or {}
    h2h = h2h or {}

    def smoothed_second(raw: dict[str, Any]) -> dict[str, float]:
        counts = raw.get("second_half_result", {}) or {}
        n = int(raw.get("sample", 0))
        alpha = 1.0
        denom = n + 3 * alpha
        return {k: (float(counts.get(k, 0)) + alpha) / denom for k in SECOND_HALF_RESULTS}

    hp, ap, h2hp = smoothed_second(home_venue), smoothed_second(away_venue), smoothed_second(h2h)
    hs, aas, h2hs = int(home_venue.get("sample", 0)), int(away_venue.get("sample", 0)), int(h2h.get("sample", 0))

    hw = 0.45 * _reliability(hs)
    aw = 0.45 * _reliability(aas)
    h2w = 0.10 * _reliability(h2hs) if h2hs else 0.0
    probs = {k: _clip(_weighted_mix([(hp[k], hw), (ap[k], aw), (h2hp[k], h2w)])) for k in SECOND_HALF_RESULTS}
    total = sum(probs.values())
    if total:
        probs = {k: v / total for k, v in probs.items()}
    return {"probabilities": probs, "samples": {"home_venue": hs, "away_venue": aas, "h2h": h2hs}}


def no_vig_three_way(odds: dict[str, float] | None) -> dict[str, float]:
    """Convert a 1/X/2 market to normalized market probabilities."""
    odds = odds or {}
    vals = {k: float(odds[k]) for k in ("home_win", "draw", "away_win") if odds.get(k)}
    inv = {k: 1.0 / v for k, v in vals.items() if v > 1}
    total = sum(inv.values())
    return {k: v / total for k, v in inv.items()} if total else {}


def value_check(model_probability: float, odds: float | None, min_edge: float = 0.04, min_ev: float = 0.05) -> dict[str, Any]:
    """Strict value gate for special markets."""
    if odds is None or float(odds) <= 1:
        return {"status": "NO_PRICE"}
    p = _clip(model_probability)
    o = float(odds)
    implied = 1.0 / o
    edge = p - implied
    ev = p * o - 1.0
    status = "VALUE_CANDIDATE" if edge >= min_edge and ev >= min_ev else "FIRSAT_YOK"
    return {
        "status": status,
        "model_probability": round(p, 6),
        "fair_odds": round(1.0 / p, 3),
        "odds": round(o, 3),
        "implied_probability": round(implied, 6),
        "edge": round(edge, 6),
        "ev": round(ev, 6),
    }


def score_special_opportunity(
    model_probability: float,
    *,
    sample: int,
    agreement: int = 0,
    sources: int = 1,
    odds: float | None = None,
    conflicting_model_probability: float | None = None,
) -> dict[str, Any]:
    """Return a conservative confidence score without ranking political choices."""
    p = _clip(model_probability)
    reliability = _reliability(sample)
    disagreement = abs(p - float(conflicting_model_probability)) if conflicting_model_probability is not None else 0.0
    conflict_penalty = min(0.25, disagreement * 0.75)
    support_bonus = min(0.15, max(0, sources - 1) * 0.05 + max(0, agreement - 1) * 0.025)
    confidence = _clip(0.55 * p + 0.30 * reliability + 0.15 * (1.0 - conflict_penalty) + support_bonus, 0.0, 0.99)
    out = {
        "confidence": round(confidence, 4),
        "sample_reliability": round(reliability, 4),
        "conflict_penalty": round(conflict_penalty, 4),
        "support_bonus": round(support_bonus, 4),
    }
    if odds is not None:
        out["value"] = value_check(p, odds)
    return out
