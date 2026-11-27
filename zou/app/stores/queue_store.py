import logging

import redis
from rq import Queue, Worker

from zou.app import config
from zou.app.stores import redis_client

logger = logging.getLogger(__name__)

queue_store = None
job_queue = None

if config.ENABLE_JOB_QUEUE:
    queue_store = redis.StrictRedis(
        host=config.KEY_VALUE_STORE["host"],
        port=config.KEY_VALUE_STORE["port"],
        db=config.KV_JOB_DB_INDEX,
        password=config.KEY_VALUE_STORE["password"],
        decode_responses=True,
    )
    try:
        queue_store.ping()
    except redis.ConnectionError:
        if config.DEBUG:
            # Dev convenience only: jobs enqueued on fakeredis are never
            # executed. In production a job queue without Redis means
            # silently losing every job, so we fail at startup instead.
            import fakeredis

            logger.warning(
                "Job queue Redis is unreachable, falling back to fakeredis: "
                "enqueued jobs will NOT run."
            )
            queue_store = fakeredis.FakeStrictRedis()
        else:
            raise
    job_queue = Queue(connection=queue_store)


def count_workers():
    """
    Return the number of rq workers that listen to the job queue database.
    """
    # Count the workers in-process rather than shelling out to `rq info
    # --url redis://:<password>@...`: that put the Redis password in the
    # argv of a subprocess any local user can read in ps, and the status
    # probe is reachable without authentication, so its timing was the
    # attacker's to choose.
    connection = redis_client.get_client(
        config.KV_JOB_DB_INDEX, decode_responses=False
    )
    return Worker.count(connection=connection)


def count_started_jobs():
    """
    Return the number of jobs that run now in the job queue.
    """
    return job_queue.started_job_registry.count
