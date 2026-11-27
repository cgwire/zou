from tests.blueprints.comments.base import MentionTestCase
from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.services import comments_service, projects_service


class CommentUpdateMentionTestCase(MentionTestCase):
    """
    The status and the mention notifications a comment update changes.
    """

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
        # Through the service: it drops the cached team of the project,
        # which posting the comment has just filled.
        projects_service.add_team_member(
            str(self.project.id), self.user_manager["id"]
        )
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
