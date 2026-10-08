import unittest

from app.open_source_intel import HTFT_OUTCOMES, _rates, _blend_htft


class TestHTFTMatrix(unittest.TestCase):
    def test_has_exactly_nine_outcomes(self):
        self.assertEqual(len(HTFT_OUTCOMES), 9)
        self.assertEqual(len(set(HTFT_OUTCOMES)), 9)
        self.assertNotIn("0/0", HTFT_OUTCOMES)

    def test_rates_sum_to_one_with_rounding_tolerance(self):
        rows = [
            {"ht":"1","ft":"1","h1":1,"a1":0,"second_half_goals":1},
            {"ht":"1","ft":"X","h1":1,"a1":0,"second_half_goals":0},
            {"ht":"X","ft":"2","h1":0,"a1":0,"second_half_goals":1},
        ]
        rates = _rates(rows)
        self.assertAlmostEqual(sum(rates["htft"].values()), 1.0, places=3)

    def test_blend_produces_fair_odds(self):
        home = {"htft":{"1/1":0.40}, "sample":10}
        away = {"htft":{"1/1":0.20}, "sample":10}
        h2h = {"htft":{"1/1":0.10}, "sample":5}
        rows = _blend_htft(home, away, h2h)
        top = next(row for row in rows if row["market"] == "HT/FT 1/1")
        self.assertAlmostEqual(top["model_probability"], 0.28, places=6)
        self.assertAlmostEqual(top["fair_odds"], 3.57, places=2)


if __name__ == "__main__":
    unittest.main()
