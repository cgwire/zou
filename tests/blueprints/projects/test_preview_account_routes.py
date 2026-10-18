from tests.base import ApiDBTestCase

from zou.app.models.event import ApiEvent
from zou.app.models.person import Person
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
        from zou.app.models.metadata_descriptor import MetadataDescriptor
        from zou.app.services import comments_service

        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_task_status()
        project_id = str(self.project.id)
        visible_playlist = self.generate_fixture_playlist(
            "Client playlist", for_client=True
        )
        hidden_playlist = self.generate_fixture_playlist(
            "Internal playlist", for_client=False
        )
        descriptors = {}
        for name, for_client in (("visible", True), ("hidden", False)):
            descriptors[name] = str(
                MetadataDescriptor.create(
                    project_id=self.project.id,
                    name=name,
                    data_type="string",
                    field_name=name,
                    entity_type="Asset",
                    for_client=for_client,
                ).id
            )
        comments = {}
        for name, for_client in (("visible", True), ("hidden", False)):
            comments[name] = comments_service.create_comment(
                self.user_manager["id"],
                str(self.task.id),
                str(self.task_status.id),
                name,
                [],
                {},
                "",
                for_client=for_client,
            )["id"]
        service = preview_accounts_service
        account, password = service.create_or_reset_preview_account(project_id)
        service.set_preview_account_open(project_id, True)
        paths = [
            f"data/projects/{project_id}/assets",
            f"data/playlists?project_id={project_id}",
            f"data/projects/{project_id}/metadata-descriptors",
            f"data/tasks/{self.task.id}/comments",
        ]
        hidden = {
            paths[1]: str(hidden_playlist["id"]),
            paths[2]: descriptors["hidden"],
            paths[3]: comments["hidden"],
        }

        def ids(path):
            return sorted(entry["id"] for entry in self.get(path))

        self.log_in_client()
        expected = {path: ids(path) for path in paths}
        self.log_out()
        for path in paths:
            self.assertTrue(expected[path], path)
        self.assertIn(str(visible_playlist["id"]), expected[paths[1]])
        self.assertIn(descriptors["visible"], expected[paths[2]])
        self.assertIn(comments["visible"], expected[paths[3]])
        tokens = self.post(
            "auth/login",
            {"email": account["email"], "password": password},
            200,
        )
        self.base_headers["Authorization"] = f"Bearer {tokens['access_token']}"
        for path in paths:
            preview_ids = ids(path)
            self.assertEqual(preview_ids, expected[path], path)
            self.assertNotIn(hidden.get(path), preview_ids, path)

    def test_delete_project_without_force(self):
        self.generate_fixture_project_closed()
        account, _ = preview_accounts_service.create_or_reset_preview_account(
            self.project_closed.id
        )
        # The team change event pins any project to a forced delete, which
        # is outside what this test checks.
        ApiEvent.delete_all_by(project_id=self.project_closed.id)
        self.delete(f"data/projects/{self.project_closed.id}")
        self.assertIsNone(Person.get(account["id"]))
