import subprocess

from unittest.mock import patch

from tests.base import ApiDBTestCase, ApiTestCase

from zou import __version__
from zou.app import app, config


class VersionTestCase(ApiTestCase):
    def test_version_route(self):
        data = self.get("/")
        self.assertEqual(
            data, {"api": app.config["APP_NAME"], "version": __version__}
        )

    def test_status_route(self):
        data = self.get("/status")
        self.assertIn("database-up", data)
        self.assertIn("event-stream-up", data)
        self.assertIn("key-value-store-up", data)

    def test_status_route_spawns_no_subprocess(self):
        # The job queue probe used to run `rq info --url
        # redis://:<password>@...`, which put the Redis password in an argv
        # any local user can read in ps — from a route reachable without
        # authentication, so the attacker chose when it appeared.
        original_popen = subprocess.Popen
        spawned = []

        def recording_popen(args, *rest, **kwargs):
            spawned.append(args)
            return original_popen(args, *rest, **kwargs)

        subprocess.Popen = recording_popen
        try:
            self.get("/status")
            self.app.get("/status.txt")
        finally:
            subprocess.Popen = original_popen

        self.assertEqual(spawned, [])


class StatsRouteTestCase(ApiDBTestCase):
    """
    The instance wide counters. They span every production, so only an admin
    reads them.
    """

    def test_stats_route(self):
        stats = self.get("/stats")
        for key in [
            "number_of_comments",
            "number_of_picture_previews",
            "number_of_video_previews",
            "number_of_model_previews",
        ]:
            self.assertIn(key, stats)

    def test_stats_route_is_admin_only(self):
        self.generate_fixture_user_manager()
        self.log_in_manager()
        self.get("/stats", 403)


class ConfigRouteTestCase(ApiDBTestCase):
    def test_config_route_gives_the_instance_movie_bitrates(self):
        """
        Kitsu shows them as the defaults of the video settings and caps
        the typed bitrates at the high definition one, as the API does.
        """
        with patch.object(config, "MOVIE_HIGHDEF_BITRATE", 40), patch.object(
            config, "MOVIE_LOWDEF_BITRATE", 8
        ):
            conf = self.get("config")
        self.assertEqual(conf["movie_highdef_bitrate"], 40)
        self.assertEqual(conf["movie_lowdef_bitrate"], 8)
