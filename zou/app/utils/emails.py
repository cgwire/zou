import re
import traceback
from io import StringIO
from html.parser import HTMLParser
from flask_mail import Message

from zou.app import mail, app


def send_email(subject, html, recipient_email, body=None, locale=None):
    """
    Send an email with given subject and body to given recipient.
    If locale is provided (e.g. "en_US", "fr_FR"), the Content-Language
    header is set so the recipient's client can use the correct language.
    """
    if body is None:
        body = strip_html_tags(html)
    if app.config["MAIL_DEBUG_BODY"]:
        print(body)
    if app.config["MAIL_ENABLED"]:
        with app.app_context():
            try:
                mail_default_sender = app.config["MAIL_DEFAULT_SENDER"]
                message = Message(
                    sender="Kitsu Bot <%s>" % mail_default_sender,
                    body=body,
                    html=html,
                    subject=subject,
                    recipients=[recipient_email],
                )
                if locale:
                    # Set Content-Language so the recipient's client knows the language
                    try:
                        lang_tag = locale.replace("_", "-")
                        if hasattr(message, "msg"):
                            message.msg["Content-Language"] = lang_tag
                    except Exception:
                        pass
                mail.send(message)
            except Exception:
                app.logger.info("Exception when sending a mail notification:")
                app.logger.info(traceback.format_exc())


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
                self.text.write(" (%s)" % self.link_url)
            self.in_link = False
            self.link_url = ""
        elif tag in ("p", "div"):
            self.text.write("\n")

    def handle_data(self, d):
        self.text.write(d)

    def get_data(self):
        return self.text.getvalue()


def strip_html_tags(html):
    """
    Convert HTML email to plain text, preserving URLs from links
    and maintaining basic formatting with line breaks.
    """
    s = HTMLStripper()
    s.feed(html)
    text = s.get_data()
    # Clean up multiple consecutive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
