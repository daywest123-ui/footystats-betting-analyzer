"""Combine statistical model output with public-web intelligence.

This is a ranking layer, not a guarantee and not an automatic betting executor.
"""
from __future__ import annotations


def fuse(stat_probability: float, web_score: float, web_confidence: float, market_probability: float | None = None) -> dict:
    stat_probability = max(0.0, min(1.0, stat_probability))
    web_component = 0.5 + 0.25 * max(-1.0, min(1.0, web_score))
    # Web influence is capped so noisy public opinion cannot overwhelm statistics.
    web_weight = 0.25 * max(0.0, min(1.0, web_confidence))
    final_probability = stat_probability * (1 - web_weight) + web_component * web_weight
    value = None
    if market_probability is not None and market_probability > 0:
        value = final_probability - market_probability

    if final_probability >= 0.72 and (value is None or value >= 0.05):
        category = "BANKO"
    elif final_probability >= 0.58 and (value is None or value >= 0.03):
        category = "VALUE"
    elif final_probability >= 0.50:
        category = "SURPRISE"
    else:
        category = "AVOID"

    return {
        "stat_probability": round(stat_probability, 4),
        "web_score": round(web_score, 4),
        "web_confidence": round(web_confidence, 4),
        "final_probability": round(final_probability, 4),
        "value_edge": None if value is None else round(value, 4),
        "category": category,
    }
