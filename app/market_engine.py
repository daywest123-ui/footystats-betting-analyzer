"""Three-source consensus layer for football market candidates.

Market probability is a benchmark for value, not an independent model vote.
This prevents the model from partially voting for the same market it later
uses to calculate its edge.
"""
from __future__ import annotations

from app.signal_fusion import evaluate_market


def consensus_probability(
    stat_probability: float,
    prediction_probability: float,
    intelligence_probability: float,
) -> tuple[float, int]:
    probs = [
        max(0.0, min(1.0, p))
        for p in (stat_probability, prediction_probability, intelligence_probability)
    ]
    votes = sum(p >= 0.55 for p in probs)
    probability = probs[0] * 0.45 + probs[1] * 0.35 + probs[2] * 0.20
    return probability, votes


def analyze_candidate(
    match: str,
    market: str,
    odds: float,
    stat_probability: float,
    prediction_probability: float,
    intelligence_probability: float,
    data_quality: float = 1.0,
    market_probability: float | None = None,
) -> dict:
    # Current odds are a value benchmark only. They are never counted as a
    # second model vote because that would double-count the same information.
    probability, votes = consensus_probability(
        stat_probability, prediction_probability, intelligence_probability
    )
    result = evaluate_market(
        match,
        market,
        odds,
        probability,
        votes,
        3,
        data_quality,
        odds_market_probability=market_probability,
    )
    result["engines"] = {
        "statistical_pct": round(stat_probability * 100, 1),
        "prediction_pct": round(prediction_probability * 100, 1),
        "intelligence_pct": round(intelligence_probability * 100, 1),
        "market_benchmark_pct": (
            None if market_probability is None else round(market_probability * 100, 1)
        ),
    }
    return result
