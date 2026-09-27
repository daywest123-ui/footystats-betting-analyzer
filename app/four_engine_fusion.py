"""Four-engine fusion layer for FootyStats football analysis.

This module combines four independent *method families* inspired by the
public projects reviewed for this repository:
1) FootyStats CSV feature extraction,
2) ML-style ensemble scoring,
3) Bayesian/Poisson + Dixon-Coles modelling,
4) statistical football-library style feature engineering.

No source code is copied from third-party repositories. The output is a
transparent probability ensemble with explicit data-quality penalties.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math


def _clamp(x: float, lo: float = 0.01, hi: float = 0.99) -> float:
    return max(lo, min(hi, float(x)))


def _mean(values: list[float], default: float = 0.5) -> float:
    vals = [float(v) for v in values if v is not None]
    return sum(vals) / len(vals) if vals else default


@dataclass(frozen=True)
class EngineVote:
    name: str
    probability: float
    weight: float
    available: bool
    reason: str


def _footystats_probability(market: str, fs: dict[str, Any] | None,
                            home_form: dict[str, Any] | None,
                            away_form: dict[str, Any] | None) -> EngineVote:
    fs = fs or {}
    hf, af = home_form or {}, away_form or {}
    if market == "btts_yes":
        p = _mean([fs.get("btts_rate"), hf.get("btts_rate"), af.get("btts_rate")])
        reason = "FootyStats BTTS + recent form"
    elif market == "over_2_5":
        p = _mean([fs.get("over_25_rate"), hf.get("over25_rate"), af.get("over25_rate")])
        reason = "FootyStats O2.5 + recent form"
    elif market == "home_win":
        h = float(hf.get("points_per_game", 1.0))
        a = float(af.get("points_per_game", 1.0))
        gd = float(hf.get("goal_diff_per_game", 0.0)) - float(af.get("goal_diff_per_game", 0.0))
        p = _clamp(0.50 + (h - a) / 20.0 + gd / 18.0 + 0.03)
        reason = "FootyStats/form strength differential"
    else:
        return EngineVote("FOOTYSTATS", 0.5, 0.0, False, "market unsupported")
    return EngineVote("FOOTYSTATS", _clamp(p), 0.30, True, reason)


def _ensemble_probability(market: str, hf: dict[str, Any],
                          af: dict[str, Any], dc: dict[str, Any] | None) -> EngineVote:
    dc = dc or {}
    if market == "home_win":
        p = 0.62 * float(dc.get("home_win", 0.5)) + 0.38 * _clamp(
            0.50 + (float(hf.get("points_per_game", 1.0)) -
                    float(af.get("points_per_game", 1.0))) / 18.0)
    elif market == "btts_yes":
        p = 0.62 * float(dc.get("btts_yes", 0.5)) + 0.38 * _mean(
            [hf.get("btts_rate"), af.get("btts_rate")])
    elif market == "over_2_5":
        p = 0.62 * float(dc.get("over_2_5", 0.5)) + 0.38 * _mean(
            [hf.get("over25_rate"), af.get("over25_rate")])
    else:
        return EngineVote("ENSEMBLE", 0.5, 0.0, False, "market unsupported")
    return EngineVote("ENSEMBLE", _clamp(p), 0.25, True, "ensemble of form + score model")


def _bayesian_probability(market: str, dc: dict[str, Any] | None) -> EngineVote:
    dc = dc or {}
    key = {"home_win": "home_win", "btts_yes": "btts_yes",
           "over_2_5": "over_2_5"}.get(market)
    if not key or key not in dc:
        return EngineVote("BAYES_DIXON_COLES", 0.5, 0.0, False, "no Dixon-Coles output")
    return EngineVote("BAYES_DIXON_COLES", _clamp(float(dc[key])), 0.30, True,
                      "Poisson/Elo/Dixon-Coles")


def _football_stats_probability(market: str, hf: dict[str, Any],
                                af: dict[str, Any], fs: dict[str, Any] | None) -> EngineVote:
    fs = fs or {}
    if market == "home_win":
        h_attack = float(hf.get("goals_for_per_game", 1.25))
        a_def = float(af.get("goals_against_per_game", 1.25))
        a_attack = float(af.get("goals_for_per_game", 1.25))
        h_def = float(hf.get("goals_against_per_game", 1.25))
        edge = (h_attack - a_def) - (a_attack - h_def)
        p = _clamp(0.50 + edge / 8.0)
    elif market == "btts_yes":
        p = _mean([hf.get("btts_rate"), af.get("btts_rate"), fs.get("btts_rate")])
    elif market == "over_2_5":
        p = _mean([hf.get("over25_rate"), af.get("over25_rate"), fs.get("over_25_rate")])
    else:
        return EngineVote("FOOTY_STATS", 0.5, 0.0, False, "market unsupported")
    return EngineVote("FOOTY_STATS", _clamp(p), 0.15, True, "feature-engineered football statistics")


def fuse_market(market: str, *, footystats: dict[str, Any] | None,
                home_form: dict[str, Any] | None, away_form: dict[str, Any] | None,
                dixon_coles: dict[str, Any] | None,
                web_probability: float | None = None,
                web_confidence: float = 0.0) -> dict[str, Any]:
    hf, af = home_form or {}, away_form or {}
    votes = [
        _footystats_probability(market, footystats, hf, af),
        _ensemble_probability(market, hf, af, dixon_coles),
        _bayesian_probability(market, dixon_coles),
        _football_stats_probability(market, hf, af, footystats),
    ]

    if web_probability is not None and web_confidence > 0:
        votes.append(EngineVote("WEB_INTELLIGENCE", _clamp(web_probability),
                                min(0.10, 0.10 * web_confidence), True,
                                "bounded external intelligence"))

    active = [v for v in votes if v.available and v.weight > 0]
    total_w = sum(v.weight for v in active)
    probability = sum(v.probability * v.weight for v in active) / total_w if total_w else 0.5
    agreement = sum(1 for v in active if abs(v.probability - probability) <= 0.08)
    dispersion = math.sqrt(_mean([(v.probability - probability) ** 2 for v in active], 0.0))
    data_quality = _clamp(
        0.55 + 0.10 * len(active) + 0.05 * min(
            int(hf.get("matches", 0)), int(af.get("matches", 0)), 8
        ) - min(0.25, dispersion),
        0.0, 1.0,
    )

    return {
        "market": market,
        "probability": round(_clamp(probability), 6),
        "probability_pct": round(_clamp(probability) * 100, 2),
        "engine_count": len(active),
        "agreement": agreement,
        "dispersion": round(dispersion, 5),
        "data_quality": round(data_quality, 4),
        "votes": [
            {"engine": v.name, "probability_pct": round(v.probability * 100, 2),
             "weight": v.weight, "reason": v.reason}
            for v in votes if v.available
        ],
    }
