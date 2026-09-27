import unittest
from app.four_engine_fusion import fuse_market
from app.coupon_engine_v5 import build_candidates,build_coupon

class FourEngineTests(unittest.TestCase):
    def setUp(self):
        self.hf={"matches":8,"points_per_game":2.0,"goal_diff_per_game":.8,"goals_for_per_game":1.8,
                 "goals_against_per_game":1.0,"btts_rate":.65,"over25_rate":.70}
        self.af={"matches":8,"points_per_game":1.0,"goal_diff_per_game":-.4,"goals_for_per_game":1.1,
                 "goals_against_per_game":1.7,"btts_rate":.60,"over25_rate":.65}
        self.dc={"home_win":.68,"draw":.20,"away_win":.12,"btts_yes":.63,"btts_no":.37,"over_2_5":.66,"under_2_5":.34}
        self.fs={"btts_rate":.67,"over_05_rate":.92,"over_15_rate":.78,"over_25_rate":.68,"over_35_rate":.42,
                 "corners_avg":10.2}

    def test_fusion_probability_is_bounded(self):
        out=fuse_market("home_win",footystats=self.fs,home_form=self.hf,away_form=self.af,dixon_coles=self.dc)
        self.assertGreaterEqual(out["probability"],.01); self.assertLessEqual(out["probability"],.99)
        self.assertGreaterEqual(out["engine_count"],3)

    def test_goal_and_corner_markets(self):
        for market in ("over_1_5","over_2_5","over_95_corners"):
            out=fuse_market(market,footystats=self.fs,home_form=self.hf,away_form=self.af,dixon_coles=self.dc)
            self.assertGreater(out["engine_count"],0)
            self.assertGreaterEqual(out["probability"],.01)
            self.assertLessEqual(out["probability"],.99)

    def test_coupon_requires_value_and_quality(self):
        fixture={"fixture_id":"A|B|2026-09-27","home":"A","away":"B","league":"Test",
                 "odds":{"home_win":1.90,"btts_yes":1.90,"over_2_5":1.80},
                 "fusion":{
                   "home_win":{"probability":.68,"data_quality":.90,"agreement":4,"engine_count":4,"votes":[]},
                   "btts_yes":{"probability":.40,"data_quality":.90,"agreement":4,"engine_count":4,"votes":[]},
                   "over_2_5":{"probability":.65,"data_quality":.90,"agreement":4,"engine_count":4,"votes":[]}}}
        candidates=build_candidates([fixture])
        self.assertTrue(any(x["market"]=="home_win" for x in candidates))
        self.assertFalse(any(x["market"]=="btts_yes" for x in candidates))
        coupon=build_coupon(candidates)
        self.assertGreaterEqual(coupon["leg_count"],1)

if __name__=="__main__":
    unittest.main()
