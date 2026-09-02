"""Three-engine consensus layer for football market candidates."""
from __future__ import annotations
from signal_fusion import evaluate_market

def consensus_probability(stat_probability: float, prediction_probability: float,
                          intelligence_probability: float) -> tuple[float, int]:
    probs = [stat_probability, prediction_probability, intelligence_probability]
    votes = sum(p >= 0.55 for p in probs)
    # Robust weighted blend: statistical evidence remains primary.
    probability = probs[0] * 0.45 + probs[1] * 0.35 + probs[2] * 0.20
    return probability, votes

def analyze_candidate(match: str, market: str, odds: float,
                      stat_probability: float, prediction_probability: float,
                      intelligence_probability: float, data_quality: float = 1.0) -> dict:
    probability, votes = consensus_probability(
        stat_probability, prediction_probability, intelligence_probability
    )
    result = evaluate_market(
        match, market, odds, probability, votes, 3, data_quality
    )
    result["engines"] = {
        "statistical_pct": round(stat_probability * 100, 1),
        "prediction_pct": round(prediction_probability * 100, 1),
        "intelligence_pct": round(intelligence_probability * 100, 1),
    }
    return result
