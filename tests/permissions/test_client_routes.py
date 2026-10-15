from tests.base import ApiDBTestCase

from zou.app.services import projects_service


class ClientStudioRoutesTestCase(ApiDBTestCase):
    """
    How the studio runs a production (time spent, quotas, planning, news,
    retakes) stays out of a client's reach, while the status of the work
    stays open to them.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_user_client()
        self.project_id = str(self.project.id)
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )

    def studio_paths(self):
        return [
            f"data/projects/{self.project_id}/time-spents",
            f"data/projects/{self.project_id}/milestones",
            f"data/projects/{self.project_id}/schedule-items",
            f"data/projects/{self.project_id}/news",
            f"data/projects/{self.project_id}/quotas/{self.task_type.id}",
            f"data/projects/{self.project_id}/quotas/persons/{self.person.id}",
            f"data/projects/{self.project_id}/episodes/retake-stats",
        ]

    def test_studio_routes_are_closed_to_clients(self):
        for path in self.studio_paths():
            self.get(path, 200)
        self.log_in_client()
        for path in self.studio_paths():
            self.get(path, 403)

    def test_work_status_stays_open_to_clients(self):
        self.log_in_client()
        self.get(f"data/projects/{self.project_id}/episodes/stats", 200)
        self.get(f"data/projects/{self.project_id}/playlists", 200)
        self.get(f"data/shots/with-tasks?project_id={self.project_id}", 200)
