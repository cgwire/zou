from unittest.mock import patch
from sqlalchemy.exc import IntegrityError

from zou.app.models.subscription import Subscription
from zou.app.services import notifications_service, subscriptions_service
from tests.services.cases import NotificationsTestCase


class NotificationRecipientTestCase(NotificationsTestCase):
    def test_an_asset_task_carries_no_sequence_subscription(self):
        """
        An asset has no parent to subscribe to, and the lookup must not
        take its absence for a match.
        """
        asset_task = self.generate_fixture_task().serialize(relations=True)
        self.assertEqual(
            subscriptions_service.get_sequence_subscriptions_for_task(
                asset_task
            ),
            [],
        )


class SubscriptionTestCase(NotificationsTestCase):
    """
    Subscribing and unsubscribing, on a task or on a whole sequence.
    """

    def test_subscribe_to_task(self):
        subscriptions_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        self.assertTrue(
            subscriptions_service.has_task_subscription(
                self.outsider_id, self.task_dict["id"]
            )
        )

    def test_subscribe_to_task_twice(self):
        first = subscriptions_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        second = subscriptions_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        self.assertEqual(first["id"], second["id"])

    def test_subscribe_to_task_losing_the_insert_race(self):
        # Two concurrent subscriptions: the loser reads before the winner
        # commits, so subscription_task_uc rejects its insert. It must get
        # the winning row back instead of a 500. The rejection is simulated:
        # a real one rolls back the transaction holding the fixtures.
        first = subscriptions_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        read_subscription = subscriptions_service.get_task_subscription_raw
        reads = []

        def stale_first_read(*args, **kwargs):
            reads.append(None)
            if len(reads) == 1:
                return None
            return read_subscription(*args, **kwargs)

        rejected = IntegrityError("INSERT", {}, Exception("subscription_uc"))
        with patch.object(
            subscriptions_service,
            "get_task_subscription_raw",
            stale_first_read,
        ), patch.object(Subscription, "create", side_effect=rejected):
            second = subscriptions_service.subscribe_to_task(
                self.outsider_id, self.task_dict["id"]
            )
        self.assertEqual(first["id"], second["id"])

    def test_unsubscribe_from_task(self):
        subscriptions_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        subscriptions_service.unsubscribe_from_task(
            self.outsider_id, self.task_dict["id"]
        )
        self.assertIsNone(
            subscriptions_service.get_task_subscription_raw(
                self.outsider_id, self.task_dict["id"]
            )
        )

    def test_unsubscribe_from_a_task_nobody_subscribed_to(self):
        self.assertEqual(
            subscriptions_service.unsubscribe_from_task(
                self.outsider_id, self.task_dict["id"]
            ),
            {},
        )

    def test_is_person_subscribed(self):
        """
        Memoized, so subscribing and unsubscribing both have to drop it.
        """
        self.assertFalse(
            subscriptions_service.is_person_subscribed(
                self.outsider_id, self.task_dict["id"]
            )
        )
        subscriptions_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        self.assertTrue(
            subscriptions_service.is_person_subscribed(
                self.outsider_id, self.task_dict["id"]
            )
        )
        subscriptions_service.unsubscribe_from_task(
            self.outsider_id, self.task_dict["id"]
        )
        self.assertFalse(
            subscriptions_service.is_person_subscribed(
                self.outsider_id, self.task_dict["id"]
            )
        )

    def test_a_subscription_read_on_a_malformed_id(self):
        """
        The ids come straight from the path, so a value the driver cannot
        read as a uuid answers no subscription rather than a 500.
        """
        self.assertIsNone(
            subscriptions_service.get_task_subscription_raw(
                self.outsider_id, "not-an-id"
            )
        )
        self.assertFalse(
            subscriptions_service.has_sequence_subscription(
                self.outsider_id, "not-an-id", self.task_type_dict["id"]
            )
        )

    def test_subscribe_to_sequence(self):
        subscriptions_service.subscribe_to_sequence(
            self.outsider_id,
            self.sequence_dict["id"],
            self.task_type_dict["id"],
        )
        self.assertTrue(
            subscriptions_service.has_sequence_subscription(
                self.outsider_id,
                self.sequence_dict["id"],
                self.task_type_dict["id"],
            )
        )

    def test_unsubscribe_from_sequence(self):
        subscriptions_service.subscribe_to_sequence(
            self.outsider_id,
            self.sequence_dict["id"],
            self.task_type_dict["id"],
        )
        subscriptions_service.unsubscribe_from_sequence(
            self.outsider_id,
            self.sequence_dict["id"],
            self.task_type_dict["id"],
        )
        self.assertFalse(
            subscriptions_service.has_sequence_subscription(
                self.outsider_id,
                self.sequence_dict["id"],
                self.task_type_dict["id"],
            )
        )

    def test_unsubscribe_from_a_sequence_nobody_subscribed_to(self):
        self.assertEqual(
            subscriptions_service.unsubscribe_from_sequence(
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
        subscriptions_service.subscribe_to_sequence(
            person_id, self.sequence_dict["id"], task_type_id
        )
        # Same sequence, another task type.
        subscriptions_service.subscribe_to_sequence(
            person_id, self.sequence_dict["id"], str(self.task_type_layout.id)
        )
        # Same sequence, someone else.
        subscriptions_service.subscribe_to_sequence(
            self.assignee_id, self.sequence_dict["id"], task_type_id
        )
        # A sequence of another production, subscribed the same way.
        self.generate_fixture_project_standard()
        other_sequence = self.generate_fixture_sequence(
            name="SQ99", project_id=self.project_standard.id
        )
        subscriptions_service.subscribe_to_sequence(
            person_id, str(other_sequence.id), task_type_id
        )

        result = subscriptions_service.get_all_sequence_subscriptions(
            person_id, str(self.project.id), task_type_id
        )
        self.assertEqual(result, [self.sequence_dict["id"]])

    def test_get_subscriptions_for_project(self):
        """
        Task subscriptions of one production. A sequence subscription
        carries no task, so it is not one of these.
        """
        subscriptions_service.subscribe_to_task(
            self.outsider_id, self.task_dict["id"]
        )
        subscriptions_service.subscribe_to_sequence(
            self.outsider_id,
            self.sequence_dict["id"],
            self.task_type_dict["id"],
        )
        self.generate_fixture_project_standard()
        other_task = self.generate_fixture_shot_task_standard()
        subscriptions_service.subscribe_to_task(
            self.outsider_id, str(other_task.id)
        )

        result = subscriptions_service.get_subscriptions_for_project(
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
            subscriptions_service.subscribe_to_task(self.admin_id, task_id)
        # Someone else's subscriptions must not show up, on this task or
        # on one the caller never subscribed to.
        other_asset_task = self.generate_fixture_task(name="other asset task")
        for task_id in [str(asset_task.id), str(other_asset_task.id)]:
            subscriptions_service.subscribe_to_task(self.outsider_id, task_id)

        # The caller comes from the request context, which a service test
        # has none of.
        with patch.object(
            notifications_service.persons_service,
            "get_current_user",
            return_value=self.user,
        ):
            self.assertEqual(
                subscriptions_service.get_subscriptions_for_user(
                    str(self.project.id)
                ),
                {str(asset_task.id): True},
            )
            self.assertEqual(
                subscriptions_service.get_subscriptions_for_user(
                    str(self.project.id),
                    entity_type_id=str(self.shot_type.id),
                ),
                {shot_task_id: True},
            )

            self.generate_fixture_project_standard()
            self.assertEqual(
                subscriptions_service.get_subscriptions_for_user(
                    str(self.project_standard.id)
                ),
                {},
            )
            self.assertEqual(
                subscriptions_service.get_subscriptions_for_user(None), {}
            )
