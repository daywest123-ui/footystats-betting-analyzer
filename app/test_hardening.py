import unittest

from app.market_engine import consensus_probability
from app.odds_pipeline import _devig_probability
from app.signal_fusion import evaluate_market
from app.auto_match_selector import _market_probabilities


class HardeningTests(unittest.TestCase):
    def test_devig_1x2_sums_to_one(self):
        odds = {"home_win": 2.0, "draw": 3.5, "away_win": 4.0}
        probs = [_devig_probability(odds, key) for key in odds]
        self.assertTrue(all(p is not None for p in probs))
        self.assertAlmostEqual(sum(probs), 1.0, places=9)

    def test_devig_btts_sums_to_one(self):
        odds = {"btts_yes": 1.8, "btts_no": 2.0}
        self.assertAlmostEqual(
            _devig_probability(odds, "btts_yes")
            + _devig_probability(odds, "btts_no"),
            1.0,
            places=9,
        )

    def test_value_edge_is_probability_edge_and_ev_is_separate(self):
        result = evaluate_market(
            "A vs B", "home_win", 2.0, 0.60, 3, 3,
            data_quality=1.0, odds_market_probability=0.48
        )
        self.assertAlmostEqual(result["value_edge_pct"], 12.0, places=6)
        self.assertAlmostEqual(result["ev_pct"], 20.0, places=6)
        self.assertEqual(result["decision"], "ANALYZE")

    def test_consensus_clamps_and_counts(self):
        probability, votes = consensus_probability(1.2, -0.2, 0.60)
        self.assertAlmostEqual(probability, 0.45 * 1.0 + 0.35 * 0.0 + 0.20 * 0.60)
        self.assertEqual(votes, 2)

    def test_market_probability_components_are_not_identical(self):
        home = {"points_per_game": 2.0, "goal_diff_per_game": 0.75,
                "over25_rate": 0.7, "btts_rate": 0.65, "matches": 8}
        away = {"points_per_game": 1.0, "goal_diff_per_game": -0.25,
                "over25_rate": 0.4, "btts_rate": 0.45, "matches": 8}
        probs = _market_probabilities(home, away, {"web_score": 0.2, "confidence": 0.8})
        for stat, pred, intel in probs.values():
            self.assertNotEqual(stat, pred)
            self.assertTrue(0.05 <= stat <= 0.95)
            self.assertTrue(0.05 <= pred <= 0.95)
            self.assertTrue(0.05 <= intel <= 0.95)


if __name__ == "__main__":
    unittest.main()
