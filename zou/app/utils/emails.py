from flask_mail import Message

from zou.app import mail


def send_email(subject, body, recipient_email, html=None):
    """
    Send an email with given subject and body to given recipient.
    """
    if html is None:
        html = body
    message = Message(
        body=body,
        html=html,
        subject=subject,
        recipients=[recipient_email]
    )
    mail.send(message)
