from tests.blueprints.comments.base import MentionTestCase
from zou.app.models.person import Person
from zou.app.services import comments_service, projects_service


class MentionAccessTestCase(MentionTestCase):
    """
    The routes a mention opens to an artist of the team, and the ones it
    keeps closed.
    """

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
