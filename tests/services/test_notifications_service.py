from unittest.mock import patch

from tests.base import ApiDBTestCase

from zou.app.models.notification import Notification
from zou.app.models.person import Person
from zou.app.services import (
    comments_service,
    notifications_service,
    projects_service,
)


class NotificationsTestCase(ApiDBTestCase):
    """
    One production with a sequence and a shot, and a task on that shot.
    Holds no test of its own.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.sequence_dict = self.sequence.serialize()

        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.task_type_dict = self.task_type_animation.serialize()
        self.generate_fixture_task_status()
        self.task = self.generate_fixture_shot_task()
        self.task_dict = self.task.serialize(relations=True)
        # generate_fixture_shot_task assigned the first person to the task
        # and generate_fixture_person repoints self.person, so both are
        # named here rather than read off the attribute afterwards.
        self.assignee_id = str(self.person.id)
        self.outsider_id = str(
            self.generate_fixture_person(
                first_name="Jane", email="jane.doe@gmail.com"
            ).id
        )
        self.admin_id = self.user["id"]

        self.comment = comments_service.new_comment(
            self.task.id, self.task_status.id, self.admin_id, "first comment"
        )

    def kinds(self):
        """
        Every notification as a (type, recipient) pair, which is what these
        functions are really deciding.
        """
        return sorted(
            (str(notification.type.code), str(notification.person_id))
            for notification in Notification.get_all()
        )


class NotificationRecipientTestCase(NotificationsTestCase):
    """
    Who hears about a comment: the assignees, whoever subscribed to the
    task or to its sequence, and whoever already replied.
    """

    def test_get_notification_recipients(self):
        self.assertEqual(
            notifications_service.get_notification_recipients(self.task_dict),
            {self.assignee_id},
        )

    def test_a_person_who_replied_is_a_recipient(self):
        replies = [{"person_id": self.outsider_id}]
        self.assertEqual(
            notifications_service.get_notification_recipients(
                self.task_dict, replies
            ),
            {self.assignee_id, self.outsider_id},
        )

    def test_a_task_subscriber_is_a_recipient(self):
        notifications_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        self.assertIn(
            self.outsider_id,
            notifications_service.get_notification_recipients(self.task_dict),
        )

    def test_a_sequence_subscriber_is_a_recipient(self):
        notifications_service.subscribe_to_sequence(
            self.outsider_id,
            self.sequence_dict["id"],
            self.task_type_dict["id"],
        )
        self.assertIn(
            self.outsider_id,
            notifications_service.get_notification_recipients(self.task_dict),
        )

    def test_a_sequence_subscription_is_read_per_task_type(self):
        """
        Subscribing to the animation of a sequence says nothing about its
        layout.
        """
        notifications_service.subscribe_to_sequence(
            self.outsider_id,
            self.sequence_dict["id"],
            str(self.task_type_layout.id),
        )
        self.assertNotIn(
            self.outsider_id,
            notifications_service.get_notification_recipients(self.task_dict),
        )

    def test_an_asset_task_carries_no_sequence_subscription(self):
        """
        An asset has no parent to subscribe to, and the lookup must not
        take its absence for a match.
        """
        asset_task = self.generate_fixture_task().serialize(relations=True)
        self.assertEqual(
            notifications_service.get_sequence_subscriptions(asset_task), []
        )


class SubscriptionTestCase(NotificationsTestCase):
    """
    Subscribing and unsubscribing, on a task or on a whole sequence.
    """

    def test_subscribe_to_task(self):
        notifications_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        self.assertTrue(
            notifications_service.has_task_subscription(
                self.outsider_id, self.task_dict["id"]
            )
        )

    def test_subscribe_to_task_twice(self):
        first = notifications_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        second = notifications_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        self.assertEqual(first["id"], second["id"])

    def test_unsubscribe_from_task(self):
        notifications_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        notifications_service.unsubscribe_from_task(
            self.outsider_id, self.task_dict["id"]
        )
        self.assertIsNone(
            notifications_service.get_task_subscription_raw(
                self.outsider_id, self.task_dict["id"]
            )
        )

    def test_unsubscribe_from_a_task_nobody_subscribed_to(self):
        self.assertEqual(
            notifications_service.unsubscribe_from_task(
                self.outsider_id, self.task_dict["id"]
            ),
            {},
        )

    def test_is_person_subscribed(self):
        """
        Memoized, so subscribing and unsubscribing both have to drop it.
        """
        self.assertFalse(
            notifications_service.is_person_subscribed(
                self.outsider_id, self.task_dict["id"]
            )
        )
        notifications_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        self.assertTrue(
            notifications_service.is_person_subscribed(
                self.outsider_id, self.task_dict["id"]
            )
        )
        notifications_service.unsubscribe_from_task(
            self.outsider_id, self.task_dict["id"]
        )
        self.assertFalse(
            notifications_service.is_person_subscribed(
                self.outsider_id, self.task_dict["id"]
            )
        )

    def test_a_subscription_read_on_a_malformed_id(self):
        """
        The ids come straight from the path, so a value the driver cannot
        read as a uuid answers no subscription rather than a 500.
        """
        self.assertIsNone(
            notifications_service.get_task_subscription_raw(
                self.outsider_id, "not-an-id"
            )
        )
        self.assertFalse(
            notifications_service.has_sequence_subscription(
                self.outsider_id, "not-an-id", self.task_type_dict["id"]
            )
        )

    def test_subscribe_to_sequence(self):
        notifications_service.subscribe_to_sequence(
            self.outsider_id,
            self.sequence_dict["id"],
            self.task_type_dict["id"],
        )
        self.assertTrue(
            notifications_service.has_sequence_subscription(
                self.outsider_id,
                self.sequence_dict["id"],
                self.task_type_dict["id"],
            )
        )

    def test_unsubscribe_from_sequence(self):
        notifications_service.subscribe_to_sequence(
            self.outsider_id,
            self.sequence_dict["id"],
            self.task_type_dict["id"],
        )
        notifications_service.unsubscribe_from_sequence(
            self.outsider_id,
            self.sequence_dict["id"],
            self.task_type_dict["id"],
        )
        self.assertFalse(
            notifications_service.has_sequence_subscription(
                self.outsider_id,
                self.sequence_dict["id"],
                self.task_type_dict["id"],
            )
        )

    def test_unsubscribe_from_a_sequence_nobody_subscribed_to(self):
        self.assertEqual(
            notifications_service.unsubscribe_from_sequence(
                self.outsider_id,
                self.sequence_dict["id"],
                self.task_type_dict["id"],
            ),
            {},
        )

    def test_get_all_sequence_subscriptions(self):
        """
        Scoped three ways: the person, the task type, and the production
        the sequence belongs to.
        """
        person_id = self.outsider_id
        task_type_id = self.task_type_dict["id"]
        notifications_service.subscribe_to_sequence(
            person_id, self.sequence_dict["id"], task_type_id
        )
        # Same sequence, another task type.
        notifications_service.subscribe_to_sequence(
            person_id, self.sequence_dict["id"], str(self.task_type_layout.id)
        )
        # Same sequence, someone else.
        notifications_service.subscribe_to_sequence(
            self.assignee_id, self.sequence_dict["id"], task_type_id
        )
        # A sequence of another production, subscribed the same way.
        self.generate_fixture_project_standard()
        other_sequence = self.generate_fixture_sequence(
            name="SQ99", project_id=self.project_standard.id
        )
        notifications_service.subscribe_to_sequence(
            person_id, str(other_sequence.id), task_type_id
        )

        result = notifications_service.get_all_sequence_subscriptions(
            person_id, str(self.project.id), task_type_id
        )
        self.assertEqual(result, [self.sequence_dict["id"]])

    def test_get_subscriptions_for_project(self):
        """
        Task subscriptions of one production. A sequence subscription
        carries no task, so it is not one of these.
        """
        notifications_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        notifications_service.subscribe_to_sequence(
            self.outsider_id,
            self.sequence_dict["id"],
            self.task_type_dict["id"],
        )
        self.generate_fixture_project_standard()
        other_task = self.generate_fixture_shot_task_standard()
        notifications_service.subscribe_to_task(
            self.outsider_id, str(other_task.id)
        )

        result = notifications_service.get_subscriptions_for_project(
            str(self.project.id)
        )

        self.assertEqual(
            [subscription["task_id"] for subscription in result],
            [self.task_dict["id"]],
        )

    def test_get_subscriptions_for_user(self):
        """
        The caller's own subscriptions in one production. Scoped to the
        caller, which is why it must never be memoized. Asked without an
        entity type it answers about assets only, which is what the asset
        page needs.
        """
        asset_task = self.generate_fixture_task(name="asset task")
        shot_task_id = self.task_dict["id"]
        for task_id in [str(asset_task.id), shot_task_id]:
            notifications_service.subscribe_to_task(self.admin_id, task_id)
        # Someone else's subscriptions must not show up, on this task or
        # on one the caller never subscribed to.
        other_asset_task = self.generate_fixture_task(name="other asset task")
        for task_id in [str(asset_task.id), str(other_asset_task.id)]:
            notifications_service.subscribe_to_task(self.outsider_id, task_id)

        # The caller comes from the request context, which a service test
        # has none of.
        with patch.object(
            notifications_service.persons_service,
            "get_current_user",
            return_value=self.user,
        ):
            self.assertEqual(
                notifications_service.get_subscriptions_for_user(
                    str(self.project.id)
                ),
                {str(asset_task.id): True},
            )
            self.assertEqual(
                notifications_service.get_subscriptions_for_user(
                    str(self.project.id),
                    entity_type_id=str(self.shot_type.id),
                ),
                {shot_task_id: True},
            )

            self.generate_fixture_project_standard()
            self.assertEqual(
                notifications_service.get_subscriptions_for_user(
                    str(self.project_standard.id)
                ),
                {},
            )
            self.assertEqual(
                notifications_service.get_subscriptions_for_user(None), {}
            )


class CommentNotificationTestCase(NotificationsTestCase):
    """
    What a comment, a reply and a mention raise.
    """

    def test_create_notification(self):
        notification = notifications_service.create_notification(
            self.assignee_id,
            comment_id=self.comment["id"],
            author_id=self.comment["person_id"],
            task_id=self.comment["object_id"],
        )
        self.assertIsNotNone(Notification.get(notification["id"]))

    def test_create_notifications_for_task_and_comment(self):
        notifications_service.create_notifications_for_task_and_comment(
            self.task_dict, self.comment
        )
        self.assertEqual(self.kinds(), [("comment", self.assignee_id)])
        self.assertEqual(
            str(Notification.get_all()[0].author_id), self.admin_id
        )

    def test_the_author_of_a_comment_is_not_notified_of_it(self):
        """
        The admin is the author here, and is also a recipient through the
        assignation once assigned.
        """
        self.task.assignees.append(Person.get(self.admin_id))
        self.task.save()
        notifications_service.create_notifications_for_task_and_comment(
            self.task.serialize(relations=True), self.comment
        )
        self.assertEqual(self.kinds(), [("comment", self.assignee_id)])

    def test_create_notifications_for_task_and_comment_with_mentions(self):
        self.comment["mentions"] = [self.outsider_id]
        notifications_service.create_notifications_for_task_and_comment(
            self.task_dict, self.comment
        )
        self.assertEqual(
            self.kinds(),
            sorted(
                [
                    ("comment", self.assignee_id),
                    ("mention", self.outsider_id),
                ]
            ),
        )

    def test_a_mention_of_a_department(self):
        """
        Mentioning a department reaches its members who are on the
        production, and leaves the comment dict alone: it may come
        straight from the cache.
        """
        assignee = Person.get(self.assignee_id)
        assignee.departments.append(self.department)
        assignee.save()
        projects_service.add_team_member(
            str(self.project.id), self.assignee_id
        )
        comment = {
            "mentions": [],
            "department_mentions": [str(self.department.id)],
        }

        result = notifications_service.get_mentioned_people(
            str(self.project.id), comment
        )

        self.assertEqual(result, [self.assignee_id])
        self.assertEqual(comment["mentions"], [])

    def test_a_mention_of_someone_by_name(self):
        result = notifications_service.get_mentioned_people(
            str(self.project.id),
            {"mentions": [self.assignee_id], "department_mentions": []},
        )
        self.assertEqual(result, [self.assignee_id])

    def test_create_notifications_for_task_and_reply(self):
        """
        A reply notifies the same people as the comment did, plus the
        author of the comment being replied to.
        """
        reply = comments_service.reply_comment(
            self.comment["id"], "a reply", person_id=self.outsider_id
        )
        self.assertEqual(
            self.kinds(),
            sorted(
                [
                    ("reply", self.assignee_id),
                    ("reply", self.admin_id),
                ]
            ),
        )
        self.assertEqual(str(Notification.get_all()[0].reply_id), reply["id"])

    def test_the_author_of_a_reply_is_not_notified_of_it(self):
        comments_service.reply_comment(
            self.comment["id"], "a reply", person_id=self.assignee_id
        )
        self.assertEqual(self.kinds(), [("reply", self.admin_id)])

    def test_a_mention_inside_a_reply(self):
        with patch.object(
            comments_service,
            "get_comment_mention_ids",
            return_value=[self.outsider_id],
        ):
            comments_service.reply_comment(
                self.comment["id"], "a reply", person_id=self.assignee_id
            )
        # Being mentioned in a reply is not the same as taking part in the
        # thread: the mentioned person hears about the mention only.
        self.assertEqual(
            self.kinds(),
            sorted(
                [
                    ("reply", self.admin_id),
                    ("reply-mention", self.outsider_id),
                ]
            ),
        )

    def test_reset_notifications_for_mentions(self):
        """
        Editing a comment rebuilds the notifications its mentions raised,
        against the mentions it now carries.
        """
        self.comment["mentions"] = [self.outsider_id]
        notifications_service.create_notifications_for_task_and_comment(
            self.task_dict, self.comment
        )

        self.comment["mentions"] = [self.assignee_id]
        notifications_service.reset_notifications_for_mentions(self.comment)

        self.assertEqual(
            self.kinds(),
            sorted(
                [
                    ("comment", self.assignee_id),
                    ("mention", self.assignee_id),
                ]
            ),
        )

    def test_reset_notifications_for_mentions_keeps_the_replies(self):
        """
        A reply raises a notification of its own, tied to the comment it
        answers. Editing that comment used to wipe it, and nothing here
        recreates one: the reader simply lost it. Replies clean up after
        themselves when they are deleted.
        """
        comments_service.reply_comment(
            self.comment["id"], "a reply", person_id=self.assignee_id
        )
        comment = notifications_service.tasks_service.get_comment(
            self.comment["id"], relations=True
        )

        notifications_service.reset_notifications_for_mentions(comment)

        self.assertEqual(self.kinds(), [("reply", self.admin_id)])

    def test_delete_notifications_for_comment(self):
        notifications_service.create_notification(
            self.assignee_id,
            comment_id=self.comment["id"],
            author_id=self.comment["person_id"],
            task_id=self.comment["object_id"],
        )
        result = notifications_service.delete_notifications_for_comment(
            self.comment["id"]
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(Notification.get_all(), [])

    def test_get_last_notifications(self):
        notifications_service.create_notification(
            self.assignee_id,
            comment_id=self.comment["id"],
            author_id=self.comment["person_id"],
            task_id=self.comment["object_id"],
            type="comment",
        )
        self.assertEqual(
            len(notifications_service.get_last_notifications()), 1
        )
        self.assertEqual(
            notifications_service.get_last_notifications(
                notification_type="assignation"
            ),
            [],
        )

    def test_get_notifications_for_project(self):
        """
        Paginated and scoped to the production the notified task belongs to.
        """
        author_id = self.comment["person_id"]
        notifications_service.create_notification(
            self.outsider_id,
            comment_id=self.comment["id"],
            author_id=author_id,
            task_id=self.task_dict["id"],
        )

        # A notification on a task of another production.
        self.generate_fixture_project_standard()
        other_task = self.generate_fixture_shot_task_standard()
        notifications_service.create_notification(
            self.outsider_id,
            author_id=author_id,
            task_id=str(other_task.id),
        )

        result = notifications_service.get_notifications_for_project(
            str(self.project.id)
        )

        # get_paginated_results answers a plain list until there is more
        # than one page of them.
        self.assertEqual(
            [notification["task_id"] for notification in result],
            [self.task_dict["id"]],
        )


class AssignationNotificationTestCase(NotificationsTestCase):
    """
    What being handed a task raises.
    """

    def test_create_assignation_notification(self):
        notifications_service.create_assignation_notification(
            self.task_dict["id"], self.outsider_id
        )
        self.assertEqual(self.kinds(), [("assignation", self.outsider_id)])
        self.assertEqual(
            str(Notification.get_all()[0].author_id),
            self.task_dict["assigner_id"],
        )

    def test_assigning_a_task_to_oneself_notifies_nobody(self):
        self.assertIsNone(
            notifications_service.create_assignation_notification(
                self.task_dict["id"], self.task_dict["assigner_id"]
            )
        )
        self.assertEqual(Notification.get_all(), [])

    def test_create_assignation_notification_by_someone_else(self):
        """
        The assigner on the task is who created it; a later assignation is
        made by whoever is doing it now.
        """
        notifications_service.create_assignation_notification(
            self.task_dict["id"],
            self.outsider_id,
            author_id=self.assignee_id,
        )
        self.assertEqual(
            str(Notification.get_all()[0].author_id), self.assignee_id
        )


class PlaylistNotificationTestCase(NotificationsTestCase):
    """
    Telling the clients of a production that a playlist is ready for
    review.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_user_client()
        self.client_id = self.user_client["id"]
        projects_service.add_team_member(str(self.project.id), self.client_id)
        self.playlist = self.generate_fixture_playlist("Ready")

    def notify(self, **kwargs):
        with patch.object(
            notifications_service.persons_service,
            "get_current_user",
            return_value=self.user,
        ), patch.object(
            notifications_service.emails_service,
            "send_playlist_ready_notification",
        ) as send:
            notifications_service.notify_clients_playlist_ready(
                self.playlist, **kwargs
            )
        return [call.args[0] for call in send.call_args_list]

    def test_notify_clients_playlist_ready(self):
        """
        Every client of the production the playlist belongs to, and only
        those: a client of another production is not told, and neither is
        a team member who is not a client.
        """
        self.generate_fixture_project_standard()
        elsewhere = Person.create(
            first_name="Other",
            last_name="Client",
            email="other.client@gmail.com",
            role="client",
        )
        projects_service.add_team_member(
            str(self.project_standard.id), str(elsewhere.id)
        )
        # A bot reads the playlist through its token, it has no mailbox.
        bot = Person.create(
            first_name="Bot",
            last_name="Client",
            email="bot.client@gmail.com",
            role="client",
            is_bot=True,
        )
        projects_service.add_team_member(str(self.project.id), str(bot.id))

        self.assertEqual(self.notify(), [self.client_id])
        self.assertEqual(self.kinds(), [("playlist-ready", self.client_id)])

    def test_a_client_of_the_production_only_by_its_project_role(self):
        """
        A role can be set per production: someone who is a user
        everywhere else is a client here, and is told.
        """
        projects_service.add_team_member(
            str(self.project.id), self.assignee_id, role="client"
        )
        self.assertEqual(
            sorted(self.notify()),
            sorted([self.client_id, self.assignee_id]),
        )

    def test_notify_clients_of_one_studio(self):
        from zou.app.models.studio import Studio

        studio = Studio.create(name="Remote", color="#000000")
        other_client = Person.create(
            first_name="Studio",
            last_name="Client",
            email="studio.client@gmail.com",
            role="client",
            studio_id=studio.id,
        )
        projects_service.add_team_member(
            str(self.project.id), str(other_client.id)
        )

        self.assertEqual(
            self.notify(studio_id=str(studio.id)), [str(other_client.id)]
        )
        # An empty studio reads as no studio filter at all, since that is
        # what an untouched form field sends.
        self.assertEqual(len(self.notify(studio_id="")), 2)

    def test_notify_clients_of_one_department(self):
        client = Person.get(self.client_id)
        client.departments.append(self.department)
        client.save()
        other_client = Person.create(
            first_name="Loose",
            last_name="Client",
            email="loose.client@gmail.com",
            role="client",
        )
        projects_service.add_team_member(
            str(self.project.id), str(other_client.id)
        )

        self.assertEqual(
            self.notify(department_id=str(self.department.id)),
            [self.client_id],
        )
        self.assertEqual(len(self.notify(department_id="")), 2)
