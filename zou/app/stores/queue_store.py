import logging
import redis

from rq import Queue
from zou.app import config

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
