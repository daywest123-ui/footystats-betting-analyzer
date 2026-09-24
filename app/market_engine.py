"""Three-source consensus layer for football market candidates."""
from __future__ import annotations

from app.signal_fusion import evaluate_market


def consensus_probability(stat_probability: float, prediction_probability: float,
                          intelligence_probability: float) -> tuple[float, int]:
    probs = [max(0.0, min(1.0, p)) for p in (
        stat_probability, prediction_probability, intelligence_probability
    )]
    votes = sum(p >= 0.55 for p in probs)
    probability = probs[0] * 0.45 + probs[1] * 0.35 + probs[2] * 0.20
    return probability, votes


def analyze_candidate(match: str, market: str, odds: float,
                      stat_probability: float, prediction_probability: float,
                      intelligence_probability: float, data_quality: float = 1.0,
                      market_probability: float | None = None) -> dict:
    consensus_prediction = (
        market_probability
        if market_probability is not None
        else prediction_probability
    )
    probability, votes = consensus_probability(
        stat_probability, consensus_prediction, intelligence_probability
    )
    result = evaluate_market(
        match, market, odds, probability, votes, 3, data_quality,
        odds_market_probability=market_probability,
    )
    result["engines"] = {
        "statistical_pct": round(stat_probability * 100, 1),
        "market_or_prediction_pct": round(consensus_prediction * 100, 1),
        "intelligence_pct": round(intelligence_probability * 100, 1),
    }
    return result
