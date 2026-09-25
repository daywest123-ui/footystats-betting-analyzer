import unittest

from app.dixon_coles_model import predict


class DixonColesModelTests(unittest.TestCase):
    def setUp(self):
        self.matches = [
            {"date": "2026-08-01", "home": "Alpha", "away": "Beta", "home_goals": 2, "away_goals": 0, "finished": True},
            {"date": "2026-08-08", "home": "Beta", "away": "Alpha", "home_goals": 1, "away_goals": 1, "finished": True},
            {"date": "2026-08-15", "home": "Alpha", "away": "Gamma", "home_goals": 3, "away_goals": 1, "finished": True},
            {"date": "2026-08-22", "home": "Gamma", "away": "Beta", "home_goals": 0, "away_goals": 2, "finished": True},
            {"date": "2026-08-29", "home": "Beta", "away": "Gamma", "home_goals": 2, "away_goals": 2, "finished": True},
            {"date": "2026-09-05", "home": "Gamma", "away": "Alpha", "home_goals": 1, "away_goals": 2, "finished": True},
        ]

    def test_probabilities_are_valid_and_partition_markets(self):
        r = predict(self.matches, "Alpha", "Beta", "2026-09-10")
        self.assertAlmostEqual(r["home_win"] + r["draw"] + r["away_win"], 1.0, places=6)
        self.assertAlmostEqual(r["btts_yes"] + r["btts_no"], 1.0, places=6)
        self.assertAlmostEqual(r["over_2_5"] + r["under_2_5"], 1.0, places=6)
        for key in ("home_win", "draw", "away_win", "btts_yes", "btts_no", "over_2_5", "under_2_5"):
            self.assertGreaterEqual(r[key], 0.0)
            self.assertLessEqual(r[key], 1.0)

    def test_score_matrix_is_normalized(self):
        r = predict(self.matches, "Alpha", "Beta", "2026-09-10")
        self.assertAlmostEqual(sum(sum(row) for row in r["score_matrix"]), 1.0, places=6)
        self.assertEqual(len(r["score_matrix"]), 9)
        self.assertEqual(len(r["score_matrix"][0]), 9)

    def test_future_match_does_not_change_prediction(self):
        baseline = predict(self.matches, "Alpha", "Beta", "2026-09-10")
        future = self.matches + [{
            "date": "2026-10-01", "home": "Alpha", "away": "Beta",
            "home_goals": 0, "away_goals": 8, "finished": True,
        }]
        leaked = predict(future, "Alpha", "Beta", "2026-09-10")
        for key in ("home_win", "draw", "away_win", "btts_yes", "over_2_5", "lambda_home", "lambda_away", "elo_home", "elo_away"):
            self.assertAlmostEqual(baseline[key], leaked[key], places=10)


if __name__ == "__main__":
    unittest.main()
