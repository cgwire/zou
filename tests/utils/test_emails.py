from tests.base import ApiDBTestCase

from zou.app import app
from zou.app.utils import emails

# RFC 5322 section 2.1.1: hard limit of 998 characters per line
# (excluding the trailing CRLF).
RFC_5322_MAX_LINE_LENGTH = 998


class EmailsLineLengthTestCase(ApiDBTestCase):
    def _get_message_bytes(self, subject, html, body=None):
        """
        Build a Flask-Mail Message exactly like ``send_email`` does and
        return its serialized bytes (what would be sent over SMTP).
        """
        from flask_mail import Message

        if body is None:
            body = emails.strip_html_tags(html)
        with app.app_context():
            message = Message(
                sender="Kitsu Bot <bot@example.com>",
                body=body,
                html=html,
                subject=subject,
                recipients=["recipient@example.com"],
            )
            return message.as_bytes()

    def _assert_lines_within_rfc5322(self, raw_bytes):
        for index, line in enumerate(raw_bytes.split(b"\r\n")):
            self.assertLessEqual(
                len(line),
                RFC_5322_MAX_LINE_LENGTH,
                f"Line {index} exceeds RFC 5322 limit "
                f"({len(line)} > {RFC_5322_MAX_LINE_LENGTH}): "
                f"{line[:120]!r}...",
            )

    def test_long_html_line_is_wrapped(self):
        long_url = "https://example.com/" + ("a" * 2000)
        html = f'<p>Click here: <a href="{long_url}">link</a></p>'
        raw = self._get_message_bytes("Subject", html)
        self._assert_lines_within_rfc5322(raw)

    def test_long_plain_body_is_wrapped(self):
        body = "word " * 500
        html = "<p>short</p>"
        raw = self._get_message_bytes("Subject", html, body=body)
        self._assert_lines_within_rfc5322(raw)

    def test_html_without_line_breaks_is_wrapped(self):
        html = "<p>" + ("x" * 3000) + "</p>"
        raw = self._get_message_bytes("Subject", html)
        self._assert_lines_within_rfc5322(raw)

    def test_unicode_html_is_wrapped(self):
        html = "<p>" + ("é" * 2000) + "</p>"
        raw = self._get_message_bytes("Sujet avec accents é", html)
        self._assert_lines_within_rfc5322(raw)
