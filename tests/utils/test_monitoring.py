import os
import unittest
from unittest import mock

import prometheus_client
import pytest
from flask import Flask

from zou.app.utils import monitoring

# Part of the optional "monitoring" extra.
prometheus_flask_exporter = pytest.importorskip("prometheus_flask_exporter")
import prometheus_flask_exporter.multiprocess  # noqa: E402


class MonitoringTestCase(unittest.TestCase):
    def test_init_monitoring_without_multiproc_dir(self):
        """
        Outside gunicorn (e.g. rq workers), PROMETHEUS_MULTIPROC_DIR is
        unset and the single-process fallback must not crash.
        """
        env = {
            key: value
            for key, value in os.environ.items()
            if key.lower() != "prometheus_multiproc_dir"
        }
        app = Flask(__name__)
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.multiple(
            monitoring.config,
            PROMETHEUS_METRICS_ENABLED=True,
            SENTRY_ENABLED=False,
        ), mock.patch.object(
            monitoring,
            "prometheus_flask_exporter",
            prometheus_flask_exporter,
            create=True,
        ), mock.patch.object(
            prometheus_client,
            "REGISTRY",
            prometheus_client.CollectorRegistry(),
        ):
            monitoring.init_monitoring(app)

        self.assertIn(
            "/metrics", [rule.rule for rule in app.url_map.iter_rules()]
        )

    def test_sentry_events_do_not_carry_job_arguments(self):
        # KITSU-API-531: a chat credential was readable in the rq-job extra.
        pytest.importorskip("sentry_sdk")
        from sentry_sdk.scrubber import DEFAULT_DENYLIST, EventScrubber
        from sentry_sdk.utils import AnnotatedValue

        sentry_sdk = mock.MagicMock()
        with mock.patch.multiple(
            monitoring.config,
            PROMETHEUS_METRICS_ENABLED=False,
            SENTRY_ENABLED=True,
            SENTRY_DEBUG_URL=None,
        ), mock.patch.multiple(
            monitoring,
            create=True,
            sentry_sdk=sentry_sdk,
            FlaskIntegration=mock.MagicMock(),
            RqIntegration=mock.MagicMock(),
            SqlalchemyIntegration=mock.MagicMock(),
            EventScrubber=EventScrubber,
            DEFAULT_DENYLIST=DEFAULT_DENYLIST,
        ):
            monitoring.init_monitoring(Flask(__name__))

        frame = {
            "vars": {
                "webhook": "secret-url",
                "organisation": {
                    "name": "Studio",
                    "chat_token_discord": "secret",
                    "chat_token_slack": "secret",
                    "chat_webhook_mattermost": "secret",
                },
            }
        }
        job = {
            "job_id": "job-1",
            "func": "zou.app.utils.chats.send_to_discord",
            "args": ["secret-token", "user", "comment"],
            "kwargs": {"locale": "en"},
            "description": "send_email('secret-body')",
        }
        event = {
            "extra": {"rq-job": job},
            "exception": {
                "values": [{"stacktrace": {"frames": [frame]}}],
            },
        }
        sentry_sdk.init.call_args.kwargs["event_scrubber"].scrub_event(event)

        self.assertEqual(job["job_id"], "job-1")
        self.assertEqual(job["func"], "zou.app.utils.chats.send_to_discord")
        self.assertEqual(frame["vars"]["organisation"]["name"], "Studio")
        for scrubbed in [
            job["args"],
            job["kwargs"],
            job["description"],
            frame["vars"]["webhook"],
            frame["vars"]["organisation"]["chat_token_discord"],
            frame["vars"]["organisation"]["chat_token_slack"],
            frame["vars"]["organisation"]["chat_webhook_mattermost"],
        ]:
            self.assertIsInstance(scrubbed, AnnotatedValue)
