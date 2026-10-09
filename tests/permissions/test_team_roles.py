from tests.base import ApiDBTestCase

from zou.app import db
from zou.app.models.person import Person
from zou.app.models.project import ProjectPersonLink
from zou.app.services import projects_service
from zou.app.exceptions import WrongParameterException


class TeamRoleServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_person()

    def test_add_team_member_with_role(self):
        projects_service.add_team_member(
            str(self.project.id), str(self.person.id), role="supervisor"
        )
        self.assertEqual(
            projects_service.get_team_roles(str(self.project.id)),
            {str(self.person.id): "supervisor"},
        )

    def test_add_team_member_without_role_inherits(self):
        projects_service.add_team_member(
            str(self.project.id), str(self.person.id)
        )
        self.assertEqual(
            projects_service.get_team_roles(str(self.project.id)), {}
        )

    def test_update_team_member_role(self):
        projects_service.add_team_member(
            str(self.project.id), str(self.person.id)
        )
        projects_service.update_team_member_role(
            str(self.project.id), str(self.person.id), "manager"
        )
        self.assertEqual(
            projects_service.get_team_roles(str(self.project.id)),
            {str(self.person.id): "manager"},
        )
        projects_service.update_team_member_role(
            str(self.project.id), str(self.person.id), None
        )
        self.assertEqual(
            projects_service.get_team_roles(str(self.project.id)), {}
        )

    def test_update_team_member_role_requires_membership(self):
        self.assertRaises(
            WrongParameterException,
            projects_service.update_team_member_role,
            str(self.project.id),
            str(self.person.id),
            "manager",
        )

    def test_update_team_member_role_rejects_admin(self):
        projects_service.add_team_member(
            str(self.project.id), str(self.person.id)
        )
        self.assertRaises(
            WrongParameterException,
            projects_service.update_team_member_role,
            str(self.project.id),
            str(self.person.id),
            "admin",
        )

    def test_add_team_member_rejects_admin_without_partial_state(self):
        self.assertRaises(
            WrongParameterException,
            projects_service.add_team_member,
            str(self.project.id),
            str(self.person.id),
            "admin",
        )
        project = projects_service.get_project_raw(str(self.project.id))
        self.assertEqual(project.team, [])

    def test_a_role_that_is_not_one_is_refused(self):
        """
        The route validates the role against its own list, but the service
        is called from plugins and from the shell too, and the column is an
        enum: writing a typo raises deep in the driver.
        """
        projects_service.add_team_member(
            str(self.project.id), str(self.person.id)
        )
        for role in ["supreme-leader", "Manager", ""]:
            with self.subTest(role=role):
                self.assertRaises(
                    WrongParameterException,
                    projects_service.update_team_member_role,
                    str(self.project.id),
                    str(self.person.id),
                    role,
                )
                self.assertRaises(
                    WrongParameterException,
                    projects_service.add_team_member,
                    str(self.project.id),
                    str(self.person.id),
                    role,
                )

    def test_a_role_leaves_the_team_with_the_person(self):
        """
        The role lives on the membership link: someone taken off a team and
        put back on it comes back with their global role, not with the one
        they were given last time.
        """
        projects_service.add_team_member(
            str(self.project.id), str(self.person.id), role="manager"
        )
        projects_service.remove_team_member(
            str(self.project.id), str(self.person.id)
        )
        self.assertIsNone(
            ProjectPersonLink.query.filter_by(
                project_id=self.project.id, person_id=self.person.id
            ).first()
        )

        projects_service.add_team_member(
            str(self.project.id), str(self.person.id)
        )

        self.assertEqual(
            projects_service.get_team_roles(str(self.project.id)), {}
        )


class TeamRoleApiTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_person()

    def test_add_team_member_with_role(self):
        data = {"person_id": str(self.person.id), "role": "supervisor"}
        self.post(f"data/projects/{self.project.id}/team", data, 201)
        team = self.get(f"data/projects/{self.project.id}/team")
        self.assertEqual(team[0]["project_role"], "supervisor")

    def test_add_team_member_rejects_admin_role(self):
        data = {"person_id": str(self.person.id), "role": "admin"}
        self.post(f"data/projects/{self.project.id}/team", data, 400)

    def test_put_team_member_role(self):
        self.post(
            f"data/projects/{self.project.id}/team",
            {"person_id": str(self.person.id)},
            201,
        )
        result = self.put(
            f"data/projects/{self.project.id}/team/{self.person.id}",
            {"role": "manager"},
        )
        self.assertEqual(result["role"], "manager")
        result = self.put(
            f"data/projects/{self.project.id}/team/{self.person.id}",
            {"role": None},
        )
        self.assertIsNone(result["role"])
        team = self.get(f"data/projects/{self.project.id}/team")
        self.assertIsNone(team[0]["project_role"])

    def test_put_team_member_role_requires_membership(self):
        # update_team_member_role raises WrongParameterException for a
        # non-member, which maps to 400, not 404.
        self.put(
            f"data/projects/{self.project.id}/team/{self.person.id}",
            {"role": "manager"},
            400,
        )

    def test_put_team_member_role_rejects_admin(self):
        self.post(
            f"data/projects/{self.project.id}/team",
            {"person_id": str(self.person.id)},
            201,
        )
        self.put(
            f"data/projects/{self.project.id}/team/{self.person.id}",
            {"role": "admin"},
            400,
        )


class ProjectRoleRouteTestCase(ApiDBTestCase):
    """
    Promotion and demotion through a manager-gated route:
    POST /data/projects/<id>/team goes through
    check_manager_project_access.
    """

    def setUp(self):
        super().setUp()
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
