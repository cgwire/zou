from flask_jwt_extended.exceptions import NoAuthorizationError
from jwt import ExpiredSignatureError
from werkzeug.exceptions import Forbidden, NotFound

from zou.app import config

if config.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.rq import RqIntegration
    except ModuleNotFoundError:
        print("Sentry_sdk module not found.")


def init_sentry():
    if config.SENTRY_DSN:
        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            integrations=[
                FlaskIntegration(),
                RqIntegration(),
            ],
            traces_sample_rate=config.SENTRY_SR,
            ignore_errors=[
                NoAuthorizationError,
                NotFound,
                Forbidden,
                ExpiredSignatureError,
            ],
        )
