import email
import smtplib
import unittest
from unittest.mock import patch

from babel import Locale

from zou.app import app
from zou.app.utils import emails

# RFC 5322 section 2.1.1: hard limit of 998 characters per line
# (excluding the trailing CRLF).
RFC_5322_MAX_LINE_LENGTH = 998


def send_and_capture(subject, html, **kwargs):
    """
    Send an email with the SMTP layer patched and return the serialized
    bytes of the message given to it.
    """
    with patch.dict(app.config, {"MAIL_ENABLED": True}):
        with patch("zou.app.utils.emails.mail.send") as send:
            emails.send_email(subject, html, "recipient@example.com", **kwargs)
    with app.app_context():
        return send.call_args.args[0].as_bytes()


class EmailsLineLengthTestCase(unittest.TestCase):
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
        raw = send_and_capture("Subject", html)
        self._assert_lines_within_rfc5322(raw)

    def test_long_plain_body_is_wrapped(self):
        body = "word " * 500
        html = "<p>short</p>"
        raw = send_and_capture("Subject", html, body=body)
        self._assert_lines_within_rfc5322(raw)

    def test_unicode_html_is_wrapped(self):
        html = "<p>" + ("é" * 2000) + "</p>"
        raw = send_and_capture("Sujet avec accents é", html)
        self._assert_lines_within_rfc5322(raw)


class EmailsSendFailureTestCase(unittest.TestCase):
    def _send_with_failure(self, error):
        """
        Send an email while the SMTP layer raises given error and return
        the records logged at warning level or above.
        """
        with patch.dict(app.config, {"MAIL_ENABLED": True}):
            with patch("zou.app.utils.emails.mail.send", side_effect=error):
                with self.assertLogs(app.logger, level="WARNING") as logs:
                    emails.send_email(
                        "Subject", "<p>Hello</p>", "recipient@example.com"
                    )
        return logs.records

    def test_smtp_failure_is_logged_as_error(self):
        records = self._send_with_failure(Exception("SMTP down"))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelname, "ERROR")
        self.assertIn("recipient@example.com", records[0].getMessage())
        self.assertIsNotNone(records[0].exc_info)

    def test_refused_recipient_is_logged_as_warning(self):
        error = smtplib.SMTPRecipientsRefused(
            {"recipient@example.com": (550, b"User unknown")}
        )
        records = self._send_with_failure(error)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelname, "WARNING")
        self.assertIn("recipient@example.com", records[0].getMessage())

    def test_permanent_rejection_is_logged_as_warning(self):
        error = smtplib.SMTPDataError(550, b"Mailbox unavailable")
        records = self._send_with_failure(error)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelname, "WARNING")

    def test_temporary_smtp_error_is_logged_as_error(self):
        error = smtplib.SMTPDataError(451, b"Try again later")
        records = self._send_with_failure(error)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].levelname, "ERROR")


class EmailsContentLanguageTestCase(unittest.TestCase):
    def _sent_message(self, **kwargs):
        return email.message_from_bytes(
            send_and_capture("Subject", "<p>Hello</p>", **kwargs)
        )

    def test_the_locale_is_sent_as_content_language(self):
        message = self._sent_message(locale="fr_FR")
        self.assertEqual(message["Content-Language"], "fr-FR")

    def test_a_babel_locale_is_sent_as_content_language(self):
        message = self._sent_message(locale=Locale("fr", "FR"))
        self.assertEqual(message["Content-Language"], "fr-FR")

    def test_no_locale_sends_no_content_language(self):
        message = self._sent_message()
        self.assertIsNone(message["Content-Language"])
