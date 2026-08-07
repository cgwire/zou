from unittest.mock import patch
from babel import Locale

from tests.base import ApiDBTestCase

from zou.app.models.comment import Comment
from zou.app.models.person import Person
from zou.app.services import emails_service

MESSAGES = {
    "email_message": "Test message",
    "slack_message": "Test",
    "mattermost_message": {"message": "Test"},
    "discord_message": "Test",
}


class EmailsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_shot_suite()
        self.generate_assigned_task()

    def a_person(self, first_name, locale, **flags):
        """
        Someone to notify, with the channels they subscribe to.
        """
        return Person.create(
            first_name=first_name,
            last_name="Test",
            email=f"{first_name.lower()}@example.com",
            locale=Locale(locale),
            **{"notifications_enabled": True, **flags},
        )

    def send_and_read_the_email(self, person_id, **kwargs):
        """
        Send a notification and hand back the html body it mailed, or None
        when it mailed nothing.
        """
        with patch(
            "zou.app.services.emails_service.emails.send_email"
        ) as mock_send:
            emails_service.send_notification(
                person_id,
                "Test Subject",
                MESSAGES,
                title="Test Title",
                **kwargs,
            )
            if not mock_send.called:
                return None
            return mock_send.call_args[0][1]

    def test_get_task_descriptors(self):
        author, task_name, task_url = emails_service.get_task_descriptors(
            self.person.id, self.task.serialize()
        )
        self.assertEqual(
            task_name, "Cosmos Landromat / Props / Tree / Shaders"
        )
        self.assertEqual(
            task_url,
            f"https://localhost:8080/productions/{self.project.id}/assets/tasks/{self.task.id}",
        )
        self.generate_fixture_shot_task()
        author, task_name, task_url = emails_service.get_task_descriptors(
            self.person.id, self.shot_task.serialize()
        )
        self.assertEqual(
            task_name, "Cosmos Landromat / E01 / S01 / P01 / Animation"
        )
        self.assertEqual(
            task_url,
            f"https://localhost:8080/productions/{self.project.id}/shots/tasks/{self.shot_task.id}",
        )

    def test_send_notification_uses_the_locale_it_is_given(self):
        # An English speaker, written to in French because the caller asked:
        # the argument comes before the person's own locale.
        person = self.a_person("Jean", "en_US")

        html_body = self.send_and_read_the_email(
            str(person.id), locale="fr_FR"
        )

        self.assertIn("Cordialement", html_body)

    def test_send_notification_falls_back_on_the_person_locale(self):
        person = self.a_person("Juan", "fr_FR")

        html_body = self.send_and_read_the_email(str(person.id))

        self.assertIn("Cordialement", html_body)

    def test_send_notification_stays_quiet_when_nothing_is_enabled(self):
        person = self.a_person("Silent", "en_US", notifications_enabled=False)

        self.assertIsNone(self.send_and_read_the_email(str(person.id)))

    def test_send_notification_mails_anyway_when_forced(self):
        person = self.a_person("Forced", "en_US", notifications_enabled=False)

        html_body = self.send_and_read_the_email(
            str(person.id), force_email=True
        )

        self.assertIn("Best regards", html_body)

    def test_send_notification_reaches_the_chat_channels(self):
        """
        Each channel the person subscribes to gets its own message, and the
        ones they do not subscribe to are left alone.
        """
        person = self.a_person(
            "Chatty",
            "en_US",
            notifications_enabled=False,
            notifications_slack_enabled=True,
            notifications_slack_userid="U123",
        )

        with patch(
            "zou.app.services.emails_service.chats.send_to_slack"
        ) as to_slack, patch(
            "zou.app.services.emails_service.chats.send_to_discord"
        ) as to_discord:
            emails_service.send_notification(
                str(person.id), "Test Subject", MESSAGES, title="Test Title"
            )

        self.assertEqual(to_slack.call_args[0][1:], ("U123", "Test"))
        self.assertFalse(to_discord.called)

    def test_send_comment_notification_uses_locale(self):
        spanish_person = self.a_person("Maria", "es_ES")
        spanish_person_id = str(spanish_person.id)

        comment = Comment.create(
            object_id=self.task.id,
            person_id=self.person.id,
            text="Test comment",
            task_status_id=self.task.task_status_id,
            object_type="task",
        )

        with patch(
            "zou.app.services.emails_service.emails.send_email"
        ) as mock_send:
            emails_service.send_comment_notification(
                spanish_person_id,
                self.person.id,
                comment.serialize(),
                self.task.serialize(),
            )

            self.assertTrue(mock_send.called)
            call_args = mock_send.call_args
            html_body = call_args[0][1]
            self.assertIn("Saludos cordiales", html_body)

    def test_send_notification_falls_back_to_english(self):
        # Italian is not among the translations, so English stands.
        person = self.a_person("Mario", "it_IT")

        html_body = self.send_and_read_the_email(str(person.id))

        self.assertIn("Best regards", html_body)

    def test_build_messages_carries_the_production_name(self):
        messages = emails_service._build_messages(
            "email", "slack", "discord", self.project.serialize()
        )

        self.assertEqual(
            messages,
            {
                "email_message": "email",
                "slack_message": "slack",
                "mattermost_message": {
                    "message": "slack",
                    "project_name": self.project.name,
                },
                "discord_message": "discord",
            },
        )


class PlaylistMailTestCase(EmailsServiceTestCase):
    """
    The playlist mail is written in two passes: a fragment naming the
    episode, then the body it sits in. Both used to escape it.
    """

    def a_playlist(self, name="Sunday & Monday"):
        return {
            "id": "00000000-0000-0000-0000-000000000001",
            "project_id": str(self.project.id),
            "episode_id": str(self.episode.id),
            "name": name,
            "for_entity": "shot",
            "is_for_all": False,
            "shots": [],
        }

    def playlist_mail(self, playlist):
        with patch(
            "zou.app.services.emails_service.emails.send_email"
        ) as mock_send:
            emails_service.send_playlist_ready_notification(
                str(self.a_person("Jean", "en_US").id),
                str(self.user["id"]),
                playlist,
            )
            return mock_send.call_args[0][1]

    def test_an_ampersand_is_escaped_once_wherever_it_sits(self):
        """
        The episode name went through two translations and came out
        &amp;amp;, which the recipient reads as "Tom &amp; Jerry". The
        playlist name, interpolated once, was already right: the two are
        one sentence of one mail and have to agree.
        """
        self.episode.update({"name": "Tom & Jerry"})

        html = self.playlist_mail(self.a_playlist())

        self.assertIn("Tom &amp; Jerry", html)
        self.assertIn("Sunday &amp; Monday", html)
        self.assertNotIn("&amp;amp;", html)

    def test_the_invitation_message_is_still_escaped(self):
        """
        Its segment is concatenated straight into the body rather than
        handed to another template, so it is the one place a fragment must
        keep being escaped where it is built.
        """
        with patch(
            "zou.app.services.emails_service.emails.send_email"
        ) as mock_send:
            emails_service.send_share_invitation(
                "guest@example.com",
                {"full_name": "John Did"},
                {"name": "Playlist"},
                self.project.serialize(),
                "https://localhost:8080/share/token",
                message="<script>alert(1)</script>",
                locale="en_US",
            )
            html = mock_send.call_args[0][1]

        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
