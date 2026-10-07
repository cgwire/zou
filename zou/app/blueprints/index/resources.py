from flasgger import swag_from
import datetime

import psutil
import redis
import requests
from flask import Response, abort
from flask_jwt_extended import jwt_required
from flask.views import MethodView

from zou import __version__
from zou.app import app, config
from zou.app.indexer import indexing
from zou.app.services import (
    persons_service,
    projects_service,
    stats_service,
)
from zou.app.stores import redis_client
from zou.app.utils import date_helpers, permissions


class IndexResource(MethodView):
    @swag_from("openapi/IndexResource_get.yml")
    def get(self):
        """
        Get API name and version
        """
        return {"api": config.APP_NAME, "version": __version__}


class BaseStatusResource(MethodView):

    def get_status(self):
        is_db_up = self._check_database()
        is_kv_up = self._check_key_value_store()
        is_es_up = self._check_event_stream()
        is_jq_up = self._check_job_queue()
        is_indexer_up = self._check_indexer()

        return (
            config.APP_NAME,
            __version__,
            is_db_up,
            is_kv_up,
            is_es_up,
            is_jq_up,
            is_indexer_up,
        )

    def _check_database(self):
        try:
            projects_service.get_or_create_project_status("Open")
            return True
        except Exception:
            app.logger.warning("Database probe failed.", exc_info=1)
            return False

    def _check_key_value_store(self):
        try:
            store = redis.StrictRedis(
                host=config.KEY_VALUE_STORE["host"],
                port=config.KEY_VALUE_STORE["port"],
                db=config.AUTH_TOKEN_BLACKLIST_KV_INDEX,
                password=config.KEY_VALUE_STORE["password"],
                decode_responses=True,
            )
            store.get("test")
            return True
        except redis.ConnectionError:
            return False

    def _check_event_stream(self):
        try:
            requests.get(
                f"http://{config.EVENT_STREAM_HOST}:{config.EVENT_STREAM_PORT}",
                timeout=5,
            )
            return True
        except Exception as exception:
            app.logger.warning(f"Event stream probe failed: {exception}")
            return False

    def _check_job_queue(self):
        # Count the workers in-process rather than shelling out to `rq info
        # --url redis://:<password>@...`: that put the Redis password in the
        # argv of a subprocess any local user can read in ps, and this probe
        # is reachable without authentication, so its timing was the
        # attacker's to choose.
        try:
            from rq import Worker

            connection = redis_client.get_client(
                config.KV_JOB_DB_INDEX, decode_responses=False
            )
            return Worker.count(connection=connection) > 0
        except Exception:
            app.logger.error("Job queue is not accessible", exc_info=1)
            return False

    def _check_indexer(self):
        try:
            client = indexing.get_client()
            client.get_indexes()
            return True
        except indexing.IndexerNotInitializedError:
            return False
        except Exception as exception:
            app.logger.warning(f"Indexer probe failed: {exception}")
            return False


class StatusResource(BaseStatusResource):
    @swag_from("openapi/StatusResource_get.yml")
    def get(self):
        """
        Get status of the API services
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
    @swag_from("openapi/StatusResourcesResource_get.yml")
    def get(self):
        """
        Get resource usage stats
        """
        return {
            "date": datetime.datetime.now().isoformat(),
            "cpu": self._get_cpu_stats(),
            "memory": self._get_memory_stats(),
            "jobs": self._get_job_stats(),
        }

    def _get_cpu_stats(self):
        loadavg = list(psutil.getloadavg())
        return {
            "percent": psutil.cpu_percent(interval=1, percpu=True),
            "loadavg": {
                "last 1 min": loadavg[0],
                "last 5 min": loadavg[1],
                "last 10 min": loadavg[2],
            },
        }

    def _get_memory_stats(self):
        memory = psutil.virtual_memory()
        return {
            "total": memory.total,
            "used": memory.used,
            "available": memory.available,
            "percent": memory.percent,
        }

    def _get_job_stats(self):
        nb_jobs = 0
        if config.ENABLE_JOB_QUEUE:
            from zou.app.stores.queue_store import job_queue

            registry = job_queue.started_job_registry
            nb_jobs = registry.count
        return {"running_jobs": nb_jobs}


class TxtStatusResource(BaseStatusResource):
    @swag_from("openapi/TxtStatusResource_get.yml")
    def get(self):
        """
        Get status of the API services as text
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

        text = f"""name: {api_name}
version: {version}
database-up: {"up" if is_db_up else "down"}
event-stream-up: {"up" if is_es_up else "down"}
key-value-store-up: {"up" if is_kv_up else "down"}
job-queue-up: {"up" if is_jq_up else "down"}
indexer-up: {"up" if is_indexer_up else "down"}
"""
        return Response(text, mimetype="text")


class InfluxStatusResource(BaseStatusResource):
    @swag_from("openapi/InfluxStatusResource_get.yml")
    def get(self):
        """
        Get status of the API services for InfluxDB
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


class StatsResource(MethodView):
    @jwt_required()
    @swag_from("openapi/StatsResource_get.yml")
    def get(self):
        """
        Get usage stats
        """
        if not permissions.has_admin_permissions():
            raise permissions.PermissionDenied
        return stats_service.get_main_stats()


class ConfigResource(MethodView):
    @swag_from("openapi/ConfigResource_get.yml")
    def get(self):
        """
        Get the configuration of the Kitsu instance
        """
        organisation = persons_service.get_organisation()
        conf = {
            "is_self_hosted": config.IS_SELF_HOSTED,
            "crisp_token": config.CRISP_TOKEN,
            "dark_theme_by_default": organisation["dark_theme_by_default"],
            "indexer_configured": config.INDEXER["key"] is not None,
            "saml_enabled": config.SAML_ENABLED,
            "saml_idp_name": config.SAML_IDP_NAME,
            "oidc_enabled": config.OIDC_ENABLED,
            "oidc_idp_name": config.OIDC_IDP_NAME,
            "default_locale": persons_service.get_default_locale(),
            "default_timezone": persons_service.get_default_timezone(),
            "enforce_2fa": config.ENFORCE_2FA,
            "movie_highdef_bitrate": config.MOVIE_HIGHDEF_BITRATE,
            "movie_lowdef_bitrate": config.MOVIE_LOWDEF_BITRATE,
        }
        if config.SENTRY_KITSU_ENABLED:
            conf["sentry"] = {
                "dsn": config.SENTRY_KITSU_DSN,
                "sampleRate": config.SENTRY_KITSU_SR,
            }
        return conf


class TestEventsResource(MethodView):
    @swag_from("openapi/TestEventsResource_get.yml")
    def get(self):
        """
        Generate a test event
        """
        from zou.app.utils import events

        events.emit("main:test", data={}, persist=False, project_id=None)
        return {"success": True}
