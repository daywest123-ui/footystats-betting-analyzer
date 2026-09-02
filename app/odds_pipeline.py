"""Join live odds with three-engine probability estimates."""
from __future__ import annotations
from market_engine import analyze_candidate
from odds_client import get_fixture_odds, extract_markets

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
                                   data_quality)
        results.append(result)

    # Never force a selection: only eligible candidates survive ranking.
    return sorted(
        results,
        key=lambda x: (x["decision"] == "ANALYZE", x.get("confidence_10", 0)),
        reverse=True,
    )
