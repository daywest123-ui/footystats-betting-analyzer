import unittest

from open_web_intelligence import google_news_rss


class PublicWebSmokeTest(unittest.TestCase):
    def test_public_rss_collector_returns_list(self):
        items = google_news_rss("football match prediction", "en", "US", 3)
        self.assertIsInstance(items, list)
        for item in items:
            self.assertIn("title", item)
            self.assertIn("url", item)


if __name__ == "__main__":
    unittest.main()
