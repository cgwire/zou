from tests.base import ApiDBTestCase

from zou.app.services import preview_accounts_service, projects_service


class PreviewAccountRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_user_manager()
        self.generate_fixture_user_supervisor()
        self.generate_fixture_user_cg_artist()
        self.generate_fixture_user_client()
        for user in (
            self.user_manager,
            self.user_supervisor,
            self.user_cg_artist,
            self.user_client,
        ):
            projects_service.add_team_member(self.project.id, user["id"])
        self.strategy = self.flask_app.config["AUTH_STRATEGY"]
        self.flask_app.config["AUTH_STRATEGY"] = "auth_local_classic"
        self.path = f"data/projects/{self.project.id}/preview-account"

    def tearDown(self):
        self.flask_app.config["AUTH_STRATEGY"] = self.strategy
        self.log_out()
        super().tearDown()

    def test_manager_crud_cycle(self):
        self.log_in_manager()
        self.assertIsNone(self.get(self.path))
        created = self.post(self.path, {}, 201)
        self.assertIn("password", created)
        account = self.get(self.path)
        self.assertEqual(account["id"], created["id"])
        self.assertNotIn("password", account)
        opened = self.put(self.path, {"is_open": True})
        self.assertIsNotNone(opened["preview_open_until"])
        self.delete(self.path, 204)
        self.assertIsNone(self.get(self.path))

    def test_refused_roles(self):
        for login in (
            self.log_in_supervisor,
            self.log_in_cg_artist,
            self.log_in_client,
        ):
            login()
            self.get(self.path, 403)
            self.post(self.path, {}, 403)
            self.put(self.path, {"is_open": True}, 403)
            self.delete(self.path, 403)

    def test_manager_of_other_project_refused(self):
        other = self.generate_fixture_person(
            first_name="Other", email="other.manager@example.com"
        )
        other.update({"role": "manager"})
        self.log_in("other.manager@example.com")
        self.get(self.path, 403)
        self.post(self.path, {}, 403)

    def test_post_when_ldap(self):
        self.log_in_manager()
        self.flask_app.config["AUTH_STRATEGY"] = "auth_remote_ldap"
        self.post(self.path, {}, 400)

    def test_config_flag(self):
        self.assertTrue(self.get("config")["preview_accounts_enabled"])

    def test_parity_with_real_client(self):
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_comment()
        self.generate_fixture_metadata_descriptor()
        self.generate_fixture_playlist("Client playlist", for_client=True)
        project_id = str(self.project.id)
        service = preview_accounts_service
        account, password = service.create_or_reset_preview_account(project_id)
        service.set_preview_account_open(project_id, True)
        paths = [
            f"data/projects/{project_id}/assets",
            f"data/playlists?project_id={project_id}",
            f"data/projects/{project_id}/metadata-descriptors",
            f"data/tasks/{self.task.id}/comments",
        ]

        def ids(path):
            return sorted(entry["id"] for entry in self.get(path))

        self.log_in_client()
        expected = {path: ids(path) for path in paths}
        self.assertTrue(expected[paths[0]] and expected[paths[1]])
        self.log_out()
        tokens = self.post(
            "auth/login",
            {"email": account["email"], "password": password},
            200,
        )
        self.base_headers["Authorization"] = f"Bearer {tokens['access_token']}"
        for path in paths:
            self.assertEqual(ids(path), expected[path], path)
