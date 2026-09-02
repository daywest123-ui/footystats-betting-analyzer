"""Signal fusion and disciplined market selection.

Analysis only: probabilities are estimates, not guarantees.
"""
from __future__ import annotations

MIN_ODDS = 1.55
IDEAL_ODDS_MIN = 1.60
IDEAL_ODDS_MAX = 2.20
MIN_CONFIDENCE = 0.55
MIN_CONSENSUS = 2 / 3


def fuse(stat_probability: float, web_score: float, web_confidence: float,
         market_probability: float | None = None) -> dict:
    stat_probability = max(0.0, min(1.0, stat_probability))
    web_component = 0.5 + 0.25 * max(-1.0, min(1.0, web_score))
    web_weight = 0.25 * max(0.0, min(1.0, web_confidence))
    final_probability = stat_probability * (1 - web_weight) + web_component * web_weight

    value = None
    if market_probability is not None and market_probability > 0:
        value = final_probability - market_probability

    return {
        "stat_probability": round(stat_probability, 4),
        "web_score": round(web_score, 4),
        "web_confidence": round(web_confidence, 4),
        "final_probability": round(final_probability, 4),
        "value_edge": None if value is None else round(value, 4),
        "category": (
            "STRONG" if final_probability >= 0.70 else
            "VALUE" if final_probability >= 0.58 else
            "WATCH" if final_probability >= 0.50 else "AVOID"
        ),
    }


def evaluate_market(match: str, market: str, odds: float, probability: float,
                    engine_votes: int, engine_count: int = 3,
                    data_quality: float = 1.0) -> dict:
    """Final gate: low odds and weak evidence are rejected as NO BET."""
    probability = max(0.0, min(1.0, probability))
    if odds <= 1.0:
        return {"match": match, "market": market, "decision": "NO BET",
                "reason": "Geçersiz oran"}

    implied = 1 / odds
    value_edge = probability * odds - 1
    fair_odds = 1 / probability if probability else None
    consensus = engine_votes / max(engine_count, 1)

    reasons = []
    if odds < MIN_ODDS:
        reasons.append(f"Çok düşük oran (< {MIN_ODDS})")
    if probability < MIN_CONFIDENCE:
        reasons.append("Model olasılığı %55 altında")
    if value_edge <= 0:
        reasons.append("Pozitif value edge yok")
    if consensus < MIN_CONSENSUS:
        reasons.append("En az 2/3 motor consensus sağlamadı")
    if data_quality < 0.60:
        reasons.append("Veri kalitesi yetersiz")

    zone = "IDEAL" if IDEAL_ODDS_MIN <= odds <= IDEAL_ODDS_MAX else (
        "HIGH_ODDS" if odds > 2.50 else "ACCEPTABLE"
    )
    decision = "ANALYZE" if not reasons else "NO BET"

    confidence = min(10.0, (
        probability * 5.5 +
        max(0.0, min(value_edge, 0.30)) * 8 +
        consensus * 1.2 +
        data_quality * 0.8
    ))

    return {
        "match": match,
        "market": market,
        "odds": round(odds, 2),
        "odds_zone": zone,
        "model_probability_pct": round(probability * 100, 1),
        "implied_probability_pct": round(implied * 100, 1),
        "fair_odds": round(fair_odds, 2) if fair_odds else None,
        "value_edge_pct": round(value_edge * 100, 2),
        "consensus": f"{engine_votes}/{engine_count}",
        "confidence_10": round(confidence, 2),
        "decision": decision,
        "reasons": reasons,
    }
