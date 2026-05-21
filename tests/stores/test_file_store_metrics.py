import os
import unittest

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from zou.app import app
from zou.app.stores import file_store


def _make_metrics(registry):
    return {
        "_OPS": Counter(
            "zou_storage_operations_total_test",
            "ops",
            ["op", "bucket", "status"],
            registry=registry,
        ),
        "_BYTES": Counter(
            "zou_storage_bytes_total_test",
            "bytes",
            ["op", "bucket"],
            registry=registry,
        ),
        "_DURATION": Histogram(
            "zou_storage_operation_duration_seconds_test",
            "dur",
            ["op", "bucket"],
            buckets=(0.05, 0.1, 1, 10),
            registry=registry,
        ),
        "_INFLIGHT": Gauge(
            "zou_storage_operations_inflight_test",
            "inflight",
            ["op", "bucket"],
            registry=registry,
        ),
        "_ETAG_MISMATCH": Counter(
            "zou_storage_etag_mismatch_total_test",
            "etag",
            ["bucket"],
            registry=registry,
        ),
    }


class FileStoreMetricsTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        app.app_context().push()
        self.store = file_store
        self.store.clear()

        self.registry = CollectorRegistry()
        self.metrics = _make_metrics(self.registry)
        self._saved = {
            name: getattr(file_store, name)
            for name in ("_PROM_ENABLED", *self.metrics.keys())
        }
        file_store._PROM_ENABLED = True
        for name, metric in self.metrics.items():
            setattr(file_store, name, metric)

        self.preview_id = "63e453f1-9655-49ad-acba-ff7f27c49e9d"
        self.fixture = os.path.join(
            os.getcwd(), "tests", "fixtures", "thumbnails", "th01.png"
        )

    def tearDown(self):
        for name, value in self._saved.items():
            setattr(file_store, name, value)
        self.store.clear()
        super().tearDown()

    def _sample(self, metric_key, labels):
        metric = self.metrics[metric_key]
        for sample in metric.collect()[0].samples:
            if sample.labels == labels and sample.name.endswith("_total"):
                return sample.value
            if sample.labels == labels and metric_key == "_INFLIGHT":
                return sample.value
        return 0.0

    def _histogram_count(self, op, bucket):
        for sample in self.metrics["_DURATION"].collect()[0].samples:
            if sample.name.endswith("_count") and sample.labels == {
                "op": op,
                "bucket": bucket,
            }:
                return sample.value
        return 0.0

    def test_upload_records_success_and_bytes(self):
        size = os.path.getsize(self.fixture)
        file_store.add_picture("thumbnails", self.preview_id, self.fixture)

        self.assertEqual(
            self._sample(
                "_OPS",
                {"op": "upload", "bucket": "pictures", "status": "success"},
            ),
            1.0,
        )
        self.assertEqual(
            self._sample("_BYTES", {"op": "upload", "bucket": "pictures"}),
            float(size),
        )
        self.assertEqual(self._histogram_count("upload", "pictures"), 1.0)
        self.assertEqual(
            self._sample("_INFLIGHT", {"op": "upload", "bucket": "pictures"}),
            0.0,
        )

    def test_download_generator_records_bytes(self):
        file_store.add_picture("thumbnails", self.preview_id, self.fixture)
        size = os.path.getsize(self.fixture)

        gen = file_store.open_picture("thumbnails", self.preview_id)
        total = sum(len(chunk) for chunk in gen)

        self.assertEqual(total, size)
        self.assertEqual(
            self._sample(
                "_OPS",
                {
                    "op": "download",
                    "bucket": "pictures",
                    "status": "success",
                },
            ),
            1.0,
        )
        self.assertEqual(
            self._sample("_BYTES", {"op": "download", "bucket": "pictures"}),
            float(size),
        )

    def test_exists_and_delete_counted(self):
        file_store.add_picture("thumbnails", self.preview_id, self.fixture)
        self.assertTrue(
            file_store.exists_picture("thumbnails", self.preview_id)
        )
        file_store.remove_picture("thumbnails", self.preview_id)

        self.assertEqual(
            self._sample(
                "_OPS",
                {"op": "exists", "bucket": "pictures", "status": "success"},
            ),
            1.0,
        )
        self.assertEqual(
            self._sample(
                "_OPS",
                {"op": "delete", "bucket": "pictures", "status": "success"},
            ),
            1.0,
        )

    def test_error_path_increments_error_status(self):
        with self.assertRaises(Exception):
            with file_store._measure("upload", "pictures"):
                raise RuntimeError("boom")

        self.assertEqual(
            self._sample(
                "_OPS",
                {"op": "upload", "bucket": "pictures", "status": "error"},
            ),
            1.0,
        )
        self.assertEqual(
            self._sample("_ETAG_MISMATCH", {"bucket": "pictures"}),
            0.0,
        )

    def test_etag_mismatch_path_increments_etag_counter(self):
        with self.assertRaises(Exception):
            with file_store._measure("upload", "movies"):
                raise RuntimeError(
                    "ETag mismatch for foo in movies: local=x remote=y"
                )

        self.assertEqual(
            self._sample(
                "_OPS",
                {
                    "op": "upload",
                    "bucket": "movies",
                    "status": "etag_mismatch",
                },
            ),
            1.0,
        )
        self.assertEqual(
            self._sample("_ETAG_MISMATCH", {"bucket": "movies"}), 1.0
        )

    def test_etag_mismatch_via_exception_class(self):
        if file_store._ETagMismatchError is None:
            self.skipTest("flask-fs2 swift backend not installed")

        with self.assertRaises(Exception):
            with file_store._measure("upload", "files"):
                raise file_store._ETagMismatchError("unrelated message")

        self.assertEqual(
            self._sample("_ETAG_MISMATCH", {"bucket": "files"}), 1.0
        )

    def test_prom_disabled_is_noop(self):
        file_store._PROM_ENABLED = False
        with file_store._measure("upload", "pictures", byte_count=10):
            pass
        self.assertEqual(
            self._sample(
                "_OPS",
                {"op": "upload", "bucket": "pictures", "status": "success"},
            ),
            0.0,
        )
