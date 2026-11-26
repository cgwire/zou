"""
RQ worker and job classes of Zou, set on the worker command line:

    rq worker --with-scheduler -w zou.app.utils.job_worker.ZouWorker \
        -c zou.job_settings

The preview jobs need --with-scheduler: after an object storage outage
(Keystone down), Zou queues them again with a delay. Only the scheduler
moves them back to the queue after the delay. Without it, these jobs
fail immediately and mark their preview as broken.

A stop request lets the running job end, as RQ does, except for a job
that waits on Nomad. Zou queues this job again, with the ID of the Nomad
job that it watches, and the next worker continues the watch. In the
meantime, the Nomad job continues to run.
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
    Return the gauge of the last time that a worker saw the RQ scheduler
    lock of a queue. "mostrecent" keeps the value of a worker that
    stopped: the alert watches the age of this value.
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
        Run the job function. If a job gives its Nomad job to another
        worker, it returns a Retry. RQ changes the Retry into a requeue:
        same job ID, arguments and meta, and no failure record. The job
        goes to the back of the queue, and the Nomad job continues to run.
        """
        try:
            return super()._execute()
        except remote_job.NomadJobHandedOver:
            return Retry(max=(self.number_of_retries or 0) + 1)


class ZouWorker(Worker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._main_pid = os.getpid()
        # The rq command line always gives a job class (by default, the
        # class of rq): set our class after it.
        self.job_class = ZouJob

    def setup_work_horse_signals(self):
        """
        In the job process: record a handover request, and do not stop the
        process. Only a job that waits on Nomad acts on this request.
        """
        super().setup_work_horse_signals()
        signal.signal(remote_job.HANDOVER_SIGNAL, remote_job.request_handover)

    def handle_warm_shutdown_request(self):
        """
        Tell the running job that the worker stops. RQ itself waits for
        the job to end, and sends it a signal only on a cold shutdown.
        """
        super().handle_warm_shutdown_request()
        if self.horse_pid:
            try:
                os.kill(self.horse_pid, remote_job.HANDOVER_SIGNAL)
            except ProcessLookupError:
                pass

    def heartbeat(self, *args, **kwargs):
        """
        RQ calls this on each dequeue timeout while the worker is idle,
        and on each job monitoring interval while a job runs. Record at
        the same pace whether the scheduler is alive.
        """
        super().heartbeat(*args, **kwargs)
        self.record_scheduler_seen()

    def record_scheduler_seen(self):
        """
        Record the time for each queue whose scheduler lock a worker
        holds. Do not do it from the job process: each fork would leave
        its own metrics file behind.
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
