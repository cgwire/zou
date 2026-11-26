import base64
import signal
import textwrap
import time

import nomad
import orjson as json
from nomad.api.exceptions import URLNotFoundNomadException
from rq import get_current_job

from zou.app.stores import config_store

# The RQ worker sends this signal to its running job when it must stop. A
# job that waits on Nomad gives the Nomad job to the next worker, and does
# not hold the shutdown until Nomad is done.
HANDOVER_SIGNAL = signal.SIGUSR1
NOMAD_JOB_ID_META_KEY = "nomad_job_id"

_handover_requested = False


class NomadJobHandedOver(BaseException):
    """
    A job that waits on Nomad raises this exception when its worker stops.
    The RQ job goes back to the queue and continues to watch the same Nomad
    job. It is a BaseException, so that the "except Exception" of the
    callers, which would record a failure, does not catch it.
    """


def request_handover(signum=None, frame=None):
    """
    Signal handler of the job process: the worker stops.
    """
    global _handover_requested
    _handover_requested = True


def is_handover_requested():
    """
    Tell whether the worker asked the job process to stop.
    """
    return _handover_requested


def get_resumed_nomad_job_id():
    """
    Return the ID of the Nomad job that the current RQ job watched before
    the handover. Return None for a job that runs for the first time or
    outside of RQ.
    """
    job = get_current_job()
    if job is None:
        return None
    return job.meta.get(NOMAD_JOB_ID_META_KEY)


def is_resumed():
    """
    Tell whether the current RQ job resumes a Nomad job after a handover.
    """
    return get_resumed_nomad_job_id() is not None


def _record_nomad_job_id(nomad_jobid):
    job = get_current_job()
    if job is not None:
        job.meta[NOMAD_JOB_ID_META_KEY] = nomad_jobid
        job.save_meta()


def run_job(app, config, nomad_job_name, params):
    """
    Dispatch a Nomad job and wait for it. After a handover, a resumed job
    watches the Nomad job that it dispatched before, and does not dispatch
    a new one. If the worker stops in the meantime, raise
    NomadJobHandedOver: the RQ job goes back to the queue with the ID of
    the Nomad job.
    """
    nomad_host = config_store.get_nomad_host()

    params.update(
        {
            k: v
            for k, v in config.__dict__.items()
            if k.startswith("FS_") and v is not None
        }
    )

    data = json.dumps(params)
    payload = base64.b64encode(data).decode("utf-8")
    ncli = nomad.Nomad(host=nomad_host, timeout=5)

    nomad_jobid = get_resumed_nomad_job_id()
    resumed = nomad_jobid is not None
    if not resumed:
        if is_handover_requested():
            raise NomadJobHandedOver()
        response = ncli.job.dispatch_job(nomad_job_name, payload=payload)
        nomad_jobid = response["DispatchedJobID"]
        _record_nomad_job_id(nomad_jobid)
    else:
        app.logger.info("Nomad job %r: watched again", nomad_jobid)

    while True:
        if is_handover_requested():
            app.logger.info("Nomad job %r: handed over", nomad_jobid)
            raise NomadJobHandedOver()
        try:
            summary = ncli.job.get_summary(nomad_jobid)
        except URLNotFoundNomadException:
            if not resumed:
                raise
            # Nomad removes the finished jobs after some time. If a job
            # resumes that late, it cannot know how the Nomad job ended.
            # The callers check the files that it had to produce.
            app.logger.warning(
                "Nomad job %r: no longer known by Nomad", nomad_jobid
            )
            return True
        task_group = list(summary["Summary"])[0]
        status = summary["Summary"][task_group]
        if status["Failed"] != 0 or status["Lost"] != 0:
            app.logger.error("Nomad job %r failed: %r", nomad_jobid, status)
            out, err = get_nomad_job_logs(ncli, nomad_jobid, nomad_job_name)
            out = textwrap.indent(out, "\t")
            err = textwrap.indent(err, "\t")
            raise Exception(
                f"Job {nomad_jobid} is 'Failed' or 'Lost':\n"
                f"Status: {status}\nerr:\n{err}\nout:\n{out}"
            )
        if status["Complete"] == 1:
            app.logger.info("Nomad job %r: complete", nomad_jobid)
            break
        # There is no timeout here, but Python RQ jobs have a timeout. Nomad
        # jobs also have a timeout.
        time.sleep(1)
    return True


def get_nomad_job_logs(ncli, nomad_jobid, nomad_job_name):
    """
    Return the stdout and stderr of the last allocation of the given Nomad
    job. If a task never started, stdout contains its event messages.
    """
    allocations = ncli.job.get_allocations(nomad_jobid)
    last = max(
        [(alloc["CreateIndex"], idx) for idx, alloc in enumerate(allocations)]
    )[1]
    alloc_id = allocations[last]["ID"]
    # If the task did not start, the logs are not available.
    task = allocations[last]["TaskStates"][nomad_job_name]
    if not task["StartedAt"]:
        out = "\n".join([x["DisplayMessage"] for x in task["Events"]])
        err = ""
    else:
        # plain=True: framed logs come as one JSON document per 64 KiB chunk.
        err = ncli.client.stream_logs.stream(
            alloc_id, nomad_job_name, "stderr", plain=True
        )
        out = ncli.client.stream_logs.stream(
            alloc_id, nomad_job_name, "stdout", plain=True
        )
    return out.rstrip(), err.rstrip()
