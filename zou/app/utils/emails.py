import logging
import re
import smtplib
from email import charset as email_charset
from html.parser import HTMLParser
from io import StringIO

from flask_mail import Message

from zou.app import mail

logger = logging.getLogger(__name__)


# Force quoted-printable encoding for utf-8 message bodies, so that the
# Python email module wraps lines at 76 chars. Without this, long HTML
# lines (e.g. inline styles, long URLs) can go above the 998-char hard
# limit of RFC 5322, and SMTP servers reject the message with
# "Maximum line length exceeded (see RFC 5322)".
email_charset.add_charset(
    "utf-8",
    email_charset.QP,
    email_charset.QP,
    "utf-8",
)


def send_email(subject, html, recipient_email, body=None, locale=None):
    """
    If MAIL_ENABLED is set, send an email with the given subject and HTML
    to the given recipient. By default, the plain text body is the HTML
    without its tags. If locale is given (e.g. "en_US", "fr_FR"), set the
    Content-Language header, so that the client of the recipient can use
    the correct language. Log a send failure, never raise it.
    """
    from zou.app import app

    if body is None:
        body = strip_html_tags(html)
    if app.config["MAIL_DEBUG_BODY"]:
        logger.info(body)
    if app.config["MAIL_ENABLED"]:
        with app.app_context():
            try:
                mail_default_sender = app.config["MAIL_DEFAULT_SENDER"]
                extra_headers = {}
                if locale:
                    extra_headers["Content-Language"] = str(locale).replace(
                        "_", "-"
                    )
                message = Message(
                    sender=f"Kitsu Bot <{mail_default_sender}>",
                    body=body,
                    html=html,
                    subject=subject,
                    recipients=[recipient_email],
                    extra_headers=extra_headers,
                )
                mail.send(message)
            except Exception as exception:
                if is_recipient_refusal(exception):
                    # A dead address is a data problem, not a failure of
                    # the application: keep it out of the error level, so
                    # that it does not page anyone.
                    app.logger.warning(
                        f"Email to {recipient_email} refused by the SMTP "
                        f"server (subject: {subject}): {exception}"
                    )
                else:
                    # Log at error level, so that failures show in the
                    # production and RQ worker logs. The default Flask
                    # logger drops info messages: SMTP errors were not
                    # visible while RQ still showed the email job as a
                    # success.
                    app.logger.error(
                        f"Failed to send email to {recipient_email} "
                        f"(subject: {subject})",
                        exc_info=True,
                    )


def is_recipient_refusal(exception):
    """
    Tell whether the SMTP server permanently rejected the message because
    of its recipient (unknown user, dead domain, full mailbox).
    """
    if isinstance(exception, smtplib.SMTPRecipientsRefused):
        return True
    return (
        isinstance(exception, smtplib.SMTPResponseException)
        and 550 <= exception.smtp_code <= 554
    )


class HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = StringIO()
        self.in_link = False
        self.link_url = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.in_link = True
            for attr_name, attr_value in attrs:
                if attr_name == "href":
                    self.link_url = attr_value
                    break
        elif tag in ("p", "br", "div"):
            self.text.write("\n")

    def handle_endtag(self, tag):
        if tag == "a" and self.in_link:
            if self.link_url:
                self.text.write(f" ({self.link_url})")
            self.in_link = False
            self.link_url = ""
        elif tag in ("p", "div"):
            self.text.write("\n")

    def handle_data(self, data):
        self.text.write(data)

    def get_data(self):
        return self.text.getvalue()


def strip_html_tags(html):
    """
    Convert an HTML email to plain text. Keep the URLs of the links and a
    basic format with line breaks.
    """
    stripper = HTMLStripper()
    stripper.feed(html)
    text = stripper.get_data()
    # Reduce 3 or more consecutive newlines to 2.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
