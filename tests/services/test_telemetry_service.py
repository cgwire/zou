from unittest import mock

from tests.base import ApiDBTestCase

from zou.app.services import telemetry_service


class TelemetryServiceTestCase(ApiDBTestCase):
    """
    The only thing this service does is leave the studio's network, so what
    matters is the shape of what it sends.
    """

    def setUp(self):
        super().setUp()

    def test_send_main_infos_sends_counts_and_no_personal_data(self):
        with mock.patch("requests.post") as post:
            telemetry_service.send_main_infos()

        self.assertEqual(post.call_count, 1)
        payload = post.call_args.kwargs["json"]

        self.assertEqual(
            sorted(payload),
            [
                "api_version",
                "nb_active_users",
                "nb_comments",
                "nb_model_previews",
                "nb_movie_previews",
                "nb_picture_previews",
                "organisation_id",
                "organisation_name",
                "python_version",
            ],
        )
        # Counts, never a name, an email or an id of a person.
        for key in [
            "nb_active_users",
            "nb_comments",
            "nb_model_previews",
            "nb_movie_previews",
            "nb_picture_previews",
        ]:
            self.assertIsInstance(payload[key], int)
        self.assertEqual(payload["nb_active_users"], 1)
