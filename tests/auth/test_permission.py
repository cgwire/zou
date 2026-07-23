from tests.base import ApiDBTestCase

from zou.app.services import projects_service


class PermissionTestCase(ApiDBTestCase):
    def setUp(self):
        super(PermissionTestCase, self).setUp()

        self.generate_fixture_user_cg_artist()
        self.user_cg_artist_id = self.user_cg_artist["id"]
        self.generate_fixture_user_manager()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.project_id = self.project.id

    def tearDown(self):
        self.log_out()
        super(PermissionTestCase, self).tearDown()

    def test_admin_can_create_project(self):
        self.log_in(self.user["email"])
        data = {"name": "Cosmos Landromat 2"}
        self.post("data/projects/", data, 201)

    def test_admin_can_edit_project(self):
        self.log_in(self.user["email"])
        data = {"name": "Cosmos Landromat 2 edited"}
        self.put(f"data/projects/{self.project_id}", data, 200)

    def test_admin_can_read_project(self):
        self.log_in(self.user["email"])
        project = self.get(f"data/projects/{self.project_id}")
        self.assertEqual(project["id"], str(self.project_id))

    def test_cg_artist_cannot_create_project(self):
        self.log_in_cg_artist()
        data = {"name": "Cosmos Landromat 2"}
        self.post("data/projects/", data, 403)

    def test_cg_artist_cannot_edit_project(self):
        self.log_in_cg_artist()
        data = {"name": "Cosmos Landromat 2 edited"}
        self.put(f"data/projects/{self.project_id}", data, 403)

    def test_cg_artist_can_read_open_projects(self):
        self.log_in_cg_artist()
        self.get("data/projects/open")

    def test_cg_artist_can_read_project_task_types(self):
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        task_type_id = self.task_type_concept.id
        projects_service.add_task_type_setting(
            self.project_id, task_type_id, 1
        )
        self.log_in_cg_artist()
        user_id = str(self.user_cg_artist["id"])
        projects_service.add_team_member(self.project_id, user_id)
        result = self.get(f"data/projects/{self.project_id}/task-types", 200)

        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], str(task_type_id))

    def test_cg_artist_can_read_project_task_statuses(self):
        self.log_in_cg_artist()
        user_id = str(self.user_cg_artist["id"])
        projects_service.add_team_member(self.project_id, user_id)
        self.get(f"data/projects/{self.project_id}/settings/task-status", 200)

    def test_manager_cannot_create_person(self):
        self.log_in_manager()
        data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@gmail.com",
        }
        self.post("data/persons", data, 403)

    def test_admin_can_create_person(self):
        self.log_in_admin()
        data = {
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe1@gmail.com",
        }
        self.post("data/persons", data, 201)

    def test_manager_cannot_update_admin(self):
        self.log_in_manager()
        data = {"email": "john.doe2@gmail.com"}
        self.put(f"data/persons/{self.user['id']}", data, 403)

    def test_manager_cannot_update_person(self):
        self.log_in_manager()
        data = {"role": "admin"}
        self.put(f"data/persons/{self.user_cg_artist_id}", data, 403)
        self.get(f"data/persons/{self.user_cg_artist_id}")

    def test_admin_can_update_admin(self):
        self.log_in_admin()
        data = {"first_name": "Super admin"}
        self.put(f"data/persons/{self.user['id']}", data, 200)

    def test_manager_cannot_delete_admin(self):
        self.log_in_manager()
        self.delete(f"data/persons/{self.user['id']}", 403)

    def test_user_projects(self):
        self.generate_fixture_project_standard()
        self.generate_fixture_project_closed_status()
        self.generate_fixture_project_closed()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.log_in_cg_artist()
        user_id = str(self.user_cg_artist["id"])
        projects = self.get("data/projects")
        self.assertEqual(len(projects), 0)

        projects_service.add_team_member(self.project_id, user_id)
        projects = self.get("data/projects")
        self.assertEqual(len(projects), 1)
        projects = self.get("data/projects/all")
        self.assertEqual(len(projects), 1)
        projects = self.get("data/projects/open")
        self.assertEqual(len(projects), 1)

    def test_is_in_team(self):
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        asset_id = self.asset.id
        self.log_in_cg_artist()
        self.get(f"data/assets/{asset_id}", 403)
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.get(f"data/assets/{asset_id}", 200)


class GlobalRoleFallbackTestCase(ApiDBTestCase):
    """
    Unit coverage of the permission helpers' global fallback, which reads
    the JWT identity directly since the Flask-Principal removal.
    """

    def helpers_for(self, role):
        from unittest import mock

        from zou.app import app
        from zou.app.utils import permissions

        fake_user = mock.Mock()
        fake_user.role = role
        with app.test_request_context():
            with mock.patch.object(
                permissions, "get_current_user", return_value=fake_user
            ):
                return {
                    "admin": permissions.has_admin_permissions(),
                    "manager": permissions.has_manager_permissions(),
                    "supervisor": permissions.has_supervisor_permissions(),
                    "at_least_supervisor": (
                        permissions.has_at_least_supervisor_permissions()
                    ),
                    "client": permissions.has_client_permissions(),
                    "vendor": permissions.has_vendor_permissions(),
                    "artist": permissions.has_artist_permissions(),
                }

    def test_admin_implies_manager(self):
        helpers = self.helpers_for("admin")
        self.assertTrue(helpers["admin"])
        self.assertTrue(helpers["manager"])
        self.assertTrue(helpers["at_least_supervisor"])
        self.assertFalse(helpers["supervisor"])

    def test_manager_is_not_admin(self):
        helpers = self.helpers_for("manager")
        self.assertFalse(helpers["admin"])
        self.assertTrue(helpers["manager"])
        self.assertTrue(helpers["at_least_supervisor"])

    def test_single_role_mappings(self):
        self.assertTrue(self.helpers_for("supervisor")["supervisor"])
        self.assertTrue(self.helpers_for("client")["client"])
        self.assertTrue(self.helpers_for("vendor")["vendor"])

    def test_artist_global_fallback_stays_false(self):
        # Flask-Principal never granted a "user" need: the historical
        # always-False global fallback is preserved on purpose.
        helpers = self.helpers_for("user")
        self.assertFalse(helpers["artist"])
        self.assertFalse(helpers["at_least_supervisor"])

    def test_person_permissions_follow_identity_type(self):
        from unittest import mock

        from zou.app import app
        from zou.app.utils import permissions

        for identity_type, expected in [
            ("person", True),
            ("person_api", True),
            ("bot", False),
        ]:
            with app.test_request_context():
                with mock.patch.object(
                    permissions,
                    "get_jwt",
                    return_value={"identity_type": identity_type},
                ):
                    self.assertEqual(
                        permissions.has_person_permissions(), expected
                    )

    def test_all_false_outside_request_context(self):
        from zou.app.utils import permissions

        self.assertFalse(permissions.has_admin_permissions())
        self.assertFalse(permissions.has_manager_permissions())
        self.assertFalse(permissions.has_person_permissions())
