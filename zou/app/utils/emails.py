import traceback
from io import StringIO
from html.parser import HTMLParser
from flask_mail import Message

from zou.app import mail, app


def send_email(subject, html, recipient_email, body=None):
    """
    Send an email with given subject and body to given recipient.
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

    def handle_data(self, d):
        self.text.write(d)

    def get_data(self):
        return self.text.getvalue()


def strip_html_tags(html):
    s = HTMLStripper()
    s.feed(html)
    return s.get_data()
