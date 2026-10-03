import unittest

from app.unified_betting_engine import HTFT, _normalize, _no_vig_1x2, select_htft_candidates
from app.open_source_intel import _extract_match


class UnifiedBettingEngineTests(unittest.TestCase):
    def test_htft_has_nine_outcomes(self):
        self.assertEqual(len(HTFT), 9)

    def test_normalize_sums_to_one_and_contains_all_outcomes(self):
        p = _normalize({"1/1": 3, "X/X": 2})
        self.assertAlmostEqual(sum(p.values()), 1.0, places=12)
        self.assertEqual(set(p), set(HTFT))

    def test_no_vig_sums_to_one(self):
        p = _no_vig_1x2({"home_win": 2.0, "draw": 3.0, "away_win": 4.0})
        self.assertAlmostEqual(sum(p.values()), 1.0, places=12)

    def test_no_vig_empty_without_odds(self):
        self.assertEqual(_no_vig_1x2(None), {})

    def test_extract_match_resolves_common_fc_alias_without_flipping_side(self):
        row = {
            "home_team": "Liverpool FC", "away_team": "Chelsea",
            "home_score_normaltime": 2, "away_score_normaltime": 1,
            "home_score_period1": 1, "away_score_period1": 0,
        }
        parsed = _extract_match(row, "Liverpool")
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed["team_home"])
        self.assertEqual(parsed["ht"], "1")
        self.assertEqual(parsed["ft"], "1")

    def test_extract_match_rejects_ambiguous_team_alias(self):
        row = {
            "home_team": "Alpha United", "away_team": "Beta City",
            "home_score_normaltime": 1, "away_score_normaltime": 1,
            "home_score_period1": 0, "away_score_period1": 0,
        }
        self.assertIsNone(_extract_match(row, "Gamma"))

    def test_candidate_selection_preserves_probability_and_fair_odds(self):
        analysis = [{
            "home": "A",
            "away": "B",
            "components": {
                "htft": {
                    "probabilities": {"1/1": 0.25},
                    "fair_odds": {"1/1": 4.0},
                    "risk": "MEDIUM",
                    "sample": {"home_history": 20, "away_history": 20, "h2h": 2},
                    "data_quality": 0.667,
                }
            }
        }]
        rows = select_htft_candidates(analysis, min_probability=0.20)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["market"], "HT/FT 1/1")
        self.assertEqual(rows[0]["fair_odds"], 4.0)


if __name__ == "__main__":
    unittest.main()
