import os

from flask import g, request_started

from tests.base import ApiDBTestCase
from zou.app.models.chat import Chat
from zou.app.services import chats_service, news_service, projects_service


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
    The open tasks pool and its burndown are planning views: clients and
    vendors are refused, by the role they hold on the project when the call
    names one.
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

    def test_vendors_are_refused(self):
        self.generate_fixture_user_vendor()
        projects_service.add_team_member(
            self.project_id, self.user_vendor["id"]
        )
        self.log_in_vendor()
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

    def test_a_vendor_on_the_project_is_refused_its_pool(self):
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"], role="vendor"
        )
        self.log_in_cg_artist()
        for path in self.paths:
            self.get(f"{path}?project_id={self.project_id}", 403)


class ClientEntityChatTestCase(FreshRequestsTestCase):
    """
    The chat of an entity is a studio discussion: Kitsu never opens it to
    a client, and its routes refuse them, by the role on the project. The
    files attached to its messages follow the chat.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_user_client()
        self.generate_fixture_user_cg_artist()
        self.project_id = str(self.project.id)
        for user in (self.user_client, self.user_cg_artist):
            projects_service.add_team_member(self.project_id, user["id"])
        # A client who joined the chat before it closed to them.
        chats_service.join_chat(self.asset.id, self.user_client["id"])
        self.message = chats_service.create_chat_message(
            chats_service.get_chat(self.asset.id)["id"],
            self.user_client["id"],
            "Hello",
        )
        self.chat_path = f"data/entities/{self.asset.id}/chat"
        self.read_paths = [
            self.chat_path,
            f"{self.chat_path}/messages",
            f"{self.chat_path}/messages/{self.message['id']}",
        ]

    def generate_attachment(self):
        self.post(f"actions/user/chats/{self.asset.id}/join", {}, 200)
        message = self.upload_file(
            f"{self.chat_path}/messages",
            self.get_fixture_file_path(os.path.join("thumbnails", "th01.png")),
            extra_fields={"message": "With a file"},
        )
        chat_message = chats_service.get_chat_message(message["id"])
        return chat_message["attachment_files"][0]

    def get_status(self, path):
        return self.app.get(path, headers=self.base_headers).status_code

    def test_the_chat_is_closed_to_clients(self):
        message_path = f"{self.chat_path}/messages/{self.message['id']}"
        self.log_in_client()
        for path in self.read_paths:
            self.get(path, 403)
        self.post(f"{self.chat_path}/messages", {"message": "Hi"}, 403)
        self.delete(message_path, 403)
        self.post(f"actions/user/chats/{self.asset.id}/join", {}, 403)
        self.assertEqual(self.get("data/user/chats"), [])

    def test_a_client_can_still_leave_the_chat(self):
        self.log_in_client()
        self.delete(f"actions/user/chats/{self.asset.id}/join")
        chat = chats_service.get_chat(self.asset.id)
        self.assertNotIn(self.user_client["id"], chat["participants"])

    def test_the_team_keeps_the_chat(self):
        self.log_in_cg_artist()
        for path in self.read_paths:
            self.get(path)

    def test_a_client_on_the_project_is_refused_the_chat(self):
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"], role="client"
        )
        self.log_in_cg_artist()
        for path in self.read_paths:
            self.get(path, 403)

    def test_the_attachments_follow_the_chat(self):
        attachment = self.generate_attachment()
        attachment_path = f"data/attachment-files/{attachment['id']}"
        paths = [
            attachment_path,
            f"{attachment_path}/file/{attachment['name']}",
            f"pictures/thumbnails/attachment-files/{attachment['id']}.png",
        ]
        self.log_in_cg_artist()
        self.assertEqual([self.get_status(path) for path in paths], [200] * 3)
        self.log_in_client()
        self.assertEqual([self.get_status(path) for path in paths], [403] * 3)

    def test_an_attachment_record_checks_the_project_of_its_chat(self):
        attachment = self.generate_attachment()
        chat_count = Chat.query.count()
        self.generate_fixture_user_supervisor()
        self.log_in_supervisor()
        status = self.get_status(f"data/attachment-files/{attachment['id']}")
        self.assertEqual(status, 403)
        self.assertEqual(Chat.query.count(), chat_count)


class ClientTimeSpentsTestCase(FreshRequestsTestCase):
    """
    The time logged on a task or an entity is how the studio runs a
    production: Kitsu shows it to no client, and its routes refuse them.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_user_client()
        self.generate_fixture_user_cg_artist()
        self.project_id = str(self.project.id)
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        self.paths = [
            f"data/entities/{self.asset.id}/time-spents",
            f"actions/tasks/{self.task.id}/time-spents",
            f"actions/tasks/{self.task.id}/time-spents/2026-10-27",
        ]

    def test_time_spents_are_closed_to_clients(self):
        self.log_in_client()
        for path in self.paths:
            self.get(path, 403)

    def test_the_team_keeps_the_time_spents(self):
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()
        for path in self.paths:
            self.get(path)

    def test_a_client_on_the_project_is_refused_the_time_spents(self):
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"], role="client"
        )
        self.log_in_cg_artist()
        for path in self.paths:
            self.get(path, 403)


class ClientNewsTestCase(FreshRequestsTestCase):
    """
    The news feed tells who did what on a production, and when: Kitsu
    shows it to no client, and every route serving it refuses them, by the
    role on the project.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_commented_shot_task()
        news = news_service.create_news_for_task_and_comment(
            self.task_dict, self.comment
        )
        self.generate_fixture_user_client()
        self.generate_fixture_user_cg_artist()
        self.project_id = self.task_dict["project_id"]
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        self.paths = [
            f"data/projects/news?project_id={self.project_id}",
            f"data/projects/{self.project_id}/news/{news['id']}",
            f"data/entities/{self.shot.id}/news",
        ]

    def test_the_news_are_closed_to_clients(self):
        self.log_in_client()
        self.get("data/projects/news", 403)
        for path in self.paths:
            self.get(path, 403)

    def test_the_team_keeps_the_news(self):
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()
        for path in self.paths:
            self.get(path)

    def test_a_client_on_the_project_is_refused_its_news(self):
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"], role="client"
        )
        self.log_in_cg_artist()
        for path in self.paths:
            self.get(path, 403)
