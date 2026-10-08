from tests.base import ApiDBTestCase

from zou.app.models.person import Person
from zou.app.models.studio import Studio
from zou.app.services import comments_service, projects_service, tasks_service
from tests.permissions.cases import DemotedRoleTestCase


class TaskCommentDeleteRoleTestCase(DemotedRoleTestCase):
    """
    Coverage audit fix: tasks/resources.py TaskCommentResource.delete
    resolves the project role before branching, so a demoted manager
    cannot delete another person's comment.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_comment()

    def test_demoted_manager_cannot_delete_others_comment(self):
        self.demote_manager("user")
        self.delete(
            f"data/tasks/{self.task.id}/comments/{self.comment['id']}", 403
        )


class CommentUpdateRoleTestCase(DemotedRoleTestCase):
    """
    Coverage audit fix: crud/comments.py
    CommentResource.check_update_permissions resolves the project role via
    check_belong_to_project before the has_manager check, so a demoted
    manager loses comment-edit powers.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_comment()

    def test_demoted_manager_cannot_edit_others_comment(self):
        self.demote_manager("user")
        self.put(
            f"data/comments/{self.comment['id']}",
            {"text": "Edited"},
            403,
        )


class CommentReplyRoleTestCase(ApiDBTestCase):
    """
    Coverage audit fix: comments/resources.py reply() runs
    check_task_action_access (which resolves the project role) before the
    client-isolation branch, so a demoted client cannot reply across
    studios.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_user_manager()
        self.generate_fixture_user_client()

    def test_demoted_client_blocked_from_replying_across_studios(self):
        studio_a = Studio.create(name="Studio A", color="#FF0000")
        studio_b = Studio.create(name="Studio B", color="#00FF00")

        author_id = str(self.user_client["id"])
        author = Person.get(author_id)
        author.update({"studio_id": studio_a.id})
        projects_service.add_team_member(
            str(self.project.id), author_id, role="client"
        )
        comment = comments_service.create_comment(
            person_id=author_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text="Client note",
        )

        manager_id = str(self.user_manager["id"])
        manager = Person.get(manager_id)
        manager.update({"studio_id": studio_b.id})
        projects_service.add_team_member(
            str(self.project.id), manager_id, role="client"
        )

        self.log_in_manager()
        self.post(
            f"data/tasks/{self.task.id}/comments/{comment['id']}/reply",
            {"text": "reply"},
            403,
        )


class DirectRoleReadTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_person()

    def make_comment(self, author_id):
        return comments_service.create_comment(
            person_id=author_id,
            task_id=str(self.task.id),
            task_status_id=str(self.task_status.id),
            text="hello",
        )

    def test_last_comment_map_uses_project_role(self):
        projects_service.add_team_member(
            str(self.project.id), str(self.person.id), role="client"
        )
        self.make_comment(str(self.person.id))
        comment_map = tasks_service.get_last_comment_map([str(self.task.id)])
        self.assertEqual(comment_map, {})
