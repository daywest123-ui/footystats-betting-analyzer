from app.unified_betting_engine import HTFT, _normalize, _no_vig_1x2

def test_htft_has_nine_outcomes():
    assert len(HTFT) == 9

def test_normalize_sums_to_one():
    p = _normalize({"1/1": 3, "X/X": 2})
    assert abs(sum(p.values()) - 1) < 1e-9
    assert set(p) == set(HTFT)

def test_no_vig_sums_to_one():
    p = _no_vig_1x2({"home_win": 2.0, "draw": 3.0, "away_win": 4.0})
    assert abs(sum(p.values()) - 1) < 1e-9

def test_no_vig_empty_without_odds():
    assert _no_vig_1x2(None) == {}
