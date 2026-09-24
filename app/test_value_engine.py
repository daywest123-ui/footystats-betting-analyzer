from value_engine import devig_proportional, value_signal

def test_devig():
    p = devig_proportional([2.0, 3.0, 4.0])
    assert abs(sum(p) - 1.0) < 1e-9

def test_value_signal():
    s = value_signal("1X2", "HOME", 2.20, 0.50)
    assert s.decision == "VALUE"
    assert s.ev > 0

# E2E validation marker
