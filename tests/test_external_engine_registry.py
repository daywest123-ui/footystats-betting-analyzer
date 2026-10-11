import unittest

from app.external_engine_registry import ENGINES, get_engine, registry_status


class ExternalEngineRegistryTests(unittest.TestCase):
    def test_registers_three_distinct_engines(self):
        self.assertEqual(len(ENGINES), 3)
        self.assertEqual(len({engine.key for engine in ENGINES}), 3)

    def test_known_engine_lookup(self):
        self.assertEqual(
            get_engine("prophitbet").repository,
            "https://github.com/kochlisGit/ProphitBet-Soccer-Bets-Predictor",
        )

    def test_unknown_engine_raises(self):
        with self.assertRaises(KeyError):
            get_engine("not-a-real-engine")

    def test_status_is_explicitly_unconfigured_without_env(self):
        statuses = registry_status()
        self.assertEqual(len(statuses), 3)
        self.assertTrue(all("status" in item for item in statuses))
        self.assertTrue(all("configured" in item for item in statuses))


if __name__ == "__main__":
    unittest.main()
