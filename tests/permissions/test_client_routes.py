from flask import g, request_started

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


class ClientHiddenStatsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_user_client()
        self.generate_fixture_user_cg_artist()
        self.generate_fixture_user_manager()
        self.project_id = str(self.project.id)
        self.path = f"data/projects/{self.project_id}/episodes/stats"
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )

    def hide_stats(self):
        self.project.update({"is_client_stats_visible": False})
        projects_service.clear_project_cache(self.project_id)

    def test_client_episode_stats_hidden(self):
        self.hide_stats()
        self.log_in_client()
        self.get(self.path, 403)

    def test_project_client_role_episode_stats_hidden(self):
        self.hide_stats()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"], role="client"
        )
        self.log_in_cg_artist()
        self.get(self.path, 403)

    def test_client_episode_stats_visible(self):
        self.log_in_client()
        self.get(self.path, 200)

    def test_manager_sees_hidden_episode_stats(self):
        self.hide_stats()
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        self.log_in_manager()
        self.get(self.path, 200)


def forget_project_role(sender, **extra):
    g.pop("project_role", None)


class FreshRequestsTestCase(ApiDBTestCase):
    """
    Each request starts without a project role, as a real one does: g
    outlives the requests of a test, so a route that read the role before
    resolving its project would read the one the previous request left.
    """

    def setUp(self):
        super().setUp()
        request_started.connect(forget_project_role, self.flask_app)
        self.addCleanup(
            request_started.disconnect, forget_project_role, self.flask_app
        )


class ClientOpenTasksTestCase(FreshRequestsTestCase):
    """
    The open tasks pool and its burndown are planning views: clients are
    refused, by the role they hold on the project when the call names one.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_user_client()
        self.generate_fixture_user_cg_artist()
        self.project_id = str(self.project.id)
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        self.paths = [
            "data/tasks/open-tasks",
            "data/tasks/open-tasks/burndown",
        ]

    def test_clients_are_refused(self):
        self.log_in_client()
        for path in self.paths:
            self.get(path, 403)
            self.get(f"{path}?project_id={self.project_id}", 403)

    def test_artists_keep_the_pool(self):
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()
        for path in self.paths:
            self.get(path, 200)
            self.get(f"{path}?project_id={self.project_id}", 200)

    def test_a_client_on_the_project_is_refused_its_pool(self):
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"], role="client"
        )
        self.log_in_cg_artist()
        for path in self.paths:
            self.get(f"{path}?project_id={self.project_id}", 403)
