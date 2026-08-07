from tests.base import ApiDBTestCase

from zou.app import db
from zou.app.models.studio import Studio
from zou.app.services import tasks_service, time_spents_service
from zou.app.services.exception import WrongDateFormatException


class TimeSpentsTestCase(ApiDBTestCase):
    """
    One person logging hours on an asset task and on a shot task of the
    same production, over two months of 2018 and the first days of 2019,
    plus the admin logging on the asset task. The two tasks belong to
    different departments and the shot hangs under a sequence, so every
    scoped or breadcrumbed reading has something to reject.

    Holds no test of its own.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_person()
        self.person_id = str(self.person.id)
        self.user_id = self.user["id"]

        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_task_type()
        self.generate_fixture_task()
        self.task_id = str(self.task.id)

        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        self.shot_task_id = str(self.shot_task.id)

        # Asset task, Shaders, Modeling department.
        self.log(self.task_id, "2018-05-03", 600)
        self.log(self.task_id, "2018-06-03", 600)
        self.log(self.task_id, "2018-06-04", 500)
        self.log(self.task_id, "2019-01-02", 850)
        # Shot task, Animation department.
        self.log(self.shot_task_id, "2018-06-04", 300)
        # The admin, on the asset task.
        self.log(self.task_id, "2018-06-03", 600, person_id=self.user_id)

    def log(self, task_id, date, duration, person_id=None):
        return tasks_service.create_or_update_time_spent(
            task_id, person_id or self.person_id, date, duration
        )

    def in_another_project(self, date, duration):
        """
        Log the same person on a task of another production, so that a
        reading scoped to one production has something to leave out.
        """
        self.generate_fixture_project_standard()
        self.generate_fixture_asset_standard()
        self.generate_fixture_task_standard()
        self.log(str(self.task_standard.id), date, duration)
        return self.project_standard


class TimeSpentTableTestCase(TimeSpentsTestCase):
    """
    The tables behind the time sheet screens: durations summed by person,
    laid out by year, month, week or day.
    """

    def test_time_spents_add_up_on_the_task(self):
        task = tasks_service.get_task(self.task_id)
        self.assertEqual(task["duration"], 3150)

    def test_get_year_table(self):
        year_table = time_spents_service.get_year_table()
        self.assertEqual(year_table["2018"][self.person_id], 2000)
        self.assertEqual(year_table["2019"][self.person_id], 850)
        self.assertEqual(year_table["2018"][self.user_id], 600)

    def test_get_month_table(self):
        month_table = time_spents_service.get_month_table("2018")
        self.assertEqual(month_table["5"][self.person_id], 600)
        self.assertEqual(month_table["6"][self.person_id], 1400)
        self.assertEqual(month_table["6"][self.user_id], 600)
        # 2019 belongs to another table, whatever the month.
        self.assertNotIn("1", month_table)

    def test_get_week_table(self):
        week_table = time_spents_service.get_week_table("2018")
        self.assertEqual(week_table["18"][self.person_id], 600)
        self.assertEqual(week_table["22"][self.person_id], 600)
        self.assertEqual(week_table["22"][self.user_id], 600)
        self.assertEqual(week_table["23"][self.person_id], 800)
        self.assertNotIn("1", week_table)

    def test_get_day_table(self):
        day_table = time_spents_service.get_day_table("2018", "06")
        self.assertEqual(day_table["3"][self.person_id], 600)
        self.assertEqual(day_table["4"][self.person_id], 800)
        self.assertEqual(day_table["3"][self.user_id], 600)
        # The 3rd of May is in another table, though it shares the day
        # number with the 3rd of June.
        self.assertEqual(sorted(day_table), ["3", "4"])

    def test_get_day_table_of_a_month_that_does_not_exist(self):
        self.assertRaises(
            WrongDateFormatException,
            time_spents_service.get_day_table,
            "2018",
            "13",
        )
        self.assertRaises(
            WrongDateFormatException,
            time_spents_service.get_day_table,
            "2018",
            "0",
        )


class TimeSpentScopeTestCase(TimeSpentsTestCase):
    """
    Which hours a reading is allowed to sum. The resources hand these
    filters the caller's own productions and departments, so they carry
    the permission scoping rather than a display preference.
    """

    def test_a_table_scoped_to_one_project(self):
        other_project = self.in_another_project("2018-05-03", 400)
        month_table = time_spents_service.get_month_table(
            "2018", project_id=other_project.id
        )
        self.assertEqual(month_table["5"], {self.person_id: 400})

    def test_a_table_scoped_to_a_list_of_projects(self):
        """
        A manager is scoped to every production they are on at once, so
        the filter is handed a list rather than a single id.
        """
        other_project = self.in_another_project("2018-05-03", 400)
        month_table = time_spents_service.get_month_table(
            "2018", project_id=[str(self.project.id), str(other_project.id)]
        )
        self.assertEqual(month_table["5"][self.person_id], 1000)

    def test_a_table_scoped_to_no_project_at_all(self):
        """
        A manager on no production is handed an empty list, which has to
        read as nothing rather than as everything.
        """
        self.assertEqual(
            time_spents_service.get_month_table("2018", project_id=[]), {}
        )

    def test_a_table_scoped_to_a_department(self):
        """
        A supervisor only reads the hours of their own departments. The
        asset task is in Modeling, the shot task in Animation, and both
        carry hours on the 4th of June.
        """
        month_table = time_spents_service.get_month_table(
            "2018", department_ids=[str(self.department_animation.id)]
        )
        self.assertEqual(month_table["6"], {self.person_id: 300})

    def test_a_table_scoped_to_a_studio(self):
        studio = Studio.create(name="Remote", color="#000000")
        self.person.update({"studio_id": studio.id})
        month_table = time_spents_service.get_month_table(
            "2018", studio_id=str(studio.id)
        )
        # The admin belongs to no studio and drops out.
        self.assertEqual(month_table["6"], {self.person_id: 1400})

    def test_a_table_scoped_to_one_person(self):
        month_table = time_spents_service.get_month_table(
            "2018", person_id=self.user_id
        )
        self.assertEqual(month_table["6"], {self.user_id: 600})

    def test_a_day_table_scoped_to_one_person(self):
        """
        The day table is the only reading that hands the person over to
        the shared scoping helper: the yearly ones filter on it
        themselves. An artist reads their own hours through it.
        """
        day_table = time_spents_service.get_day_table(
            "2018", "6", person_id=self.user_id
        )
        self.assertEqual(day_table, {"3": {self.user_id: 600}})

    def test_entries_scoped_to_one_project(self):
        other_project = self.in_another_project("2018-05-03", 400)
        entries = time_spents_service.get_month_time_spents(
            self.person_id, "2018", "5", project_id=other_project.id
        )
        self.assertEqual(
            [(entry["entity_name"], entry["duration"]) for entry in entries],
            [("Car", 400)],
        )

    def test_entries_scoped_to_a_list_of_projects(self):
        other_project = self.in_another_project("2018-05-03", 400)
        entries = time_spents_service.get_month_time_spents(
            self.person_id,
            "2018",
            "5",
            project_id=[str(self.project.id), str(other_project.id)],
        )
        self.assertEqual(
            sorted(entry["entity_name"] for entry in entries),
            ["Car", "Tree"],
        )

    def test_entries_scoped_to_a_department(self):
        entries = time_spents_service.get_month_time_spents(
            self.person_id,
            "2018",
            "6",
            department_ids=[str(self.department_animation.id)],
        )
        self.assertEqual(
            [(entry["entity_name"], entry["duration"]) for entry in entries],
            [("P01", 300)],
        )


class TimeSpentEntryTestCase(TimeSpentsTestCase):
    """
    The time sheet itself: one line per task, with the breadcrumb needed
    to tell two tasks of the same type apart.
    """

    def test_get_year_time_spents(self):
        entries = time_spents_service.get_year_time_spents(
            self.person_id, 2018
        )
        self.assertEqual(
            sorted(
                (entry["entity_name"], entry["duration"]) for entry in entries
            ),
            [("P01", 300), ("Tree", 1700)],
        )

    def test_get_month_time_spents(self):
        entries = time_spents_service.get_month_time_spents(
            self.person_id, "2018", "5"
        )
        self.assertEqual(
            [(entry["entity_name"], entry["duration"]) for entry in entries],
            [("Tree", 600)],
        )

    def test_get_week_time_spents(self):
        entries = time_spents_service.get_week_time_spents(
            self.person_id, "2018", "18"
        )
        self.assertEqual(
            [(entry["entity_name"], entry["duration"]) for entry in entries],
            [("Tree", 600)],
        )

    def test_get_week_time_spents_first_week_of_the_year(self):
        """
        The 2nd of January 2019 is in the first ISO week of 2019, which
        starts in December 2018.
        """
        entries = time_spents_service.get_week_time_spents(
            self.person_id, "2019", "1"
        )
        self.assertEqual([entry["duration"] for entry in entries], [850])

    def test_get_day_time_spents(self):
        entries = time_spents_service.get_day_time_spents(
            self.person_id, "2018", "5", "3"
        )
        self.assertEqual(
            [(entry["entity_name"], entry["duration"]) for entry in entries],
            [("Tree", 600)],
        )

    def test_an_entry_carries_the_place_of_its_task(self):
        """
        A time sheet line names the same task type on several entities, so
        it carries where the entity sits. The parents are outer joined:
        an asset has none, and this production has no episode.
        """
        entries = time_spents_service.get_day_time_spents(
            self.person_id, "2018", "6", "4"
        )
        by_entity = {entry["entity_name"]: entry for entry in entries}

        shot = by_entity["P01"]
        self.assertEqual(shot["entity_type_name"], "Shot")
        self.assertEqual(shot["sequence_name"], "S01")
        self.assertIsNone(shot["episode_name"])
        self.assertEqual(shot["project_name"], self.project.name)
        self.assertEqual(shot["task_id"], self.shot_task_id)
        self.assertEqual(
            shot["task_type_id"], str(self.task_type_animation.id)
        )

        asset = by_entity["Tree"]
        self.assertEqual(asset["entity_type_name"], "Props")
        self.assertIsNone(asset["sequence_name"])
        self.assertIsNone(asset["episode_name"])


class TimeSpentLookupTestCase(TimeSpentsTestCase):
    """
    The single readings the desktop client and the person pages make.
    """

    def test_get_time_spents(self):
        time_spents = time_spents_service.get_time_spents(
            self.person_id, "2018-06-04"
        )
        self.assertEqual(
            sorted(entry["duration"] for entry in time_spents), [300, 500]
        )

    def test_get_time_spents_scoped_to_a_department(self):
        time_spents = time_spents_service.get_time_spents(
            self.person_id,
            "2018-06-04",
            department_ids=[str(self.department_animation.id)],
        )
        self.assertEqual([entry["duration"] for entry in time_spents], [300])

    def test_get_time_spents_scoped_to_no_project_at_all(self):
        self.assertEqual(
            time_spents_service.get_time_spents(
                self.person_id, "2018-06-04", project_ids=[]
            ),
            [],
        )

    def test_get_time_spents_range(self):
        time_spents = time_spents_service.get_time_spents_range(
            self.person_id, "2018-06-01", "2018-06-30"
        )
        self.assertEqual(len(time_spents), 3)

    def test_get_time_spents_range_takes_both_bounds(self):
        time_spents = time_spents_service.get_time_spents_range(
            self.person_id, "2018-06-03", "2018-06-04"
        )
        self.assertEqual(
            sorted(entry["date"] for entry in time_spents),
            ["2018-06-03", "2018-06-04", "2018-06-04"],
        )

    def test_get_time_spent(self):
        result = time_spents_service.get_time_spent(
            self.person_id, self.task_id, "2018-06-04"
        )
        self.assertEqual(result["duration"], 500)

    def test_get_time_spent_not_found(self):
        self.assertIsNone(
            time_spents_service.get_time_spent(
                self.person_id, self.task_id, "2020-01-01"
            )
        )

    def test_get_time_spents_for_entity(self):
        """
        Newest first: the route builds a history panel from this.
        """
        time_spents = time_spents_service.get_time_spents_for_entity(
            self.asset.id
        )
        self.assertEqual(
            [entry["date"] for entry in time_spents],
            [
                "2019-01-02",
                "2018-06-04",
                "2018-06-03",
                "2018-06-03",
                "2018-05-03",
            ],
        )

    def test_a_date_the_driver_refuses_is_a_wrong_date_format(self):
        """
        These readings cast the date in SQL, so a value the driver refuses
        only surfaces when the query runs, and the resources answer a 400
        on it. Each failed statement leaves the transaction to be rolled
        back before the next reading, which throws away the fixtures with
        it: the ids are read once, up front, rather than off a row that
        is about to be detached.
        """
        project_id = str(self.project.id)
        task_type_id = str(self.task_type.id)
        readings = {
            "time spents of a day": lambda: time_spents_service.get_time_spents(
                self.person_id, "not-a-date"
            ),
            "time spents of a range": lambda: time_spents_service.get_time_spents_range(
                self.person_id, "not-a-date", "not-a-date"
            ),
            "time spent of a task": lambda: time_spents_service.get_time_spent(
                self.person_id, self.task_id, "not-a-date"
            ),
            "day off of a day": lambda: time_spents_service.get_day_off(
                self.person_id, "not-a-date"
            ),
            "time spents of a task type": lambda: time_spents_service.get_project_task_type_time_spents(
                project_id, task_type_id, "not-a-date", None
            ),
        }
        for name, reading in readings.items():
            with self.subTest(reading=name):
                self.assertRaises(WrongDateFormatException, reading)
            db.session.rollback()


class DayOffTestCase(TimeSpentsTestCase):
    """
    Day offs are read by period, and a period must not carry the first day
    of the next one.
    """

    def test_get_day_off(self):
        self.generate_fixture_day_off("2021-05-10", "2021-05-12")
        # Read from inside the period, not only on its first day.
        result = time_spents_service.get_day_off(self.person_id, "2021-05-11")
        self.assertEqual(result["id"], str(self.day_off.id))

    def test_get_day_off_empty(self):
        self.generate_fixture_day_off("2021-05-10")
        self.assertEqual(
            time_spents_service.get_day_off(self.person_id, "2021-05-11"), {}
        )

    def test_get_day_offs_for_month(self):
        self.generate_fixture_day_off("2021-01-10")
        self.generate_fixture_day_off("2021-02-10")
        self.generate_fixture_day_off("2021-02-11")
        day_offs = time_spents_service.get_day_offs_for_month(2021, 2)
        self.assertEqual(len(day_offs), 2)

        # A period overlapping the month counts, even started before it.
        self.generate_fixture_day_off("2021-01-28", "2021-02-02")
        day_offs = time_spents_service.get_day_offs_for_month(2021, 2)
        self.assertEqual(len(day_offs), 3)

    def test_a_month_stops_before_the_first_day_of_the_next_one(self):
        """
        The interval helpers end on the first day of the next period,
        while the reading takes its end inclusively. Handing the raw end
        over would make February carry the 1st of March.
        """
        self.generate_fixture_day_off("2021-03-01")
        self.assertEqual(
            time_spents_service.get_day_offs_for_month(2021, 2), []
        )
        self.assertEqual(
            len(time_spents_service.get_day_offs_for_month(2021, 3)), 1
        )

    def test_get_person_day_offs(self):
        self.generate_fixture_day_off("2021-01-10", "2021-01-12")
        self.generate_fixture_day_off("2021-02-10")
        self.generate_fixture_day_off("2021-02-11")
        self.generate_fixture_day_off("2021-03-10")
        self.generate_fixture_user_cg_artist()
        self.generate_fixture_day_off(
            "2021-02-10", person_id=self.user_cg_artist["id"]
        )

        self.assertEqual(
            len(
                time_spents_service.get_person_day_offs_for_year(
                    self.person_id, 2021
                )
            ),
            4,
        )
        self.assertEqual(
            len(
                time_spents_service.get_person_day_offs_for_month(
                    self.person_id, 2021, 2
                )
            ),
            2,
        )
        self.assertEqual(
            len(
                time_spents_service.get_person_day_offs_for_week(
                    self.person_id, 2021, 6
                )
            ),
            2,
        )

    def test_get_day_offs_between(self):
        # Created out of order, to pin that the reading is by date.
        self.generate_fixture_day_off("2021-03-15")
        self.generate_fixture_day_off("2021-03-01")
        result = time_spents_service.get_day_offs_between(
            "2021-03-01", "2021-03-31", person_id=self.person_id
        )
        self.assertEqual(
            [day_off["date"] for day_off in result],
            ["2021-03-01", "2021-03-15"],
        )

    def test_get_day_offs_between_excluding_one(self):
        """
        The overlap guard of the day off resource asks whether a period is
        free, while the row being updated is still stored: it is excluded
        so that a day off does not collide with itself.
        """
        self.generate_fixture_day_off("2021-03-01", "2021-03-05")
        result = time_spents_service.get_day_offs_between(
            "2021-03-01",
            "2021-03-31",
            person_id=self.person_id,
            exclude_id=self.day_off.id,
        )
        self.assertEqual(result, [])


class ProjectTimeSpentTestCase(TimeSpentsTestCase):
    """
    The production side of the readings: hours of a whole team, grouped
    by what a producer looks at.
    """

    def test_get_day_offs_between_for_project(self):
        """
        The day offs of the whole team, grouped by person and ordered by
        date. The reason for a day off is someone else's business: only the
        caller's own entries carry their description.
        """
        self.generate_fixture_day_off("2021-03-15")
        self.generate_fixture_day_off("2021-03-01")
        self.day_off.update({"description": "moving out"})

        result = time_spents_service.get_day_offs_between_for_project(
            str(self.project.id), "2021-03-01", "2021-03-31"
        )

        day_offs = result[self.person_id]
        self.assertEqual(
            [day_off["date"] for day_off in day_offs],
            ["2021-03-01", "2021-03-15"],
        )
        self.assertNotIn("description", day_offs[0])

        result = time_spents_service.get_day_offs_between_for_project(
            str(self.project.id),
            "2021-03-01",
            "2021-03-31",
            current_user_id=self.person_id,
        )
        self.assertEqual(
            result[self.person_id][0]["description"], "moving out"
        )

    def test_only_the_team_of_the_project_is_read(self):
        """
        The reading is scoped to the team of the production, not to the
        dates alone. generate_fixture_shot_task put the person on the
        team; the cg artist is on no production.
        """
        self.generate_fixture_user_cg_artist()
        self.generate_fixture_day_off(
            "2021-03-01", person_id=self.user_cg_artist["id"]
        )
        self.generate_fixture_day_off("2021-03-02")
        result = time_spents_service.get_day_offs_between_for_project(
            str(self.project.id), "2021-03-01", "2021-03-31"
        )
        self.assertEqual(list(result), [self.person_id])

    def test_get_project_month_time_spents(self):
        """
        Durations by department, by person, by month, with a running total
        at each level.
        """
        # The same person logging time in another production must not add
        # to these totals.
        self.in_another_project("2018-06-04", 9999)

        result = time_spents_service.get_project_month_time_spents(
            str(self.project.id)
        )
        # The keys are the raw ids the query returns, not strings.
        person = result[self.task_type.department_id][self.person.id]
        self.assertEqual(person["2018-05"], 600)
        self.assertEqual(person["2018-06"], 1100)
        self.assertEqual(person["2019-01"], 850)
        self.assertEqual(person["total"], 2550)

        # The department total sums its people: this person plus the admin,
        # who logged 600 on a task of the same department.
        department = result[self.task_type.department_id]
        per_person = [
            entry["total"]
            for key, entry in department.items()
            if key != "total"
        ]
        self.assertEqual(sorted(per_person), [600, 2550])
        self.assertEqual(department["total"], 3150)

        # The shot task sits in another department, told apart from the
        # asset one rather than folded into it.
        animation = result[self.task_type_animation.department_id]
        self.assertEqual(animation["total"], 300)

    def test_get_project_task_type_time_spents(self):
        """
        Every entry of one task type in a date range, grouped by person.
        """
        result = time_spents_service.get_project_task_type_time_spents(
            str(self.project.id),
            str(self.task_type.id),
            "2018-01-01",
            "2018-12-31",
        )
        self.assertEqual(
            [entry["date"] for entry in result[self.person_id]],
            ["2018-06-04", "2018-06-03", "2018-05-03"],
        )
        self.assertEqual(
            [entry["duration"] for entry in result[self.user_id]], [600]
        )

    def test_get_project_task_type_time_spents_without_bounds(self):
        """
        Both bounds are optional: the person page reads a whole history
        with neither of them.
        """
        result = time_spents_service.get_project_task_type_time_spents(
            str(self.project.id), str(self.task_type.id), None, None
        )
        self.assertEqual(
            [entry["date"] for entry in result[self.person_id]][0],
            "2019-01-02",
        )

    def test_get_project_task_type_time_spents_of_another_task_type(self):
        result = time_spents_service.get_project_task_type_time_spents(
            str(self.project.id),
            str(self.task_type_animation.id),
            None,
            None,
        )
        self.assertEqual(
            [entry["duration"] for entry in result[self.person_id]], [300]
        )
