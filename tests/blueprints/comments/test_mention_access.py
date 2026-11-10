from tests.base import ApiDBTestCase
from zou.app.models.notification import Notification
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

    def post_comment_mentioning_artist(self):
        comment = comments_service.create_comment(
            self.user["id"],
            self.task.id,
            self.task_status.id,
            "please look @John Did3",
        )
        mention = Notification.get_by(type="mention", comment_id=comment["id"])
        self.assertEqual(str(mention.person_id), str(self.artist.id))
        return comment, mention

    def test_pinning_a_comment_leaves_its_mention_notification_alone(self):
        comment, mention = self.post_comment_mentioning_artist()
        mention_id = mention.id
        mention.update({"read": True})

        self.put(f"/data/comments/{comment['id']}", {"pinned": True}, 200)

        mentions = Notification.get_all_by(
            type="mention", comment_id=comment["id"]
        )
        self.assertEqual([mention.id for mention in mentions], [mention_id])
        self.assertTrue(mentions[0].read)

    def test_a_person_edited_out_of_a_comment_loses_the_notification(self):
        comment, _ = self.post_comment_mentioning_artist()

        self.put(
            f"/data/comments/{comment['id']}", {"text": "never mind"}, 200
        )

        self.assertEqual(
            Notification.get_all_by(type="mention", comment_id=comment["id"]),
            [],
        )

    def test_a_person_edited_into_a_comment_gets_a_notification(self):
        comment = comments_service.create_comment(
            self.user["id"],
            self.task.id,
            self.task_status.id,
            "no mention yet",
        )

        self.put(
            f"/data/comments/{comment['id']}",
            {"text": "please look @John Did3"},
            200,
        )

        mention = Notification.get_by(type="mention", comment_id=comment["id"])
        self.assertEqual(str(mention.person_id), str(self.artist.id))

    def comment_as_artist(self, text="no mention yet"):
        return comments_service.create_comment(
            str(self.artist.id), self.task.id, self.task_status.id, text
        )

    def log_in_manager_of_the_production(self):
        self.generate_fixture_user_manager()
        self.project.team.append(Person.get(self.user_manager["id"]))
        self.project.save()
        self.log_in_manager()

    def mention_rows(self, comment):
        return Notification.get_all_by(
            type="mention", comment_id=comment["id"]
        )

    def test_a_manager_mentioning_the_author_of_a_comment_notifies_them(self):
        comment = self.comment_as_artist()
        self.log_in_manager_of_the_production()

        self.put(
            f"/data/comments/{comment['id']}",
            {"text": "please look @John Did3"},
            200,
        )

        mention = Notification.get_by(type="mention", comment_id=comment["id"])
        self.assertEqual(str(mention.person_id), str(self.artist.id))

    def test_the_person_making_the_edit_is_not_notified_of_it(self):
        comment = self.comment_as_artist()
        self.log_in_manager_of_the_production()

        self.put(
            f"/data/comments/{comment['id']}",
            {"text": "noted @John Did2"},
            200,
        )

        self.assertEqual(self.mention_rows(comment), [])

    def test_a_typo_fix_does_not_notify_again_a_person_still_named(self):
        """
        Still named, without a notification: the cleanup of old data removed
        it. Fixing a typo is nothing new for them.
        """
        comment, _ = self.post_comment_mentioning_artist()
        Notification.delete_all_by(type="mention", comment_id=comment["id"])

        self.put(
            f"/data/comments/{comment['id']}",
            {"text": "please have a look @John Did3"},
            200,
        )

        self.assertEqual(self.mention_rows(comment), [])

    def test_a_typo_fix_is_no_news_for_a_person_named_before_joining(self):
        """
        The comment named the manager before they joined the production. A
        typo fix is no news for them, as for anyone the text already named.
        """
        comment = comments_service.create_comment(
            self.user["id"],
            self.task.id,
            self.task_status.id,
            "please look @John Did2",
        )
        self.generate_fixture_user_manager()
        self.project.team.append(Person.get(self.user_manager["id"]))
        self.project.save()

        self.put(
            f"/data/comments/{comment['id']}",
            {"text": "please have a look @John Did2"},
            200,
        )

        self.assertEqual(self.mention_rows(comment), [])

    def test_an_author_naming_their_department_hears_nothing_of_an_edit(self):
        self.artist.departments = [self.department_animation]
        self.artist.save()
        comment = self.comment_as_artist("@Animation someone available?")

        self.put(
            f"/data/comments/{comment['id']}",
            {"text": "@Animation is someone available?"},
            200,
        )

        self.assertEqual(self.mention_rows(comment), [])

    def test_an_update_leaving_the_text_alone_notifies_nobody(self):
        """
        A person with no notification for a comment naming them is not newly
        mentioned as long as the text stays the same: the cleanup of old data
        may have removed the row, or they joined the production since. The
        edit form of Kitsu always sends the text back.
        """
        comment, _ = self.post_comment_mentioning_artist()
        Notification.delete_all_by(type="mention", comment_id=comment["id"])

        self.put(f"/data/comments/{comment['id']}", {"pinned": True}, 200)
        self.put(
            f"/data/comments/{comment['id']}",
            {
                "text": comment["text"],
                "checklist": [{"text": "an item", "checked": True}],
            },
            200,
        )

        self.assertEqual(
            Notification.get_all_by(type="mention", comment_id=comment["id"]),
            [],
        )
