import unittest

from zou.app.utils.flask import ParsedUserAgent, is_from_browser


class FlaskUtilsTestCase(unittest.TestCase):
    def test_is_from_browser_chrome(self):
        ua = ParsedUserAgent(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.assertTrue(is_from_browser(ua))

    def test_is_from_browser_firefox(self):
        ua = ParsedUserAgent(
            "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) "
            "Gecko/20100101 Firefox/121.0"
        )
        self.assertTrue(is_from_browser(ua))

    def test_is_from_browser_safari(self):
        ua = ParsedUserAgent(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) "
            "Version/17.2 Safari/605.1.15"
        )
        self.assertTrue(is_from_browser(ua))

    def test_is_not_from_browser_bot(self):
        ua = ParsedUserAgent("Googlebot/2.1")
        self.assertFalse(is_from_browser(ua))

    def test_is_not_from_browser_curl(self):
        ua = ParsedUserAgent("curl/7.68.0")
        self.assertFalse(is_from_browser(ua))

    def test_parsed_user_agent_properties(self):
        ua = ParsedUserAgent(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        self.assertEqual(ua.browser, "Chrome")
        self.assertEqual(ua.platform, "Linux")
        self.assertTrue(ua.version.startswith("120"))
