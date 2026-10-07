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
