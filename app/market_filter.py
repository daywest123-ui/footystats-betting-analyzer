"""Odds, value and consensus filter.

This module intentionally returns NO BET when a candidate does not meet the
minimum evidence threshold. It does not guarantee outcomes.
"""

from dataclasses import dataclass
from typing import Optional
from .config import (
    MIN_ODDS, IDEAL_ODDS_MIN, IDEAL_ODDS_MAX,
    MIN_CONFIDENCE, MIN_VALUE_EDGE, HIGH_ODDS_WARNING,
)


@dataclass
class MarketCandidate:
    match: str
    market: str
    odds: float
    probability: float
    engine_votes: int
    engine_count: int = 3
    data_quality: float = 1.0


def evaluate(candidate: MarketCandidate) -> dict:
    if candidate.odds <= 1.0:
        return {"decision": "NO BET", "reason": "Geçersiz oran"}

    implied_probability = 1 / candidate.odds
    fair_odds = 1 / candidate.probability if candidate.probability > 0 else None
    value_edge = candidate.probability * candidate.odds - 1
    consensus = candidate.engine_votes / candidate.engine_count

    reasons = []
    if candidate.odds < MIN_ODDS:
        reasons.append(f"Oran {MIN_ODDS} altı")
    if candidate.probability < MIN_CONFIDENCE:
        reasons.append("Model güveni düşük")
    if value_edge <= MIN_VALUE_EDGE:
        reasons.append("Pozitif value yok")
    if consensus < 2/3:
        reasons.append("Motor consensus yetersiz")
    if candidate.data_quality < 0.60:
        reasons.append("Veri kalitesi yetersiz")

    decision = "NO BET" if reasons else "ANALYZE"

    confidence = (
        candidate.probability * 0.45
        + min(max(value_edge, 0), 0.30) * 0.25
        + consensus * 0.20
        + candidate.data_quality * 0.10
    ) * 10

    zone = (
        "IDEAL"
        if IDEAL_ODDS_MIN <= candidate.odds <= IDEAL_ODDS_MAX
        else "HIGH_RISK" if candidate.odds > HIGH_ODDS_WARNING else "ACCEPTABLE"
    )

    return {
        "match": candidate.match,
        "market": candidate.market,
        "odds": round(candidate.odds, 2),
        "probability_pct": round(candidate.probability * 100, 1),
        "implied_probability_pct": round(implied_probability * 100, 1),
        "fair_odds": round(fair_odds, 2) if fair_odds else None,
        "value_edge_pct": round(value_edge * 100, 2),
        "consensus": f"{candidate.engine_votes}/{candidate.engine_count}",
        "confidence_10": round(confidence, 2),
        "odds_zone": zone,
        "decision": decision,
        "reasons": reasons,
    }
