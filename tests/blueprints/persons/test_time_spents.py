from tests.base import ApiDBTestCase


class PersonTimeSpentsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_person()

        self.generate_fixture_task()
        task_id = str(self.task.id)

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

    def _log_time_on_another_project(self):
        from zou.app.models.project import Project
        from zou.app.models.task import Task

        other = Project.create(
            name="Other", project_status_id=self.open_status.id
        )
        other_task = Task.create(
            name="Other",
            project_id=other.id,
            task_type_id=self.task_type.id,
            task_status_id=self.task_status.id,
            entity_id=self.asset.id,
            assignees=[self.person],
        )
        self.post(
            f"/actions/tasks/{other_task.id}/time-spents/2018-06-05/persons/{self.person_id}",
            {"duration": 100},
        )

    def _get_range(self, code=200):
        return self.get(
            f"/data/persons/{self.person_id}/time-spents"
            "?start_date=2018-06-01&end_date=2018-06-30",
            code,
        )

    def test_range_for_a_manager_is_scoped_to_their_projects(self):
        from zou.app.services import projects_service

        self._log_time_on_another_project()
        manager = self.generate_fixture_user_manager()
        self.log_in_manager()
        self.assertEqual(self._get_range(), [])

        projects_service.add_team_member(self.project.id, manager["id"])
        entries = self._get_range()
        self.assertEqual(len(entries), 3)
        self.assertEqual(
            {entry["project_id"] for entry in entries},
            {str(self.project.id)},
        )

    def test_range_for_a_supervisor_is_scoped_to_their_departments(self):
        from zou.app.services import persons_service, projects_service

        supervisor = self.generate_fixture_user_supervisor()
        projects_service.add_team_member(self.project.id, supervisor["id"])
        persons_service.add_to_department(
            str(self.department_animation.id), supervisor["id"]
        )
        self.log_in_supervisor()
        entries = self._get_range()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["duration"], 300)
        self.assertEqual(
            entries[0]["task_type_id"], str(self.task_type_animation.id)
        )

    def test_range_is_forbidden_to_an_artist_on_someone_else(self):
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self._get_range(403)

    def test_range_gives_everything_to_the_person_themselves(self):
        self._log_time_on_another_project()
        self.log_in(self.person.email)
        self.assertEqual(len(self._get_range()), 4)
