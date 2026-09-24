"""Join live odds with three-engine probability estimates."""
from __future__ import annotations
from app.market_engine import analyze_candidate
from app.odds_client import get_fixture_odds, extract_markets


def _devig_probability(odds_map: dict[str, float], key: str) -> float | None:
    keys = {
        "home_win": ("home_win", "draw", "away_win"),
        "draw": ("home_win", "draw", "away_win"),
        "away_win": ("home_win", "draw", "away_win"),
        "btts_yes": ("btts_yes", "btts_no"),
        "btts_no": ("btts_yes", "btts_no"),
        "over_2_5": ("over_2_5", "under_2_5"),
        "under_2_5": ("over_2_5", "under_2_5"),
    }.get(key, ())
    vals = [1.0 / odds_map[k] for k in keys if odds_map.get(k, 0) > 1]
    if len(vals) != len(keys) or not vals or sum(vals) <= 0:
        return None
    target = 1.0 / odds_map[key] if odds_map.get(key, 0) > 1 else None
    return target / sum(vals) if target is not None else None

def analyze_fixture_markets(fixture: dict, probabilities: dict[str, tuple[float,float,float]],
                            data_quality: float = 0.8) -> list[dict]:
    fixture_id = fixture.get("fixture_id")
    if not fixture_id:
        raise ValueError("fixture_id required for odds lookup")

    odds = extract_markets(get_fixture_odds(fixture_id))
    match = f"{fixture.get('home','?')} vs {fixture.get('away','?')}"
    results = []

    for market, engines in probabilities.items():
        if market not in odds:
            continue
        result = analyze_candidate(match, market, odds[market],
                                   engines[0], engines[1], engines[2],
                                   data_quality,
                                   market_probability=_devig_probability(odds, market))
        results.append(result)

    # Never force a selection: only eligible candidates survive ranking.
    return sorted(
        results,
        key=lambda x: (x["decision"] == "ANALYZE", x.get("confidence_10", 0)),
        reverse=True,
    )
