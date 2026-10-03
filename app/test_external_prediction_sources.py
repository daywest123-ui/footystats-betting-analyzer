import unittest

from app.external_prediction_sources import SOURCES, _contains_match, _parse_tip


class ExternalPredictionSourceTests(unittest.TestCase):
    def test_all_requested_sources_are_registered(self):
        self.assertEqual(
            {s.key for s in SOURCES},
            {"statsbet", "pitchdeep", "xgaura", "predictionsfooty", "kingsodds"},
        )

    def test_match_detection_requires_both_teams(self):
        self.assertTrue(_contains_match("Tochigi City vs Imabari", "Tochigi City", "Imabari"))
        self.assertFalse(_contains_match("Tochigi City vs another team", "Tochigi City", "Imabari"))

    def test_explicit_result_tip_is_parsed(self):
        tip, conf = _parse_tip("Tochigi City vs Imabari | Home Win | Confidence 72%", "Tochigi City", "Imabari")
        self.assertEqual(tip, "1")
        self.assertAlmostEqual(conf, 0.72)

    def test_unknown_text_is_not_converted_to_a_tip(self):
        tip, conf = _parse_tip("This is a match preview with no selection.", "A", "B")
        self.assertIsNone(tip)
        self.assertIsNone(conf)


if __name__ == "__main__":
    unittest.main()
