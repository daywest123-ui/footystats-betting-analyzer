import unittest

from app.advanced_market_engine import (
    htft_probabilities,
    no_vig_three_way,
    second_half_result_probabilities,
    value_check,
)


class AdvancedMarketEngineTests(unittest.TestCase):
    def test_htft_probabilities_sum_to_one(self):
        row = {
            "sample": 20,
            "htft": {"X/X": 0.20, "X/1": 0.10, "X/2": 0.10, "1/X": 0.10, "2/X": 0.05, "1/1": 0.20, "1/2": 0.05, "2/1": 0.05, "2/2": 0.10},
        }
        out = htft_probabilities(row, row, {})
        self.assertAlmostEqual(sum(out["probabilities"].values()), 1.0, places=6)

    def test_second_half_probabilities_sum_to_one(self):
        row = {"sample": 20, "second_half_result": {"1": 0.40, "X": 0.30, "2": 0.30}}
        out = second_half_result_probabilities(row, row, {})
        self.assertAlmostEqual(sum(out["probabilities"].values()), 1.0, places=6)

    def test_no_vig_three_way(self):
        out = no_vig_three_way({"home_win": 2.0, "draw": 3.0, "away_win": 4.0})
        self.assertAlmostEqual(sum(out.values()), 1.0, places=6)
        self.assertGreater(out["home_win"], out["away_win"])

    def test_value_gate(self):
        out = value_check(0.60, 2.0)
        self.assertEqual(out["status"], "VALUE_CANDIDATE")
        self.assertGreater(out["ev"], 0)


if __name__ == "__main__":
    unittest.main()
