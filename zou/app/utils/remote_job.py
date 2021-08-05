import nomad
import base64
import json
import textwrap
import time


def run_job(app, config, nomad_job_name, params):
    nomad_host = config.JOB_QUEUE_NOMAD_HOST

    params.update({"FS_BACKEND": config.FS_BACKEND})
    if config.FS_BACKEND == "s3":
        params.update(
            {
                "S3_ENDPOINT": config.FS_S3_ENDPOINT,
                "AWS_DEFAULT_REGION": config.FS_S3_REGION,
                "AWS_ACCESS_KEY_ID": config.FS_S3_ACCESS_KEY,
                "AWS_SECRET_ACCESS_KEY": config.FS_S3_SECRET_KEY,
            }
        )
    elif config.FS_BACKEND == "swift":
        params.update(
            {
                "OS_USERNAME": config.FS_SWIFT_USER,
                "OS_PASSWORD": config.FS_SWIFT_KEY,
                "OS_AUTH_URL": config.FS_SWIFT_AUTHURL,
                "OS_TENANT_NAME": config.FS_SWIFT_TENANT_NAME,
                "OS_REGION_NAME": config.FS_SWIFT_REGION_NAME,
            }
        )

    data = json.dumps(params).encode("utf-8")
    payload = base64.b64encode(data).decode("utf-8")
    ncli = nomad.Nomad(host=nomad_host, timeout=5)

    response = ncli.job.dispatch_job(nomad_job_name, payload=payload)

    nomad_jobid = response["DispatchedJobID"]

    while True:
        summary = ncli.job.get_summary(nomad_jobid)
        task_group = list(summary["Summary"])[0]
        status = summary["Summary"][task_group]
        if status["Failed"] != 0 or status["Lost"] != 0:
            app.logger.error("Nomad job %r failed: %r", nomad_jobid, status)
            out, err = get_nomad_job_logs(ncli, nomad_jobid, nomad_job_name)
            out = textwrap.indent(out, "\t")
            err = textwrap.indent(err, "\t")
            raise Exception(
                "Job %s is 'Failed' or 'Lost':\nStatus: "
                "%s\nerr:\n%s\nout:\n%s" % (nomad_jobid, status, err, out)
            )
            return False
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
