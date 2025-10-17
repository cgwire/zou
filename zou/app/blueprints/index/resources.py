import psutil
import redis
import requests
import datetime

from flask import Response, abort
from flask_restful import Resource
from zou import __version__

from zou.app import app, config
from zou.app.utils import permissions, shell, date_helpers
from zou.app.services import projects_service, stats_service, persons_service
from flask_jwt_extended import jwt_required
from zou.app.utils.redis import get_redis_url


class IndexResource(Resource):
    def get(self):
        """
        Get API name and version
        ---
        tags:
          - Index
        responses:
          '200':
            description: API name and version
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    api:
                      type: string
                      example: "Zou"
                    version:
                      type: string
                      example: "0.20.0"
        """
        return {"api": config.APP_NAME, "version": __version__}


class BaseStatusResource(Resource):
    def get_status(self):
        is_db_up = True
        try:
            projects_service.get_or_create_status("Open")
        except Exception:
            is_db_up = False

        is_kv_up = True
        try:
            store = redis.StrictRedis(
                host=config.KEY_VALUE_STORE["host"],
                port=config.KEY_VALUE_STORE["port"],
                db=config.AUTH_TOKEN_BLACKLIST_KV_INDEX,
                password=config.KEY_VALUE_STORE["password"],
                decode_responses=True,
            )
            store.get("test")
        except redis.ConnectionError:
            is_kv_up = False

        is_es_up = True
        try:
            requests.get(
                f"http://{config.EVENT_STREAM_HOST}:{config.EVENT_STREAM_PORT}"
            )
        except Exception:
            is_es_up = False

        is_jq_up = True
        try:
            args = [
                "rq",
                "info",
                "--url",
                get_redis_url(config.KV_JOB_DB_INDEX),
            ]
            out = shell.run_command(args)
            is_jq_up = b"0 workers" not in out
        except Exception:
            app.logger.error("Job queue is not accessible", exc_info=1)
            is_jq_up = False

        is_indexer_up = True
        try:
            requests.get(
                f"{config.INDEXER['protocol']}://{config.INDEXER['host']}:{config.INDEXER['port']}"
            )
        except Exception:
            is_indexer_up = False

        version = __version__

        return (
            config.APP_NAME,
            version,
            is_db_up,
            is_kv_up,
            is_es_up,
            is_jq_up,
            is_indexer_up,
        )


class StatusResource(BaseStatusResource):
    def get(self):
        """
        Get status of the API services
         ---
         description: Get status of the database, key value store, event stream, job queue, indexer
         tags:
           - Index
         responses:
           '200':
             description: Status of the API services
             content:
               application/json:
                 schema:
                   type: object
                   properties:
                     name:
                       type: string
                       example: "Zou"
                     version:
                       type: string
                       example: "0.20.0"
                     database-up:
                       type: boolean
                       example: true
                     key-value-store-up:
                       type: boolean
                       example: true
                     event-stream-up:
                       type: boolean
                       example: true
                     job-queue-up:
                       type: boolean
                       example: true
                     indexer-up:
                       type: boolean
                       example: true
        """
        (
            api_name,
            version,
            is_db_up,
            is_kv_up,
            is_es_up,
            is_jq_up,
            is_indexer_up,
        ) = self.get_status()

        return {
            "name": api_name,
            "version": version,
            "database-up": is_db_up,
            "key-value-store-up": is_kv_up,
            "event-stream-up": is_es_up,
            "job-queue-up": is_jq_up,
            "indexer-up": is_indexer_up,
        }


class StatusResourcesResource(BaseStatusResource):
    def get(self):
        """
        Get resource usage stats
        ---
        description: Get CPU usage for each core, memory repartition and number of jobs in the job queue.
        tags:
          - Index
        responses:
          '200':
            description: CPU, memory and jobs stats
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    date:
                      type: string
                      format: date-time
                      example: "2023-12-07T10:30:00.000Z"
                    cpu:
                      type: object
                      properties:
                        percent:
                          type: array
                          items:
                            type: number
                          example: [25.5, 30.2, 28.1]
                        loadavg:
                          type: object
                          properties:
                            "last 1 min":
                              type: number
                              example: 0.75
                            "last 5 min":
                              type: number
                              example: 0.82
                            "last 10 min":
                              type: number
                              example: 0.78
                    memory:
                      type: object
                      properties:
                        total:
                          type: integer
                          example: 8589934592
                        used:
                          type: integer
                          example: 4294967296
                        available:
                          type: integer
                          example: 4294967296
                        percent:
                          type: number
                          example: 50.0
                    jobs:
                      type: object
                      properties:
                        running_jobs:
                          type: integer
                          example: 3
        """
        loadavg = list(psutil.getloadavg())

        cpu_stats = {
            "percent": psutil.cpu_percent(interval=1, percpu=True),
            "loadavg": {
                "last 1 min": loadavg[0],
                "last 5 min": loadavg[1],
                "last 10 min": loadavg[2],
            },
        }

        memory_stats = {
            "total": psutil.virtual_memory().total,
            "used": psutil.virtual_memory().used,
            "available": psutil.virtual_memory().available,
            "percent": psutil.virtual_memory().percent,
        }

        nb_jobs = 0
        if config.ENABLE_JOB_QUEUE:
            from zou.app.stores.queue_store import job_queue

            registry = job_queue.started_job_registry
            nb_jobs = registry.count
        job_stats = {
            "running_jobs": nb_jobs,
        }

        return {
            "date": datetime.datetime.now().isoformat(),
            "cpu": cpu_stats,
            "memory": memory_stats,
            "jobs": job_stats,
        }


class TxtStatusResource(BaseStatusResource):
    def get(self):
        """
        Get status of the API services as text
        ---
        description: Get status of the database, key value store, event stream, job queue, the indexer as a text.
        tags:
          - Index
        responses:
          '200':
            description: API name, version and status as txt
            content:
              text/plain:
                schema:
                  type: string
                  example: |
                    name: Zou
                    version: 0.20.0
                    database-up: up
                    event-stream-up: up
                    key-value-store-up: up
                    job-queue-up: up
                    indexer-up: up
        """
        (
            api_name,
            version,
            is_db_up,
            is_kv_up,
            is_es_up,
            is_jq_up,
            is_indexer_up,
        ) = self.get_status()

        text = """name: %s
version: %s
database-up: %s
event-stream-up: %s
key-value-store-up: %s
job-queue-up: %s
indexer-up: %s
""" % (
            api_name,
            version,
            "up" if is_db_up else "down",
            "up" if is_kv_up else "down",
            "up" if is_es_up else "down",
            "up" if is_jq_up else "down",
            "up" if is_indexer_up else "down",
        )
        return Response(text, mimetype="text")


class InfluxStatusResource(BaseStatusResource):
    def get(self):
        """
        Get status of the API services for InfluxDB
        ---
        description: Get status of the database, key value store, event stream, job queue, indexer as a JSON object.
        tags:
          - Index
        responses:
          '200':
            description: Status of database, key value, event stream, job queue and time
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    database-up:
                      type: integer
                      example: 1
                    key-value-store-up:
                      type: integer
                      example: 1
                    event-stream-up:
                      type: integer
                      example: 1
                    job-queue-up:
                      type: integer
                      example: 1
                    indexer-up:
                      type: integer
                      example: 1
                    time:
                      type: number
                      format: float
                      example: 1701948600.123
        """
        (
            _,
            _,
            is_db_up,
            is_kv_up,
            is_es_up,
            is_jq_up,
            is_indexer_up,
        ) = self.get_status()

        return {
            "database-up": int(is_db_up),
            "key-value-store-up": int(is_kv_up),
            "event-stream-up": int(is_es_up),
            "job-queue-up": int(is_jq_up),
            "indexer-up": int(is_indexer_up),
            "time": datetime.datetime.timestamp(
                date_helpers.get_utc_now_datetime()
            ),
        }


class StatsResource(Resource):
    @jwt_required()
    def get(self):
        """
        Get usage stats
        ---
        description: Get the amount of projects, assets, shots, tasks, and persons.
        tags:
          - Index
        responses:
          '200':
            description: Main stats
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    projects:
                      type: integer
                      example: 15
                    assets:
                      type: integer
                      example: 1250
                    shots:
                      type: integer
                      example: 890
                    tasks:
                      type: integer
                      example: 5670
                    persons:
                      type: integer
                      example: 45
        """
        if not permissions.has_admin_permissions():
            abort(403)
        return stats_service.get_main_stats()


class ConfigResource(Resource):
    def get(self):
        """
        Get the configuration of the Kitsu instance
        ---
        description: The configuration includes self-hosted status, Crisp token, indexer configuration, SAML status, and dark theme status.
        tags:
          - Index
        responses:
          '200':
            description: Configuration object
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    is_self_hosted:
                      type: boolean
                      example: true
                    crisp_token:
                      type: string
                      example: "abc123def456"
                    dark_theme_by_default:
                      type: boolean
                      example: false
                    indexer_configured:
                      type: boolean
                      example: true
                    saml_enabled:
                      type: boolean
                      example: false
                    saml_idp_name:
                      type: string
                      example: "My Company SSO"
                    default_locale:
                      type: string
                      example: "en_US"
                    default_timezone:
                      type: string
                      example: "UTC"
                    sentry:
                      type: object
                      properties:
                        dsn:
                          type: string
                          example: "https://example@sentry.io/123456"
                        sampleRate:
                          type: number
                          example: 0.1
        """
        organisation = persons_service.get_organisation()
        conf = {
            "is_self_hosted": config.IS_SELF_HOSTED,
            "crisp_token": config.CRISP_TOKEN,
            "dark_theme_by_default": organisation["dark_theme_by_default"],
            "indexer_configured": config.INDEXER["key"] is not None,
            "saml_enabled": config.SAML_ENABLED,
            "saml_idp_name": config.SAML_IDP_NAME,
            "default_locale": config.DEFAULT_LOCALE,
            "default_timezone": config.DEFAULT_TIMEZONE,
        }
        if config.SENTRY_KITSU_ENABLED:
            conf["sentry"] = {
                "dsn": config.SENTRY_KITSU_DSN,
                "sampleRate": config.SENTRY_KITSU_SR,
            }
        return conf


class TestEventsResource(Resource):
    def get(self):
        """
        Generate a test event
        ---
        description: Generate a `main:test` event to test the event stream with the Python client or similar.
        tags:
          - Index
        responses:
          '200':
            description: Success flag
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    success:
                      type: boolean
                      example: true
        """
        from zou.app.utils import events

        events.emit("main:test", data={}, persist=False, project_id=None)
        return {"success": True}
