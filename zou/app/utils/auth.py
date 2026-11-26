import email_validator
import flask_bcrypt

from zou.app import config


class PasswordTooShortException(Exception):
    pass


class PasswordsNoMatchException(Exception):
    pass


class EmailNotValidException(Exception):
    pass


def encrypt_password(password):
    """
    Encrypt the given string password with the bcrypt algorithm.
    bcrypt uses only the first 72 bytes, so truncate the password to
    prevent a ValueError on newer bcrypt versions.
    """
    if isinstance(password, str):
        password = password.encode("utf-8")
    return flask_bcrypt.generate_password_hash(password[:72])


def check_password(password_hash, password):
    """
    Check a password against a bcrypt hash. Truncate the password as
    `encrypt_password` does, so that users with a password longer than 72
    bytes can still log in. On a password that is too long, bcrypt 5+
    raises ValueError and does not truncate it silently.
    """
    if isinstance(password, str):
        password = password.encode("utf-8")
    return flask_bcrypt.check_password_hash(password_hash, password[:72])


def validate_email(email, check_deliverability=None):
    """
    Return the normalized email. If an instance does not check
    deliverability, it also accepts a domain without a dot, such as
    "jdoe@studio".
    """
    if check_deliverability is None:
        check_deliverability = config.MAIL_CHECK_DELIVERABILITY
    try:
        return email_validator.validate_email(
            email,
            check_deliverability=check_deliverability,
            globally_deliverable=config.MAIL_CHECK_DELIVERABILITY,
        ).normalized
    except email_validator.EmailNotValidError as e:
        raise EmailNotValidException(str(e))


def validate_password(password, password_2=None):
    """
    Return True if the password is long enough and, if password_2 is
    given, equal to it. Else, raise PasswordTooShortException or
    PasswordsNoMatchException.
    """
    if len(password) < config.MIN_PASSWORD_LENGTH:
        raise PasswordTooShortException()
    if password_2 is not None and password != password_2:
        raise PasswordsNoMatchException()
    return True
