import unittest

from app.four_engine_fusion import fuse_market
from app.coupon_engine_v5 import build_candidates, build_coupon


class FourEngineTests(unittest.TestCase):
    def setUp(self):
        self.hf = {
            "matches": 8, "points_per_game": 2.0,
            "goal_diff_per_game": 0.8, "goals_for_per_game": 1.8,
            "goals_against_per_game": 1.0, "btts_rate": 0.65,
            "over25_rate": 0.70,
        }
        self.af = {
            "matches": 8, "points_per_game": 1.0,
            "goal_diff_per_game": -0.4, "goals_for_per_game": 1.1,
            "goals_against_per_game": 1.7, "btts_rate": 0.60,
            "over25_rate": 0.65,
        }
        self.dc = {"home_win": 0.68, "btts_yes": 0.63, "over_2_5": 0.66}
        self.fs = {"btts_rate": 0.67, "over_25_rate": 0.68}

    def test_fusion_probability_is_bounded(self):
        out = fuse_market("home_win", footystats=self.fs,
                          home_form=self.hf, away_form=self.af,
                          dixon_coles=self.dc)
        self.assertGreaterEqual(out["probability"], 0.01)
        self.assertLessEqual(out["probability"], 0.99)
        self.assertEqual(out["engine_count"], 4)

    def test_coupon_requires_value_and_quality(self):
        fixture = {
            "fixture_id": "A|B|2026-09-27",
            "home": "A", "away": "B", "league": "Test",
            "odds": {"home_win": 1.90, "btts_yes": 1.90, "over_2_5": 1.80},
            "fusion": {
                "home_win": {"probability": .68, "data_quality": .90, "agreement": 4,
                             "engine_count": 4, "votes": []},
                "btts_yes": {"probability": .40, "data_quality": .90, "agreement": 4,
                             "engine_count": 4, "votes": []},
                "over_2_5": {"probability": .65, "data_quality": .90, "agreement": 4,
                             "engine_count": 4, "votes": []},
            }
        }
        candidates = build_candidates([fixture])
        self.assertTrue(any(x["market"] == "home_win" for x in candidates))
        self.assertFalse(any(x["market"] == "btts_yes" for x in candidates))
        coupon = build_coupon(candidates)
        self.assertGreaterEqual(coupon["leg_count"], 1)


if __name__ == "__main__":
    unittest.main()
