import datetime
from unittest.mock import patch

from tests.base import ApiDBTestCase

from zou.app.blueprints.export.csv.persons import PersonsCsvExport
from zou.app.exceptions import (
    PreviewAccountsUnavailableException,
    WrongParameterException,
)
from zou.app.models.person import Person
from zou.app.models.task import Task
from zou.app.services import (
    cascade_deletion_service,
    comments_service,
    notifications_service,
    persons_service,
    preview_accounts_service,
    projects_service,
    tasks_service,
)
from zou.app.utils import auth, date_helpers


class PreviewAccountsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.strategy = self.flask_app.config["AUTH_STRATEGY"]
        self.flask_app.config["AUTH_STRATEGY"] = "auth_local_classic"

    def tearDown(self):
        self.flask_app.config["AUTH_STRATEGY"] = self.strategy
        super().tearDown()

    def test_create_preview_account(self):
        account, password = (
            preview_accounts_service.create_or_reset_preview_account(
                self.project.id
            )
        )
        person = Person.get(account["id"])
        self.assertEqual(person.role.code, "client")
        self.assertEqual(person.preview_project_id, self.project.id)
        self.assertIn(person.id, [p.id for p in self.project.team])
        self.assertRegex(
            person.email, r"^preview-[0-9a-f]{12}@preview\.kitsu\.invalid$"
        )
        self.assertIsNone(person.preview_open_until)
        self.assertTrue(auth.check_password(person.password, password))

    def test_create_twice_resets_password_and_closes(self):
        service = preview_accounts_service
        first, password = service.create_or_reset_preview_account(
            self.project.id
        )
        service.set_preview_account_open(self.project.id, True)
        second, new_password = service.create_or_reset_preview_account(
            self.project.id
        )
        self.assertEqual(first["id"], second["id"])
        self.assertNotEqual(password, new_password)
        person = Person.get(second["id"])
        self.assertIsNone(person.preview_open_until)
        self.assertIsNone(person.preview_opened_at)
        self.assertTrue(auth.check_password(person.password, new_password))

    def test_create_when_unavailable(self):
        self.flask_app.config["AUTH_STRATEGY"] = "auth_remote_ldap"
        self.assertRaises(
            PreviewAccountsUnavailableException,
            preview_accounts_service.create_or_reset_preview_account,
            self.project.id,
        )

    def test_open_extend_close(self):
        service = preview_accounts_service
        service.create_or_reset_preview_account(self.project.id)
        service.set_preview_account_open(self.project.id, True)
        person = service.get_preview_account_raw(self.project.id)
        opened_at = person.preview_opened_at
        self.assertEqual(
            person.preview_open_until - opened_at,
            service.PREVIEW_OPEN_DURATION,
        )
        service.set_preview_account_open(self.project.id, True)
        person = service.get_preview_account_raw(self.project.id)
        self.assertEqual(person.preview_opened_at, opened_at)
        self.assertGreater(
            person.preview_open_until - opened_at,
            service.PREVIEW_OPEN_DURATION,
        )
        service.set_preview_account_open(self.project.id, False)
        person = service.get_preview_account_raw(self.project.id)
        self.assertIsNone(person.preview_opened_at)
        self.assertIsNone(person.preview_open_until)

    def test_is_preview_session_valid(self):
        service = preview_accounts_service
        service.create_or_reset_preview_account(self.project.id)
        person = service.get_preview_account_raw(self.project.id)
        self.assertFalse(service.is_preview_session_valid(person, None))
        service.set_preview_account_open(self.project.id, True)
        person = service.get_preview_account_raw(self.project.id)
        opened = person.preview_opened_at.replace(
            tzinfo=datetime.timezone.utc
        ).timestamp()
        self.assertTrue(service.is_preview_session_valid(person, opened))
        self.assertFalse(service.is_preview_session_valid(person, opened - 5))
        # JWT iat has whole-second precision
        person.preview_opened_at = person.preview_opened_at.replace(
            microsecond=700000
        )
        opened = person.preview_opened_at.replace(
            tzinfo=datetime.timezone.utc
        ).timestamp()
        self.assertTrue(service.is_preview_session_valid(person, int(opened)))
        self.assertFalse(
            service.is_preview_session_valid(person, int(opened) - 1)
        )
        person.preview_open_until = (
            date_helpers.get_utc_now_datetime() - datetime.timedelta(seconds=1)
        )
        self.assertFalse(service.is_preview_session_valid(person, opened))

    def test_preview_excluded_from_people_and_seats(self):
        count = persons_service.count_active_users()
        limit = persons_service.is_user_limit_reached()
        account, _ = preview_accounts_service.create_or_reset_preview_account(
            self.project.id
        )
        ids = [p["id"] for p in persons_service.get_persons()]
        self.assertNotIn(account["id"], ids)
        ids = [p["id"] for p in persons_service.get_active_persons()]
        self.assertNotIn(account["id"], ids)
        self.assertNotIn(
            account["email"],
            [p.email for p in PersonsCsvExport().build_query().all()],
        )
        self.assertEqual(persons_service.count_active_users(), count)
        self.assertEqual(persons_service.is_user_limit_reached(), limit)

    def test_add_preview_to_other_team_refused(self):
        account, _ = preview_accounts_service.create_or_reset_preview_account(
            self.project.id
        )
        other = self.generate_fixture_project("Other")
        self.assertRaises(
            WrongParameterException,
            projects_service.add_team_member,
            other.id,
            account["id"],
        )

    def test_remove_project_deletes_preview_account(self):
        account, _ = preview_accounts_service.create_or_reset_preview_account(
            self.project.id
        )
        cascade_deletion_service.remove_project(self.project.id)
        self.assertIsNone(Person.get(account["id"]))

    def test_playlist_ready_skips_preview(self):
        account, _ = preview_accounts_service.create_or_reset_preview_account(
            self.project.id
        )
        playlist = {
            "id": "00000000-0000-0000-0000-000000000000",
            "project_id": str(self.project.id),
        }
        with patch.object(
            persons_service,
            "get_current_user",
            return_value={"id": str(self.user["id"])},
        ):
            notifications_service.notify_clients_playlist_ready(playlist)
        from zou.app.models.notification import Notification

        self.assertEqual(
            Notification.query.filter_by(person_id=account["id"]).count(), 0
        )

    def test_preview_absent_from_persons_list(self):
        account, _ = preview_accounts_service.create_or_reset_preview_account(
            self.project.id
        )
        ids = [p["id"] for p in self.get("data/persons")]
        self.assertNotIn(account["id"], ids)
        client = self.generate_fixture_person(
            first_name="Cli",
            last_name="Ent",
            desktop_login="cli.ent",
            email="cli.ent@example.com",
        )
        client.update({"role": "client"})
        projects_service.add_team_member(self.project.id, client.id)
        persons_service.clear_person_cache()
        self.log_in(client.email)
        ids = [p["id"] for p in self.get("data/persons")]
        self.assertNotIn(account["id"], ids)

    def test_preview_not_mentionable(self):
        account, _ = preview_accounts_service.create_or_reset_preview_account(
            self.project.id
        )
        mentions = comments_service.get_comment_mentions(
            self.project.id, f"Hi @{account['full_name']}"
        )
        self.assertEqual(mentions, [])

    def test_preview_not_assignable(self):
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        account, _ = preview_accounts_service.create_or_reset_preview_account(
            self.project.id
        )
        with self.assertRaises(WrongParameterException):
            tasks_service.assign_task(self.task.id, account["id"])

    def test_preview_not_assignable_through_routes(self):
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        account, _ = preview_accounts_service.create_or_reset_preview_account(
            self.project.id
        )
        preview_id = account["id"]
        self.post(
            "data/tasks",
            {
                "name": "Other",
                "project_id": str(self.project.id),
                "task_type_id": str(self.task_type.id),
                "task_status_id": str(self.task_status.id),
                "entity_id": str(self.asset.id),
                "assignees": [preview_id],
            },
            400,
        )
        self.assertEqual(
            Task.query.filter(Task.assignees.any(id=preview_id)).count(), 0
        )
        self.assertEqual(Task.query.count(), 1)
        self.put(
            f"data/tasks/{self.task.id}", {"assignees": [preview_id]}, 400
        )
        self.put(
            f"actions/tasks/{self.task.id}/assign",
            {"person_id": preview_id},
            400,
        )
        self.put(
            f"actions/persons/{preview_id}/assign",
            {"task_ids": [str(self.task.id)]},
            400,
        )
        self.assertEqual(
            Task.query.filter(Task.assignees.any(id=preview_id)).count(), 0
        )
