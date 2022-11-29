import os

try:
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    from sentry_sdk.integrations.rq import RqIntegration
except ModuleNotFoundError:
    print("sentry_sdk is not installed")
from zou.app import config


def init_sentry():
    if config.SENTRY_DSN:

        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            integrations=[
                FlaskIntegration(),
                RqIntegration(),
            ],
            traces_sample_rate=config.SENTRY_SR,
        )
