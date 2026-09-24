import nomad
import base64
import orjson as json
import signal
import textwrap
import time

from nomad.api.exceptions import URLNotFoundNomadException
from rq import get_current_job

from zou.app.stores import config_store

# Sent by the RQ worker to its running job when it is asked to stop: a job
# waiting on Nomad hands the Nomad job over to the next worker instead of
# holding the shutdown until Nomad is done.
HANDOVER_SIGNAL = signal.SIGUSR1
NOMAD_JOB_ID_META_KEY = "nomad_job_id"

_handover_requested = False


class NomadJobHandedOver(BaseException):
    """
    Raised in a job waiting on Nomad when its worker stops: the RQ job is
    queued again and resumes watching the same Nomad job. A BaseException,
    so that the "except Exception" of the callers, which would record a
    failure, lets it through.
    """


def request_handover(signum=None, frame=None):
    """
    Signal handler of the job process: the worker is stopping.
    """
    global _handover_requested
    _handover_requested = True


def is_handover_requested():
    return _handover_requested


def get_resumed_nomad_job_id():
    """
    The Nomad job the current RQ job watched before it was handed over,
    None for a job run for the first time or outside of RQ.
    """
    job = get_current_job()
    if job is None:
        return None
    return job.meta.get(NOMAD_JOB_ID_META_KEY)


def is_resumed():
    return get_resumed_nomad_job_id() is not None


def _record_nomad_job_id(nomad_jobid):
    job = get_current_job()
    if job is not None:
        job.meta[NOMAD_JOB_ID_META_KEY] = nomad_jobid
        job.save_meta()


def run_job(app, config, nomad_job_name, params):
    """
    Dispatch a Nomad job and wait for it. A job resumed after a handover
    watches the Nomad job it dispatched before instead of dispatching a
    new one. When the worker stops meanwhile, raise NomadJobHandedOver:
    the RQ job is queued again with the Nomad job id.
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
            # Nomad drops the finished jobs after a while: a job resumed
            # that late cannot tell how it ended. The callers check the
            # files it was to produce.
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
        # there isn't a timeout here but python rq jobs have a timeout. Nomad
        # jobs have a timeout too.
        time.sleep(1)
    return True


def get_nomad_job_logs(ncli, nomad_jobid, nomad_job_name):
    allocations = ncli.job.get_allocations(nomad_jobid)
    last = max(
        [(alloc["CreateIndex"], idx) for idx, alloc in enumerate(allocations)]
    )[1]
    alloc_id = allocations[last]["ID"]
    # logs aren't available when the task isn't started
    task = allocations[last]["TaskStates"][nomad_job_name]
    if not task["StartedAt"]:
        out = "\n".join([x["DisplayMessage"] for x in task["Events"]])
        err = ""
    else:
        err = ncli.client.stream_logs.stream(
            alloc_id, nomad_job_name, "stderr"
        )
        out = ncli.client.stream_logs.stream(
            alloc_id, nomad_job_name, "stdout"
        )
        if err:
            err = json.loads(err).get("Data", "")
            err = base64.b64decode(err).decode("utf-8")
        if out:
            out = json.loads(out).get("Data", "")
            out = base64.b64decode(out).decode("utf-8")
    return out.rstrip(), err.rstrip()
