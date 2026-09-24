"""
RQ worker and job classes of Zou, set on the worker command line:

    rq worker -w zou.app.utils.job_worker.ZouWorker -c zou.job_settings

A stop request lets the running job end, as RQ does, except a job waiting
on Nomad: it is queued again, with the id of the Nomad job it watches, and
the next worker resumes the watch. The Nomad job keeps running meanwhile.
"""

import os
import signal

from rq import Retry, Worker
from rq.job import Job

from zou.app.utils import remote_job


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
