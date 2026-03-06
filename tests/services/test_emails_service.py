from unittest.mock import patch
from babel import Locale

from tests.base import ApiDBTestCase

from zou.app.services import emails_service, persons_service, templates_service
from zou.app.utils.email_i18n import get_email_translation


class EmailsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(EmailsServiceTestCase, self).setUp()
        self.generate_shot_suite()
        self.generate_assigned_task()

    def test_get_signature(self):
        signature = templates_service.get_signature()
        self.assertEqual(
            signature,
            """
<p>Best regards,</p>

<p>Kitsu Team</p>""",
        )

    def test_get_signature_with_locale(self):
        signature_fr = templates_service.get_signature(locale="fr_FR")
        self.assertIn("Cordialement", signature_fr)
        self.assertIn("Kitsu", signature_fr)

        signature_es = templates_service.get_signature(locale="es_ES")
        self.assertIn("Saludos cordiales", signature_es)

    def test_get_task_descriptors(self):
        (author, task_name, task_url) = emails_service.get_task_descriptors(
            self.person.id, self.task.serialize()
        )
        self.assertEqual(
            task_name, "Cosmos Landromat / Props / Tree / Shaders"
        )
        self.assertEqual(
            task_url,
            "https://localhost:8080/productions/%s/assets/tasks/%s"
            % (self.project.id, self.task.id),
        )
        self.generate_fixture_shot_task()
        (author, task_name, task_url) = emails_service.get_task_descriptors(
            self.person.id, self.shot_task.serialize()
        )
        self.assertEqual(
            task_name, "Cosmos Landromat / E01 / S01 / P01 / Animation"
        )
        self.assertEqual(
            task_url,
            "https://localhost:8080/productions/%s/shots/tasks/%s"
            % (self.project.id, self.shot_task.id),
        )

    def test_send_notification_uses_user_locale(self):
        from zou.app.models.person import Person

        french_person = Person.create(
            first_name="Jean",
            last_name="Dupont",
            email="jean.dupont@example.com",
            locale=Locale("fr_FR"),
            notifications_enabled=True,
        )
        french_person_id = str(french_person.id)

        with patch(
            "zou.app.services.emails_service.emails.send_email"
        ) as mock_send:
            messages = {
                "email_message": "Test message",
                "slack_message": "Test",
                "mattermost_message": {"message": "Test"},
                "discord_message": "Test",
            }
            emails_service.send_notification(
                french_person_id,
                "Test Subject",
                messages,
                title="Test Title",
                locale="fr_FR",
            )

            self.assertTrue(mock_send.called)
            call_args = mock_send.call_args
            html_body = call_args[0][1]
            self.assertIn("Cordialement", html_body)

    def test_send_comment_notification_uses_locale(self):
        from zou.app.models.person import Person
        from zou.app.models.comment import Comment

        spanish_person = Person.create(
            first_name="Maria",
            last_name="Garcia",
            email="maria.garcia@example.com",
            locale=Locale("es_ES"),
            notifications_enabled=True,
        )
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

    def test_send_notification_fallback_to_en_us(self):
        from zou.app.models.person import Person

        # Use a locale not in EMAIL_TRANSLATIONS (e.g. Italian) so we fall back to en_US
        italian_person = Person.create(
            first_name="Mario",
            last_name="Rossi",
            email="mario.rossi@example.com",
            locale=Locale("it_IT"),
            notifications_enabled=True,
        )
        italian_person_id = str(italian_person.id)

        with patch(
            "zou.app.services.emails_service.emails.send_email"
        ) as mock_send:
            messages = {
                "email_message": "Test message",
                "slack_message": "Test",
                "mattermost_message": {"message": "Test"},
                "discord_message": "Test",
            }
            emails_service.send_notification(
                italian_person_id,
                "Test Subject",
                messages,
                title="Test Title",
            )

            self.assertTrue(mock_send.called)
            call_args = mock_send.call_args
            html_body = call_args[0][1]
            self.assertIn("Best regards", html_body)
