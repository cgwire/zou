from tests.base import ApiDBTestCase


class NonMemberSubscriptionTestCase(ApiDBTestCase):
    """
    A subscriber receives the notifications and comment emails of the
    task, so subscribing must require access to its production. The
    supervisor fixture is not in the team.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_user_supervisor()
        self.log_in_supervisor()

    def test_non_member_cannot_subscribe_to_task(self):
        self.post(f"/actions/user/tasks/{self.task.id}/subscribe", {}, 403)

    def test_non_member_cannot_subscribe_to_tasks(self):
        self.post(
            "/actions/user/tasks/subscribe",
            {"task_ids": [str(self.task.id)]},
            403,
        )

    def test_non_member_cannot_subscribe_to_sequence(self):
        self.post(
            f"/actions/user/sequences/{self.sequence.id}"
            f"/task-types/{self.task_type.id}/subscribe",
            {},
            403,
        )
