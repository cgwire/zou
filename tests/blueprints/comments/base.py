from tests.base import ApiDBTestCase
from zou.app.models.person import Person
from zou.app.models.task import Task
from zou.app.services import comments_service


class CommentTestCase(ApiDBTestCase):
    """
    One task with a first comment on it, plus a client to read it as.
    Holds no test of its own.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_user_client()
        self.generate_fixture_task()
        self.comment = comments_service.new_comment(
            self.task.id,
            self.task_status.id,
            self.user["id"],
            "first comment",
        )

    def make_sibling_task(self):
        """
        Create a second task on the same asset with a different task type.
        """
        return Task.create(
            name="Modeling task",
            project_id=self.project.id,
            task_type_id=self.task_type_modeling.id,
            task_status_id=self.task_status.id,
            entity_id=self.asset.id,
            assignees=[self.person],
            assigner_id=self.assigner.id,
        )


class ClientCommentTestCase(CommentTestCase):
    """
    The comment fixtures, plus the helpers to read a comment as the client
    of the production. Holds no test of its own.
    """

    def put_the_client_in_the_team(self):
        client_person = Person.get(self.user_client["id"])
        self.project.team = [client_person, self.person]
        self.project.save()
        return client_person

    def comment_for_client(self, text="Visible to client", for_client=True):
        return self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {
                "task_status_id": str(self.task_status.id),
                "comment": text,
                "for_client": for_client,
            },
        )


class MentionTestCase(ApiDBTestCase):
    """
    A task assigned to nobody relevant, and an artist who is part of the
    team without being assigned to the task: the only way in for them is a
    mention. Each test plants the mention it needs.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_department()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.generate_fixture_user_cg_artist()
        self.artist = Person.get(self.user_cg_artist["id"])
        self.project.team.append(self.artist)
        self.project.save()

    def mention_artist(self, text="please look @John Did3"):
        return comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], text
        )

    def post_comment_as_artist(self, task_status_id=None, code=201):
        if task_status_id is None:
            task_status_id = self.task_status.id
        return self.post(
            f"/actions/tasks/{self.task.id}/comment",
            {"task_status_id": str(task_status_id), "comment": "an answer"},
            code,
        )
