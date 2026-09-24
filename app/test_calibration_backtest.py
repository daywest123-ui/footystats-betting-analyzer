import unittest

from app.calibration_backtest import (
    CalibrationPoint,
    brier_score,
    calibration_table,
    expected_calibration_error,
    log_loss,
    value_backtest,
)


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
        row = next(item for item in table if item["bucket"] == "80%-90%")
        self.assertAlmostEqual(row["observed_rate"], 0.5)
        self.assertAlmostEqual(row["absolute_gap"], 0.3)

    def test_expected_calibration_error(self):
        points = [CalibrationPoint(0.8, 1), CalibrationPoint(0.8, 0)]
        self.assertAlmostEqual(expected_calibration_error(points), 0.3)

    def test_empty_value_backtest_is_explicit(self):
        result = value_backtest([CalibrationPoint(0.40, 0, 1.20)])
        self.assertEqual(result["opportunities"], 0)
        self.assertIsNone(result["roi"])

    def test_value_backtest(self):
        points = [
            CalibrationPoint(0.60, 1, 2.0),
            CalibrationPoint(0.60, 0, 2.0),
            CalibrationPoint(0.40, 0, 2.0),
        ]
        result = value_backtest(points, 0.09, 0.19)
        self.assertEqual(result["opportunities"], 2)

    def test_value_backtest_uses_explicit_market_probability(self):
        # Raw 2.00 odds imply 50%, but de-vig market probability can be 48%.
        # The explicit market probability must drive the edge threshold.
        points = [CalibrationPoint(0.52, 1, 2.0, 0.48)]
        result = value_backtest(points, 0.03, 0.03)
        self.assertEqual(result["opportunities"], 1)

    def test_value_backtest_rejects_invalid_market_probability(self):
        points = [CalibrationPoint(0.80, 1, 2.0, 1.0)]
        result = value_backtest(points, 0.03, 0.03)
        self.assertEqual(result["opportunities"], 0)


if __name__ == "__main__":
    unittest.main()
