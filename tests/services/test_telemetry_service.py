import platform

from unittest import mock

from tests.base import ApiDBTestCase

from zou import __version__
from zou.app import config
from zou.app.models.person import Person
from zou.app.models.preview_file import PreviewFile
from zou.app.services import persons_service, telemetry_service


class TelemetryServiceTestCase(ApiDBTestCase):
    """
    The only thing this service does is leave the studio's network, so what
    matters is where it goes and what it carries: counts, and nothing that
    names anybody.
    """

    def send(self):
        """
        Run the one call this service makes and hand back the mock, so a
        case can read either the payload or the address it went to.
        """
        with mock.patch("requests.post") as post:
            telemetry_service.send_main_infos()
        self.assertEqual(post.call_count, 1)
        return post

    def test_send_main_infos_names_nobody(self):
        payload = self.send().call_args.kwargs["json"]

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

    def test_send_main_infos_says_which_studio_it_is(self):
        # The two fields that identify the sender, and the two versions the
        # community estimate is broken down by.
        organisation = persons_service.get_organisation()

        payload = self.send().call_args.kwargs["json"]

        self.assertEqual(payload["organisation_id"], organisation["id"])
        self.assertEqual(payload["organisation_name"], organisation["name"])
        self.assertEqual(payload["api_version"], __version__)
        self.assertEqual(payload["python_version"], platform.python_version())

    def test_send_main_infos_posts_to_the_configured_address(self):
        post = self.send()

        self.assertEqual(post.call_args.args, (config.TELEMETRY_URL,))
        # A studio behind a dead proxy must not hang on this.
        self.assertEqual(post.call_args.kwargs["timeout"], 30)

    def test_the_previews_are_counted_by_kind(self):
        # Three distinct counts, so a payload key wired to the wrong count
        # cannot pass.
        for extension, number in [("mp4", 1), ("png", 2), ("obj", 3)]:
            for _ in range(number):
                PreviewFile.create(name="main", extension=extension)

        payload = self.send().call_args.kwargs["json"]

        self.assertEqual(payload["nb_movie_previews"], 1)
        self.assertEqual(payload["nb_picture_previews"], 2)
        self.assertEqual(payload["nb_model_previews"], 3)

    def test_only_the_active_members_of_the_studio_are_counted(self):
        """
        The count is what the community size is estimated from: a guest
        account belongs to a client, and a disabled one to nobody.
        """
        # The admin the test case logs in as is the one that counts.
        self.assertEqual(
            self.send().call_args.kwargs["json"]["nb_active_users"], 1
        )
        Person.create(
            first_name="Gone",
            last_name="Away",
            email="gone@example.com",
            active=False,
        )
        Person.create(
            first_name="Guest",
            last_name="Client",
            email="guest@example.com",
            is_guest=True,
        )

        payload = self.send().call_args.kwargs["json"]

        self.assertEqual(payload["nb_active_users"], 1)
