from flask import g

from tests.base import ApiDBTestCase

from zou.app import app, db
from zou.app.models.person import Person
from zou.app.models.project import ProjectPersonLink
from zou.app.services import projects_service, user_service
from zou.app.utils import permissions


class ProjectPersonLinkRoleTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_person()

    def test_role_column_defaults_to_none(self):
        self.project.team.append(self.person)
        self.project.save()
        link = ProjectPersonLink.query.filter_by(
            project_id=self.project.id, person_id=self.person.id
        ).first()
        self.assertIsNotNone(link)
        self.assertIsNone(link.role)
        link.role = "supervisor"
        db.session.commit()
        link = ProjectPersonLink.query.filter_by(
            project_id=self.project.id, person_id=self.person.id
        ).first()
        self.assertEqual(link.role.code, "supervisor")


class GetProjectRoleTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_person()

    def add_to_team(self, person, role=None):
        self.project.team.append(person)
        self.project.save()
        if role is not None:
            link = ProjectPersonLink.query.filter_by(
                project_id=self.project.id, person_id=person.id
            ).first()
            link.role = role
            db.session.commit()

    def test_explicit_link_role_wins(self):
        self.add_to_team(self.person, role="supervisor")
        self.assertEqual(
            user_service.get_project_role(
                str(self.person.id), str(self.project.id)
            ),
            "supervisor",
        )

    def test_null_link_role_inherits_global_role(self):
        self.add_to_team(self.person)
        self.assertEqual(
            user_service.get_project_role(
                str(self.person.id), str(self.project.id)
            ),
            self.person.role.code,
        )

    def test_no_link_falls_back_to_global_role(self):
        self.assertEqual(
            user_service.get_project_role(
                str(self.person.id), str(self.project.id)
            ),
            self.person.role.code,
        )


class PermissionOverrideTestCase(ApiDBTestCase):
    def test_project_role_overrides_global_checks(self):
        with app.test_request_context():
            g.project_role = "manager"
            self.assertTrue(permissions.has_manager_permissions())
            self.assertFalse(permissions.has_supervisor_permissions())
            self.assertTrue(permissions.has_at_least_supervisor_permissions())
            self.assertFalse(permissions.has_client_permissions())

        with app.test_request_context():
            g.project_role = "user"
            self.assertFalse(permissions.has_manager_permissions())
            self.assertTrue(permissions.has_artist_permissions())

        with app.test_request_context():
            g.project_role = "vendor"
            self.assertTrue(permissions.has_vendor_permissions())
            self.assertFalse(permissions.has_at_least_supervisor_permissions())


class ProjectRoleRouteTestCase(ApiDBTestCase):
    """
    Promotion and demotion through a manager-gated route:
    POST /data/projects/<id>/team goes through
    check_manager_project_access.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        # generate_fixture_project reassigns self.project on every call, so
        # the first project must be captured before creating the second one.
        self.project_a = self.project
        self.project_b = self.generate_fixture_project("Second project")
        self.generate_fixture_person()
        self.generate_fixture_user_cg_artist()
        self.generate_fixture_user_manager()

    def set_team_role(self, project, person_id, role):
        link = ProjectPersonLink.query.filter_by(
            project_id=project.id, person_id=person_id
        ).first()
        link.role = role
        db.session.commit()

    def add_member(self, project, person_id, role=None):
        projects_service.add_team_member(str(project.id), person_id)
        if role is not None:
            self.set_team_role(project, person_id, role)

    def test_project_manager_can_manage_team_on_their_project_only(self):
        artist_id = str(self.user_cg_artist["id"])
        person_id = str(self.person.id)
        # Pre-add the target person so the POST under test only has to
        # clear the permission gate, not also perform a fresh team insert.
        projects_service.add_team_member(str(self.project_a.id), person_id)
        self.add_member(self.project_a, artist_id, role="manager")
        self.add_member(self.project_b, artist_id)
        self.log_in_cg_artist()
        data = {"person_id": person_id}
        self.post(f"data/projects/{self.project_a.id}/team", data, 201)
        self.post(f"data/projects/{self.project_b.id}/team", data, 403)

    def test_demoted_manager_cannot_manage_team(self):
        manager_id = str(self.user_manager["id"])
        self.add_member(self.project_a, manager_id, role="user")
        self.log_in_manager()
        data = {"person_id": str(self.person.id)}
        self.post(f"data/projects/{self.project_a.id}/team", data, 403)


class ProjectRoleSemanticsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_person()
        self.generate_fixture_user_cg_artist()

    def add_member(self, project, person_id, role=None):
        project.team.append(Person.get(person_id))
        project.save()
        if role is not None:
            link = ProjectPersonLink.query.filter_by(
                project_id=project.id, person_id=person_id
            ).first()
            link.role = role
            db.session.commit()

    def test_admin_ignores_project_roles(self):
        # ApiDBTestCase creates and logs in a global admin (self.user).
        # A link role never demotes an admin.
        admin_id = str(self.user["id"])
        self.add_member(self.project, admin_id, role="user")
        data = {"person_id": str(self.person.id)}
        self.post(f"data/projects/{self.project.id}/team", data, 201)

    def test_project_vendor_restricted_to_assigned_entities(self):
        # Global artist set as vendor on the project: entity access
        # restrictions apply, the unassigned task becomes forbidden.
        artist_id = str(self.user_cg_artist["id"])
        self.add_member(self.project, artist_id, role="vendor")
        self.log_in_cg_artist()
        self.get(f"data/tasks/{self.task.id}", 403)
