import datetime

from tests.base import ApiDBTestCase

from zou.app.models.person import Person
from zou.app.services import (
    auth_service,
    persons_service,
    preview_accounts_service,
    projects_service,
)
from zou.app.utils import date_helpers


class PreviewAccountAuthTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.strategy = self.flask_app.config["AUTH_STRATEGY"]
        self.flask_app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.generate_base_context()
        self.generate_assigned_task()
        self.generate_fixture_user_manager()
        projects_service.add_team_member(
            self.project.id, self.user_manager["id"]
        )
        self.account, self.password = (
            preview_accounts_service.create_or_reset_preview_account(
                self.project.id
            )
        )
        self.admin_headers = dict(self.base_headers)

    def tearDown(self):
        self.flask_app.config["AUTH_STRATEGY"] = self.strategy
        super().tearDown()

    def open_window(self):
        preview_accounts_service.set_preview_account_open(
            self.project.id, True
        )

    def preview_login(self, code=200):
        self.base_headers = {}
        self.post_headers = {"Content-type": "application/json"}
        tokens = self.post(
            "auth/login",
            {"email": self.account["email"], "password": self.password},
            code,
        )
        if code == 200:
            headers = {"Authorization": f"Bearer {tokens['access_token']}"}
            self.base_headers.update(headers)
            self.post_headers.update(headers)
        return tokens

    def read_project(self, code=200):
        return self.get(f"data/projects/{self.project.id}", code)

    def test_login_refused_when_closed(self):
        self.preview_login(401)

    def test_login_and_read_when_open(self):
        self.open_window()
        self.preview_login()
        self.read_project()

    def test_write_refused(self):
        self.open_window()
        self.preview_login()
        self.post(
            f"actions/tasks/{self.task.id}/comment",
            {"task_status_id": self.task_status.id, "comment": "c"},
            403,
        )
        self.put(
            f"data/persons/{self.account['id']}", {"first_name": "X"}, 403
        )

    def test_old_token_refused_after_reopen(self):
        self.open_window()
        self.preview_login()
        self.read_project()
        preview_accounts_service.set_preview_account_open(
            self.project.id, False
        )
        self.open_window()
        # JWT iat has a one second granularity: move the reopening out of
        # the login second instead of relying on timing.
        person = Person.get(self.account["id"])
        person.update(
            {
                "preview_opened_at": date_helpers.get_utc_now_datetime()
                + datetime.timedelta(seconds=5)
            }
        )
        persons_service.clear_person_cache()
        self.read_project(401)

    def test_expired_window_refused(self):
        self.open_window()
        self.preview_login()
        person = Person.get(self.account["id"])
        person.update(
            {
                "preview_open_until": date_helpers.get_utc_now_datetime()
                - datetime.timedelta(minutes=1)
            }
        )
        persons_service.clear_person_cache()
        self.read_project(401)

    def test_unavailable_strategy_refused(self):
        self.open_window()
        self.preview_login()
        self.flask_app.config["AUTH_STRATEGY"] = "auth_local_no_password"
        self.read_project(401)

    def test_2fa_exemption(self):
        preview = Person.get(self.account["id"]).serialize()
        self.assertTrue(
            auth_service.is_user_exempt_from_2fa(preview, self.flask_app)
        )
        self.assertFalse(
            auth_service.is_user_exempt_from_2fa(
                self.user_manager, self.flask_app
            )
        )

    def test_admin_cannot_update_preview_person(self):
        self.put(
            f"data/persons/{self.account['id']}", {"role": "manager"}, 403
        )
        self.assertEqual(Person.get(self.account["id"]).role.code, "client")
