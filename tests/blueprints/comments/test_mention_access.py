from tests.base import ApiDBTestCase

from zou.app.models.person import Person
from zou.app.services import comments_service, projects_service


class MentionAccessTestCase(ApiDBTestCase):
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

    def test_mentioned_artist_can_comment_with_current_status(self):
        self.mention_artist()
        self.log_in_cg_artist()
        result = self.post_comment_as_artist()
        self.assertEqual(result["text"], "an answer")

    def test_mentioned_artist_cannot_change_status(self):
        self.mention_artist()
        self.log_in_cg_artist()
        self.post_comment_as_artist(self.task_status_wip.id, 403)

    def test_status_comparison_ignores_uuid_case(self):
        self.mention_artist()
        self.log_in_cg_artist()
        self.post_comment_as_artist(str(self.task_status.id).upper(), 201)

    def test_mentioned_artist_can_reply(self):
        comment = self.mention_artist()
        self.log_in_cg_artist()
        reply = self.post(
            f"/data/tasks/{self.task.id}/comments/{comment['id']}/reply",
            {"text": "my answer"},
            200,
        )
        self.assertEqual(reply["text"], "my answer")

    def test_department_mention_grants_access(self):
        self.artist.departments = [self.department_animation]
        self.artist.save()
        self.mention_artist("@Animation someone available?")
        self.log_in_cg_artist()
        self.post_comment_as_artist()

    def test_mention_inside_a_reply_grants_access(self):
        comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.user["id"], "no mention"
        )
        comments_service.reply_comment(
            comment["id"], "@John Did3 thoughts?", person_id=self.user["id"]
        )
        self.log_in_cg_artist()
        self.post_comment_as_artist()

    def test_non_mentioned_artist_is_refused(self):
        self.log_in_cg_artist()
        self.post_comment_as_artist(code=403)

    def test_mentioned_vendor_is_refused(self):
        self.generate_fixture_user_vendor()
        vendor = Person.get(self.user_vendor["id"])
        self.project.team.append(vendor)
        self.project.save()
        self.mention_artist("please look @John Did5")
        self.log_in_vendor()
        self.post_comment_as_artist(code=403)

    def test_mention_does_not_survive_team_removal(self):
        self.mention_artist()
        self.project.team = [self.person]
        self.project.save()
        projects_service.clear_project_cache(str(self.project.id))
        self.log_in_cg_artist()
        self.post_comment_as_artist(code=403)

    def test_mentioned_artist_cannot_add_preview(self):
        comment = self.mention_artist()
        self.log_in_cg_artist()
        self.post(
            f"/actions/tasks/{self.task.id}"
            f"/comments/{comment['id']}/add-preview",
            {"revision": 1},
            403,
        )

    def test_mentioned_author_cannot_move_status_through_comment_update(self):
        self.mention_artist()
        self.log_in_cg_artist()
        result = self.post_comment_as_artist()
        self.put(
            f"/data/comments/{result['id']}",
            {"task_status_id": str(self.task_status_wip.id)},
            403,
        )

    def test_assigned_artist_still_moves_status_through_comment_update(self):
        self.task.assignees.append(self.artist)
        self.task.save()
        self.log_in_cg_artist()
        result = self.post_comment_as_artist()
        self.put(
            f"/data/comments/{result['id']}",
            {"task_status_id": str(self.task_status_wip.id)},
            200,
        )
