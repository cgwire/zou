import flask_bcrypt
import email_validator

from werkzeug.exceptions import BadRequest
from zou.app import config


class PasswordTooShortException(BadRequest):
    description = "Password is too short."


class PasswordsNoMatchException(BadRequest):
    description = "Confirmation password doesn't match."


class EmailNotValidException(BadRequest):
    description = "Email is not valid."


def encrypt_password(password):
    """
    Encrypt given string password using bcrypt algorithm.
    """
    return flask_bcrypt.generate_password_hash(password)


def validate_email(email):
    try:
        return email_validator.validate_email(email)["email"]
    except email_validator.EmailNotValidError as e:
        raise EmailNotValidException(str(e))


def validate_password(password, password_2=None):
    if len(password) < config.MIN_PASSWORD_LENGTH:
        raise PasswordTooShortException()
    if password_2 is not None and password != password_2:
        raise PasswordsNoMatchException()
    return True
