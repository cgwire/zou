from tests.base import ApiDBTestCase


class PersonTimeSpentsTestCase(ApiDBTestCase):
    def setUp(self):
        super(PersonTimeSpentsTestCase, self).setUp()
        self.generate_fixture_person()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_assigner()

        self.generate_fixture_task()
        task_id = str(self.task.id)

        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        shot_task_id = str(self.shot_task.id)

        # Storing the person_id because the Person object is not bound to a
        # session and throws a DetachedInstanceError when the id is accessed
        # later.
        self.person_id = str(self.person.id)

        self.post(
            f"/actions/tasks/{task_id}/time-spents/2018-06-04/persons/{self.person_id}",
            {"duration": 500},
        )
        self.post(
            f"/actions/tasks/{shot_task_id}/time-spents/2018-06-04/persons/{self.person_id}",
            {"duration": 300},
        )
        self.post(
            f"/actions/tasks/{task_id}/time-spents/2018-06-03/persons/{self.person_id}",
            {"duration": 600},
        )

    def test_get_time_spents(self):
        time_spents = self.get(
            f"/data/persons/{self.person_id}/time-spents/2018-06-04"
        )
        duration = 0
        for time_spent in time_spents:
            duration += time_spent["duration"]

        self.assertEqual(len(time_spents), 2)
        self.assertEqual(duration, 800)

    def test_get_all_month_time_spents(self):
        time_spents = self.get(
            f"/data/persons/{self.person_id}/time-spents/month/all/2018/06"
        )
        duration = sum([ts["duration"] for ts in time_spents])

        self.assertEqual(len(time_spents), 3)
        self.assertEqual(duration, 1400)
