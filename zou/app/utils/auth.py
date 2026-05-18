import flask_bcrypt
import email_validator

from zou.app import config


class PasswordTooShortException(Exception):
    pass


class PasswordsNoMatchException(Exception):
    pass


class EmailNotValidException(Exception):
    pass


def encrypt_password(password):
    """
    Encrypt given string password using bcrypt algorithm.
    bcrypt only uses the first 72 bytes, so truncate to avoid
    ValueError on newer bcrypt versions.
    """
    if isinstance(password, str):
        password = password.encode("utf-8")
    return flask_bcrypt.generate_password_hash(password[:72])


def check_password(password_hash, password):
    """
    Check a password against a bcrypt hash. Mirrors `encrypt_password`
    truncation so that users whose password exceeds 72 bytes can still
    log in (bcrypt 5+ raises ValueError on overlong input instead of
    silently truncating).
    """
    if isinstance(password, str):
        password = password.encode("utf-8")
    return flask_bcrypt.check_password_hash(password_hash, password[:72])


def validate_email(
    email, check_deliverability=config.MAIL_CHECK_DELIVERABILITY
):
    try:
        return email_validator.validate_email(
            email, check_deliverability=check_deliverability
        ).normalized
    except email_validator.EmailNotValidError as e:
        raise EmailNotValidException(str(e))


def validate_password(password, password_2=None):
    if len(password) < config.MIN_PASSWORD_LENGTH:
        raise PasswordTooShortException()
    if password_2 is not None and password != password_2:
        raise PasswordsNoMatchException()
    return True
