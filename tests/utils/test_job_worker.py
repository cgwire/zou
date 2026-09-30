import os
import signal
import unittest

from unittest.mock import patch

import fakeredis

from rq import Queue, get_current_job
from rq.job import JobStatus

from zou.app.utils import remote_job
from zou.app.utils.job_worker import ZouJob, ZouWorker


def hand_over():
    job = get_current_job()
    job.meta[remote_job.NOMAD_JOB_ID_META_KEY] = "zou-tile/dispatch-1"
    job.save_meta()
    raise remote_job.NomadJobHandedOver()


def watch_nomad():
    nomad_job_id = remote_job.get_resumed_nomad_job_id()
    if nomad_job_id is not None:
        return nomad_job_id
    hand_over()


def fail():
    raise RuntimeError("boom")


class ZouJobTestCase(unittest.TestCase):
    """
    A job that hands its Nomad job over is queued again, with its meta,
    instead of failing. Run the way a job process runs it, without the
    fork.
    """

    def setUp(self):
        self.connection = fakeredis.FakeStrictRedis()
        self.queue = Queue(
            "test", connection=self.connection, job_class=ZouJob
        )
        self.worker = ZouWorker([self.queue], connection=self.connection)

    def perform_next(self):
        job = self.queue.dequeue_any(
            [self.queue], None, connection=self.connection, job_class=ZouJob
        )[0]
        self.worker.prepare_execution(job)
        self.worker.perform_job(job, self.queue)
        return ZouJob.fetch(job.id, connection=self.connection)

    def test_the_worker_runs_zou_jobs(self):
        self.assertIs(self.worker.job_class, ZouJob)

    def test_a_handed_over_job_is_queued_again_with_its_nomad_job(self):
        on_failure = patch.object(ZouJob, "execute_failure_callback")
        with on_failure as failure_callback:
            self.queue.enqueue(watch_nomad)
            job = self.perform_next()
        failure_callback.assert_not_called()
        self.assertEqual(job.get_status(), JobStatus.QUEUED)
        self.assertEqual(self.queue.job_ids, [job.id])
        self.assertEqual(
            job.meta[remote_job.NOMAD_JOB_ID_META_KEY], "zou-tile/dispatch-1"
        )

        job = self.perform_next()
        self.assertEqual(job.get_status(), JobStatus.FINISHED)
        self.assertEqual(job.return_value(), "zou-tile/dispatch-1")

    def test_a_job_handed_over_twice_is_queued_again(self):
        self.queue.enqueue(hand_over)
        self.perform_next()
        job = self.perform_next()
        self.assertEqual(job.get_status(), JobStatus.QUEUED)

    def test_other_failures_still_fail(self):
        self.queue.enqueue(fail)
        job = self.perform_next()
        self.assertEqual(job.get_status(), JobStatus.FAILED)


class ZouWorkerSignalsTestCase(unittest.TestCase):
    """
    On a stop request the worker tells its job process, which records it
    instead of dying.
    """

    def setUp(self):
        remote_job._handover_requested = False
        self.addCleanup(setattr, remote_job, "_handover_requested", False)
        for signum in [
            signal.SIGINT,
            signal.SIGTERM,
            remote_job.HANDOVER_SIGNAL,
        ]:
            self.addCleanup(signal.signal, signum, signal.getsignal(signum))
        self.worker = ZouWorker(
            [Queue("test", connection=fakeredis.FakeStrictRedis())],
            connection=fakeredis.FakeStrictRedis(),
        )

    def test_the_job_process_records_a_handover_request(self):
        self.worker.setup_work_horse_signals()
        os.kill(os.getpid(), remote_job.HANDOVER_SIGNAL)
        self.assertTrue(remote_job.is_handover_requested())

    def test_a_warm_shutdown_signals_the_running_job(self):
        self.worker._horse_pid = 4242
        with patch("zou.app.utils.job_worker.os.kill") as kill:
            self.worker.handle_warm_shutdown_request()
        kill.assert_called_once_with(4242, remote_job.HANDOVER_SIGNAL)

    def test_a_warm_shutdown_without_job_signals_nothing(self):
        with patch("zou.app.utils.job_worker.os.kill") as kill:
            self.worker.handle_warm_shutdown_request()
        kill.assert_not_called()


class SchedulerLastSeenTestCase(unittest.TestCase):
    """
    The worker records when it last saw the RQ scheduler lock of its
    queues, for an alert to fire when no scheduler runs any more.
    """

    def setUp(self):
        from prometheus_client import CollectorRegistry, Gauge

        from zou.app.utils import job_worker

        self.registry = CollectorRegistry()
        gauge = Gauge(
            "zou_rq_scheduler_last_seen_timestamp_seconds",
            "test",
            ["queue"],
            registry=self.registry,
        )
        patcher = patch.object(job_worker, "SCHEDULER_LAST_SEEN", gauge)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.connection = fakeredis.FakeStrictRedis()
        self.queue = Queue("test", connection=self.connection)
        self.worker = ZouWorker([self.queue], connection=self.connection)

    def last_seen(self):
        return self.registry.get_sample_value(
            "zou_rq_scheduler_last_seen_timestamp_seconds", {"queue": "test"}
        )

    def hold_scheduler_lock(self):
        from rq.scheduler import RQScheduler

        self.connection.set(RQScheduler.get_locking_key("test"), 1234)

    def test_heartbeat_records_the_scheduler(self):
        import time

        self.hold_scheduler_lock()
        before = time.time()
        self.worker.heartbeat()
        self.assertGreaterEqual(self.last_seen(), before)

    def test_nothing_recorded_without_scheduler(self):
        # The last value stays: the alert fires once it gets too old.
        self.worker.heartbeat()
        self.assertIsNone(self.last_seen())

    def test_the_job_process_records_nothing(self):
        # A fork per job would leave one metrics file per job behind.
        self.hold_scheduler_lock()
        with patch.object(os, "getpid", return_value=os.getpid() + 1):
            self.worker.heartbeat()
        self.assertIsNone(self.last_seen())

    def test_redis_failure_does_not_stop_the_worker(self):
        from unittest.mock import PropertyMock

        import redis

        with patch.object(
            Queue,
            "scheduler_pid",
            new_callable=PropertyMock,
            side_effect=redis.ConnectionError(),
        ):
            self.worker.record_scheduler_seen()
        self.assertIsNone(self.last_seen())
