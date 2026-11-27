from tests.base import ApiDBTestCase
from zou.app.models.project import ProjectTaskTypeSoftwareLink
from zou.app.services import cascade_deletion_service, projects_service


class TaskTypeSoftwareLinksTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_task_type()
        self.generate_fixture_software()
        self.project_id = str(self.project.id)
        self.task_type_id = str(self.task_type.id)
        self.software_id = str(self.software.id)
        projects_service.add_task_type_setting(
            self.project_id, self.task_type_id
        )
        self.link = {
            "project_id": self.project_id,
            "task_type_id": self.task_type_id,
            "software_id": self.software_id,
        }

    def add_link(self):
        return projects_service.add_task_type_software(
            self.project_id, self.task_type_id, self.software_id
        )

    def test_remove_returns_the_deleted_link(self):
        self.add_link()
        args = (self.project_id, self.task_type_id, self.software_id)
        removed = projects_service.remove_task_type_software(*args)
        self.assertEqual(removed, self.link)
        self.assertIsNone(projects_service.remove_task_type_software(*args))

    def test_the_links_go_with_the_project(self):
        self.add_link()
        cascade_deletion_service.remove_project(self.project_id)
        self.assertEqual(ProjectTaskTypeSoftwareLink.query.count(), 0)
