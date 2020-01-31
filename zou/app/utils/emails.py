from flask_mail import Message

from zou.app import mail, app


def send_email(subject, body, recipient_email, html=None):
    """
    Send an email with given subject and body to given recipient.
    """
    if html is None:
        html = body
    with app.app_context():
        message = Message(
            sender="Kitsu Bot <no-reply@cg-wire.com>",
            body=body,
            html=html,
            subject=subject,
            recipients=[recipient_email]
        )
        mail.send(message)
