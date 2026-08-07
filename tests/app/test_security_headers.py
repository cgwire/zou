from tests.base import ApiTestCase


class SecurityHeadersTestCase(ApiTestCase):
    def test_security_headers_are_set(self):
        response = self.app.get("/")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "SAMEORIGIN")
        self.assertEqual(
            response.headers["Content-Security-Policy"],
            "frame-ancestors 'self'",
        )
        self.assertEqual(
            response.headers["Referrer-Policy"],
            "strict-origin-when-cross-origin",
        )
