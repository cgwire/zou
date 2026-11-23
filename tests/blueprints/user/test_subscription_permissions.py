from tests.base import ApiDBTestCase
from zou.app.services import projects_service, tasks_service


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


class VendorSubscriptionTestCase(ApiDBTestCase):
    """
    A vendor reaches only the entities holding one of their tasks, and
    follows only the tasks they reach.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.vendor_id = str(self.generate_fixture_user_vendor()["id"])
        projects_service.add_team_member(str(self.project.id), self.vendor_id)
        self.log_in_vendor()

    def test_a_vendor_subscribes_only_to_a_task_they_reach(self):
        path = f"/actions/user/tasks/{self.task.id}/subscribe"
        many = "/actions/user/tasks/subscribe"
        body = {"task_ids": [str(self.task.id)]}
        self.post(path, {}, 403)
        self.post(many, body, 403)

        tasks_service.assign_task(self.task.id, self.vendor_id)
        self.post(path, {}, 201)
        self.post(many, body, 201)
