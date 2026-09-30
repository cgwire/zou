"""
RQ worker and job classes of Zou, set on the worker command line:

    rq worker --with-scheduler -w zou.app.utils.job_worker.ZouWorker \
        -c zou.job_settings

--with-scheduler is needed for the preview jobs queued again with a delay
after an object storage outage (Keystone down): only the scheduler moves
them back to the queue once the delay is over. Without it, those jobs
fail at once and mark their preview broken.

A stop request lets the running job end, as RQ does, except a job waiting
on Nomad: it is queued again, with the id of the Nomad job it watches, and
the next worker resumes the watch. The Nomad job keeps running meanwhile.
"""

import os
import signal

import redis
from rq import Retry, Worker
from rq.job import Job

from zou.app import config
from zou.app.utils import remote_job


def _make_scheduler_last_seen_gauge():
    """
    Timestamp of the last time a worker saw the RQ scheduler lock of a
    queue. "mostrecent" keeps the value of a worker that stopped: its
    age is what the alert watches.
    """
    if not config.PROMETHEUS_METRICS_ENABLED:
        return None
    try:
        from prometheus_client import Gauge

        return Gauge(
            "zou_rq_scheduler_last_seen_timestamp_seconds",
            "Last time an RQ worker saw the scheduler of a queue running",
            ["queue"],
            multiprocess_mode="mostrecent",
        )
    except (ImportError, ValueError):
        return None


SCHEDULER_LAST_SEEN = _make_scheduler_last_seen_gauge()


class ZouJob(Job):
    def _execute(self):
        """
        Run the job function. A job that hands its Nomad job over returns
        a Retry, which RQ turns into a requeue: same job id, arguments and
        meta, and no failure recorded. It lands at the back of the queue,
        the Nomad job runs on meanwhile.
        """
        try:
            return super()._execute()
        except remote_job.NomadJobHandedOver:
            return Retry(max=(self.number_of_retries or 0) + 1)


class ZouWorker(Worker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._main_pid = os.getpid()
        # The rq command line always passes a job class, rq's own by
        # default: set ours after it.
        self.job_class = ZouJob

    def setup_work_horse_signals(self):
        """
        In the job process: record a handover request instead of dying on
        it. Only a job waiting on Nomad acts on it.
        """
        super().setup_work_horse_signals()
        signal.signal(remote_job.HANDOVER_SIGNAL, remote_job.request_handover)

    def handle_warm_shutdown_request(self):
        """
        Tell the running job the worker is stopping. RQ itself waits for
        the job to end, and only sends it a signal on a cold shutdown.
        """
        super().handle_warm_shutdown_request()
        if self.horse_pid:
            try:
                os.kill(self.horse_pid, remote_job.HANDOVER_SIGNAL)
            except ProcessLookupError:
                pass

    def heartbeat(self, *args, **kwargs):
        """
        Called on every dequeue timeout while idle and every job
        monitoring interval while a job runs: record whether the
        scheduler is alive at the same pace.
        """
        super().heartbeat(*args, **kwargs)
        self.record_scheduler_seen()

    def record_scheduler_seen(self):
        """
        Record the time for each queue whose scheduler lock is held. Not
        from the job process: each fork would leave a metrics file of its
        own behind.
        """
        if SCHEDULER_LAST_SEEN is None or os.getpid() != self._main_pid:
            return
        for queue in self.queues:
            try:
                if queue.scheduler_pid is not None:
                    SCHEDULER_LAST_SEEN.labels(
                        queue=queue.name
                    ).set_to_current_time()
            except redis.RedisError:
                pass
