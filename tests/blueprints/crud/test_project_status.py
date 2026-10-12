from tests.base import ApiDBTestCase
from zou.app.models.project_status import ProjectStatus

from zou.app.services import projects_service
from zou.app.utils import fields


class ProjectStatusTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_data(ProjectStatus, 3)

    def test_get_project_statuss(self):
        project_statuss = self.get("data/project-status")
        self.assertEqual(len(project_statuss), 3)

    def test_get_project_status(self):
        project_status = self.get_first("data/project-status")
        project_status_again = self.get(
            f"data/project-status/{project_status['id']}"
        )
        self.assertEqual(project_status, project_status_again)
        self.get_404(f"data/project-status/{fields.gen_uuid()}")

    def test_create_project_status(self):
        data = {"name": "open", "color": "#000000"}
        self.project_status = self.post("data/project-status", data)
        self.assertIsNotNone(self.project_status["id"])

        project_statuss = self.get("data/project-status")
        self.assertEqual(len(project_statuss), 4)

    def test_update_project_status(self):
        project_status = self.get_first("data/project-status")
        data = {"color": "#FFFFFF"}
        self.put(f"data/project-status/{project_status['id']}", data)
        project_status_again = self.get(
            f"data/project-status/{project_status['id']}"
        )
        self.assertEqual(data["color"], project_status_again["color"])
        self.put_404(f"data/project-status/{fields.gen_uuid()}", data)

    def test_delete_project_status(self):
        project_statuss = self.get("data/project-status")
        self.assertEqual(len(project_statuss), 3)
        project_status = project_statuss[0]
        self.delete(f"data/project-status/{project_status['id']}")
        project_statuss = self.get("data/project-status")
        self.assertEqual(len(project_statuss), 2)
        self.delete_404(f"data/project-status/{fields.gen_uuid()}")

    def test_create_project_status_drops_cached_list(self):
        self.assertEqual(len(projects_service.get_project_statuses()), 3)
        self.post(
            "data/project-status", {"name": "Archived", "color": "#000000"}
        )
        self.assertEqual(len(projects_service.get_project_statuses()), 4)

    def test_update_open_status_drops_cached_open_status(self):
        open_status = projects_service.get_open_status()
        self.put(
            f"data/project-status/{open_status['id']}", {"color": "#FF0000"}
        )
        self.assertEqual(
            projects_service.get_open_status()["color"], "#FF0000"
        )
