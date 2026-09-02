from app.market_engine import analyze_candidate

def test_low_odds_rejected():
    r = analyze_candidate("A vs B", "MS1", 1.30, .80, .76, .72)
    assert r["decision"] == "NO BET"

def test_positive_value_candidate():
    r = analyze_candidate("A vs B", "KG VAR", 1.85, .66, .63, .61)
    assert r["decision"] == "ANALYZE"
