import unittest

from app import odds_harvester_client as oh


class OddsHarvesterClientTests(unittest.TestCase):
    def setUp(self):
        oh._CACHE.clear()

    def test_extract_odds_oddsharvester_schema(self):
        record = {
            "1x2_market": [
                {"1": "2.10", "X": "3.40", "2": "3.70", "bookmaker_name": "Test"}
            ],
            "btts_market": [
                {"btts_yes": "1.72", "btts_no": "2.05", "bookmaker_name": "Test"}
            ],
            "over_under_2_5_market": [
                {"odds_over": "1.91", "odds_under": "1.89", "bookmaker_name": "Test"}
            ],
        }
        got = oh._extract_odds(record)
        self.assertEqual(got["home_win"], 2.10)
        self.assertEqual(got["draw"], 3.40)
        self.assertEqual(got["away_win"], 3.70)
        self.assertEqual(got["btts_yes"], 1.72)
        self.assertEqual(got["btts_no"], 2.05)
        self.assertEqual(got["over_2_5"], 1.91)
        self.assertEqual(got["under_2_5"], 1.89)

    def test_fixture_matching_uses_normalized_team_names(self):
        oh._CACHE["2026-09-24"] = [{
            "home_team": "Liverpool FC",
            "away_team": "Chelsea",
            "1x2_market": [
                {"1": "2.25", "X": "3.40", "2": "3.10"}
            ],
        }]
        got = oh.fixture_odds("Liverpool", "Chelsea", "2026-09-24")
        self.assertEqual(got["home_win"], 2.25)
        self.assertEqual(got["draw"], 3.40)
        self.assertEqual(got["away_win"], 3.10)

    def test_current_fixtures_are_read_from_cache(self):
        oh._CACHE["2026-09-24"] = [{
            "home_team": "Team A",
            "away_team": "Team B",
            "kickoff": "2026-09-24T19:00",
            "league": "Test League",
        }]
        rows = oh.current_fixtures("2026-09-24")
        self.assertEqual(rows[0]["home"], "Team A")
        self.assertEqual(rows[0]["away"], "Team B")
        self.assertFalse(rows[0]["finished"])


if __name__ == "__main__":
    unittest.main()
