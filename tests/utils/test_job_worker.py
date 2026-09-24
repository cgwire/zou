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
