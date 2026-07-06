from tests.base import ApiTestCase

from zou.app import app


class MaxContentLengthTestCase(ApiTestCase):
    def test_limit_is_configured(self):
        self.assertIsNotNone(app.config["MAX_CONTENT_LENGTH"])

    def test_oversized_body_is_rejected(self):
        previous = app.config["MAX_CONTENT_LENGTH"]
        app.config["MAX_CONTENT_LENGTH"] = 1024
        try:
            response = self.app.post(
                "auth/login",
                data=b"x" * 2048,
                headers={"Content-type": "application/json"},
            )
            self.assertEqual(response.status_code, 413)
        finally:
            app.config["MAX_CONTENT_LENGTH"] = previous
