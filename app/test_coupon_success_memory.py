import unittest
from app.coupon_success_memory import market_stats, success_bonus

class CouponSuccessMemoryTests(unittest.TestCase):
    def test_seed_contains_user_winning_selections(self):
        stats=market_stats()
        self.assertEqual(stats["home_win"]["samples"],3)
        self.assertEqual(stats["btts_yes"]["samples"],2)
        self.assertEqual(stats["under_2_5"]["samples"],3)

    def test_bonus_is_small_and_positive(self):
        self.assertGreater(success_bonus("home_win",2.49),0)
        self.assertLessEqual(success_bonus("home_win",2.49),3.75)

    def test_unknown_market_has_no_bonus(self):
        self.assertEqual(success_bonus("draw",3.0),0.0)

if __name__=="__main__":
    unittest.main()
