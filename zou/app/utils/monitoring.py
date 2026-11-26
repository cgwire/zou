import logging

from babel.core import UnknownLocaleError
from flask_fs.errors import FileNotFound
from flask_jwt_extended.exceptions import NoAuthorizationError
from jwt import ExpiredSignatureError
from werkzeug.exceptions import Forbidden, NotFound

from zou import __version__ as zou_version
from zou.app import config
from zou.app.exceptions import (
    ModelWithRelationsDeletionException,
    TwoFactorAuthenticationRequiredException,
    WrongIdFormatException,
    WrongParameterException,
    WrongTaskTypeForEntityException,
)
from zou.app.utils import permissions

logger = logging.getLogger(__name__)

# The RQ integration sends the raw job arguments, and the default job
# description repeats them: chat credentials, mail bodies and recipients.
# The chat settings can also be in the local variables of a frame.
SENTRY_SCRUBBED_KEYS = [
    "args",
    "chat_token_discord",
    "chat_token_slack",
    "chat_webhook_mattermost",
    "description",
    "kwargs",
    "ldap_password",
    "webhook",
]


if config.SENTRY_ENABLED:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.rq import RqIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber
    except ModuleNotFoundError:
        logger.warning("sentry_sdk module not found.")

if config.PROMETHEUS_METRICS_ENABLED:
    try:
        import prometheus_flask_exporter
        import prometheus_flask_exporter.multiprocess
    except ModuleNotFoundError:
        logger.warning("prometheus_flask_exporter not found.")


def init_monitoring(app):
    """
    Configure Sentry and the Prometheus metrics on the given app, each one
    only if the configuration enables it.
    """
    if config.SENTRY_ENABLED:
        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            integrations=[
                FlaskIntegration(),
                RqIntegration(),
                SqlalchemyIntegration(),
            ],
            traces_sample_rate=config.SENTRY_SR,
            event_scrubber=EventScrubber(
                denylist=[*DEFAULT_DENYLIST, *SENTRY_SCRUBBED_KEYS],
                recursive=True,
            ),
            ignore_errors=[
                NoAuthorizationError,
                NotFound,
                Forbidden,
                ExpiredSignatureError,
                FileNotFound,
                ModelWithRelationsDeletionException,
                TwoFactorAuthenticationRequiredException,
                UnknownLocaleError,
                WrongIdFormatException,
                WrongParameterException,
                WrongTaskTypeForEntityException,
            ],
        )

        if config.SENTRY_DEBUG_URL:

            @app.route(config.SENTRY_DEBUG_URL)
            def trigger_error():
                return 1 / 0

    if config.PROMETHEUS_METRICS_ENABLED:
        prometheus_kwargs = {
            "app": app,
            "defaults_prefix": "zou",
            "group_by": "url_rule",
        }
        try:
            metrics = prometheus_flask_exporter.multiprocess.GunicornPrometheusMetrics(
                **prometheus_kwargs
            )
        except ValueError:
            prometheus_kwargs["metrics_decorator"] = permissions.require_admin
            metrics = prometheus_flask_exporter.PrometheusMetrics(
                **prometheus_kwargs
            )
        metrics.info("zou_info", "Application info", version=zou_version)
        _register_inflight_gauge(app)


def _register_inflight_gauge(app):
    """
    Expose a gauge of the HTTP requests in progress for each URL rule.

    The ``zou_top`` dashboard uses it to show the endpoints that Zou serves
    at the moment. It uses ``multiprocess_mode='livesum'``, so that the
    values of concurrent gunicorn workers add up correctly.
    """
    from flask import request
    from prometheus_client import Gauge

    try:
        inflight = Gauge(
            "zou_http_request_inflight",
            "In-progress HTTP requests per URL rule",
            ["method", "path"],
            multiprocess_mode="livesum",
        )
    except ValueError:
        # If the gauge is already registered (e.g. reloader), do not add
        # the hooks again.
        return

    def _rule():
        try:
            if request.url_rule is not None:
                return request.url_rule.rule
        except RuntimeError:
            pass
        return request.path if request else "-"

    @app.before_request
    def _inflight_inc():
        try:
            inflight.labels(method=request.method, path=_rule()).inc()
        except Exception:
            pass

    @app.teardown_request
    def _inflight_dec(_exc):
        try:
            inflight.labels(method=request.method, path=_rule()).dec()
        except Exception:
            pass
