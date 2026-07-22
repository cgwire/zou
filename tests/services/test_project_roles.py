from flask import g

from tests.base import ApiDBTestCase

from zou.app import app, db
from zou.app.models.project import ProjectPersonLink
from zou.app.services import user_service
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
