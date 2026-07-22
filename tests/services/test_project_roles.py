from tests.base import ApiDBTestCase

from zou.app import db
from zou.app.models.project import ProjectPersonLink


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
