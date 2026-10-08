import unittest

from app.market_probabilities import MARKETS, build_market_probabilities, as_model_market_rows


class TestFullMarketLayer(unittest.TestCase):
    def setUp(self):
        self.home = {
            "matches": 8,
            "points_per_game": 2.0,
            "over25_rate": 0.62,
            "btts_rate": 0.58,
            "ht_home_rate": 0.45,
            "ht_draw_rate": 0.35,
            "ht_away_rate": 0.20,
            "corners_over8_5_rate": 0.64,
            "cards_over4_5_rate": 0.57,
        }
        self.away = {
            "matches": 8,
            "points_per_game": 1.0,
            "over25_rate": 0.50,
            "btts_rate": 0.54,
            "ht_home_rate": 0.20,
            "ht_draw_rate": 0.40,
            "ht_away_rate": 0.40,
            "corners_over8_5_rate": 0.52,
            "cards_over4_5_rate": 0.49,
        }
        self.dc = {
            "home_win": 0.56, "draw": 0.24, "away_win": 0.20,
            "btts_yes": 0.58, "over_2_5": 0.55,
            "score_matrix": [
                [0.10, 0.08, 0.03],
                [0.07, 0.08, 0.05],
                [0.04, 0.05, 0.04],
            ],
        }

    def test_full_market_set(self):
        probs = build_market_probabilities(self.home, self.away, self.dc)
        self.assertEqual(set(probs), set(MARKETS))
        self.assertEqual(len(as_model_market_rows(probs)), len(MARKETS))

    def test_first_half_engines_sum_to_one(self):
        probs = build_market_probabilities(self.home, self.away, self.dc)
        for idx in range(3):
            self.assertAlmostEqual(
                sum(probs[k][idx] for k in ("first_half_home", "first_half_draw", "first_half_away")),
                1.0, places=6
            )

    def test_fair_odds_are_positive(self):
        rows = as_model_market_rows(build_market_probabilities(self.home, self.away, self.dc))
        self.assertTrue(all(row["fair_odds"] > 1 for row in rows))
        self.assertTrue(any(row["market"] == "KG VAR + ÜST 2.5" for row in rows))


if __name__ == "__main__":
    unittest.main()
