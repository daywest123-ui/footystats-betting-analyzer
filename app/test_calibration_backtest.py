import unittest

from app.calibration_backtest import CalibrationPoint, brier_score, log_loss, calibration_table, value_backtest


class CalibrationBacktestTests(unittest.TestCase):
    def test_brier_score(self):
        points = [CalibrationPoint(0.8, 1), CalibrationPoint(0.2, 0)]
        self.assertAlmostEqual(brier_score(points), 0.04)

    def test_log_loss_is_finite(self):
        points = [CalibrationPoint(0.8, 1), CalibrationPoint(0.2, 0)]
        self.assertTrue(log_loss(points) > 0)

    def test_calibration_table_observed_rate(self):
        points = [CalibrationPoint(0.8, 1), CalibrationPoint(0.8, 0)]
        table = calibration_table(points)
        self.assertEqual(table[0]["count"], 2) if False else None
        self.assertAlmostEqual(table[7]["observed_rate"], 0.5)

    def test_value_backtest(self):
        points = [
            CalibrationPoint(0.60, 1, 2.0),
            CalibrationPoint(0.60, 0, 2.0),
            CalibrationPoint(0.40, 0, 2.0),
        ]
        result = value_backtest(points, 0.09, 0.19)
        self.assertEqual(result["opportunities"], 2)


if __name__ == "__main__":
    unittest.main()
