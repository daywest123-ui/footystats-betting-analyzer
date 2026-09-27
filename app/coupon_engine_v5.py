"""Transparent coupon construction for the four-engine analyzer.

This is a paper-analysis/coupon-candidate generator. It never places bets.
It rejects weak data, poor consensus and negative/insufficient value instead
of forcing a coupon.
"""
from __future__ import annotations

from itertools import combinations
from math import prod
from typing import Any

from app.value_engine import implied_probability


MIN_PROBABILITY = 0.55
MIN_EDGE = 0.025
MIN_EV = 0.03
MIN_DATA_QUALITY = 0.65
MAX_LEGS = 4
MIN_ODDS = 1.50
MAX_ODDS = 4.50


def _market_key(row: dict[str, Any]) -> str:
    return f"{row.get('home')}|{row.get('away')}|{row.get('market')}"


def build_candidates(fixtures: list[dict[str, Any]], *,
                     max_candidates: int = 20) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for f in fixtures:
        for market in ("home_win", "btts_yes", "over_2_5"):
            fused = f.get("fusion", {}).get(market)
            odds = f.get("odds", {}).get(market)
            if not fused or not odds:
                continue
            odds = float(odds)
            p = float(fused["probability"])
            implied = implied_probability(odds) if odds > 1 else 1.0
            edge = p - implied
            ev = p * odds - 1.0
            if not (MIN_ODDS <= odds <= MAX_ODDS):
                continue
            if p < MIN_PROBABILITY or edge < MIN_EDGE or ev < MIN_EV:
                continue
            if float(fused.get("data_quality", 0)) < MIN_DATA_QUALITY:
                continue
            consensus = int(fused.get("agreement", 0))
            if consensus < max(2, int(fused.get("engine_count", 0)) - 1):
                continue
            candidates.append({
                "fixture_id": f.get("fixture_id"),
                "home": f.get("home"),
                "away": f.get("away"),
                "league": f.get("league"),
                "market": market,
                "odds": round(odds, 2),
                "model_probability_pct": round(p * 100, 2),
                "implied_probability_pct": round(implied * 100, 2),
                "value_edge_pct": round(edge * 100, 2),
                "ev_pct": round(ev * 100, 2),
                "data_quality": fused["data_quality"],
                "engine_consensus": f"{consensus}/{fused.get('engine_count', 0)}",
                "score": round(ev * 100 + edge * 60 + p * 10, 3),
                "votes": fused.get("votes", []),
            })

    return sorted(candidates, key=lambda x: x["score"], reverse=True)[:max_candidates]


def build_coupon(candidates: list[dict[str, Any]], max_legs: int = MAX_LEGS) -> dict[str, Any]:
    selected: list[dict[str, Any]] = []
    used_fixtures: set[str] = set()

    for c in candidates:
        fixture = str(c.get("fixture_id") or f"{c.get('home')}|{c.get('away')}")
        if fixture in used_fixtures:
            continue
        selected.append(c)
        used_fixtures.add(fixture)
        if len(selected) >= max_legs:
            break

    combined_odds = prod(float(x["odds"]) for x in selected) if selected else 0.0
    return {
        "status": "COUPON_CANDIDATES" if selected else "NO_BET",
        "legs": selected,
        "leg_count": len(selected),
        "combined_decimal_odds": round(combined_odds, 2) if selected else None,
        "selection_rule": "one market per fixture; no forced leg",
    }
