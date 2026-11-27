from tests.base import ApiDBTestCase


class RouteTimeSpentTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_person()
        self.generate_fixture_task()

    def test_set_time_spent(self):
        data = {"duration": 3600}
        self.post(
            f"/actions/tasks/{self.task.id}/time-spents/2017-09-23/persons/{self.person.id}",
            data,
        )
        time_spents = self.get("data/time-spents")
        self.assertEqual(time_spents[0]["date"], "2017-09-23")
        self.assertEqual(len(time_spents), 1)
        self.assertEqual(time_spents[0]["duration"], data["duration"])

    def test_set_time_spent_wrong_date(self):
        data = {"duration": 3600}
        self.post(
            f"/actions/tasks/{self.task.id}/time-spents/wrong-date/persons/{self.person.id}",
            data,
            400,
        )

    def test_admin_sets_time_of_someone_not_assigned(self):
        user_id = str(self.user["id"])
        task_id = str(self.task.id)

        data = {"duration": 7200}
        path = f"/actions/tasks/{task_id}/time-spents/2017-09-27/persons/{user_id}"
        self.post(path, data, 201)
        self.delete(path, 200)

    def test_get_time_spent(self):
        person_id = str(self.person.id)
        user_id = str(self.user["id"])
        task_id = str(self.task.id)
        data = {"duration": 3600}
        path = f"/actions/tasks/{task_id}/time-spents/2017-09-27/persons/{person_id}"
        self.post(path, data)

        self.assign_task(task_id, user_id)
        data = {"duration": 7200}
        path = f"/actions/tasks/{task_id}/time-spents/2017-09-27/persons/{user_id}"
        self.post(path, data)

        time_spents = self.get(
            f"/actions/tasks/{task_id}/time-spents/2017-09-27/"
        )
        self.assertEqual(time_spents["total"], 10800)
        self.assertEqual(time_spents[user_id][0]["duration"], 7200)
        self.assertEqual(time_spents[person_id][0]["duration"], 3600)

    def test_add_time_spent(self):
        person_id = str(self.person.id)
        task_id = str(self.task.id)

        data = {"duration": 3600}
        self.post(
            f"/actions/tasks/{task_id}/time-spents/2017-09-23/persons/{person_id}",
            data,
        )

        data = {"duration": 10800}
        self.post(
            f"/actions/tasks/{task_id}/time-spents/2017-09-23/persons/{person_id}/add",
            data,
        )
        time_spents = self.get("data/time-spents")
        self.assertEqual(time_spents[0]["duration"], 14400)
        self.assertEqual(time_spents[0]["date"], "2017-09-23")
        self.assertEqual(len(time_spents), 1)
