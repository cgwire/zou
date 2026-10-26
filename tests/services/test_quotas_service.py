import datetime

from freezegun import freeze_time

from tests.services.cases import ShotsTestCase
from zou.app.models.person import Person
from zou.app.models.task import Task
from zou.app.services import (
    quotas_service,
    tasks_service,
    time_spents_service,
)
from zou.app.utils import fields


class QuotaTestCase(ShotsTestCase):
    """
    How much a person drew over a period. Every shot counted lands in four
    buckets at once.
    """

    def test_the_entries_add_up_by_day_week_month_and_year(self):
        """
        Shots sharing a period add up. The entries counters are distinct
        period counts: how many days a month holds, how many weeks and
        months a year does, which is why two days in January are needed to
        tell a sum from an assignment.
        """
        quotas = {}
        counted = [
            (datetime.datetime(2024, 1, 8), 100, 3),
            (datetime.datetime(2024, 1, 8), 50, 2),
            (datetime.datetime(2024, 1, 9), 25, 1),
            (datetime.datetime(2024, 2, 5), 75, 4),
        ]
        for date, nb_frames, nb_drawings in counted:
            quotas_service._add_quota_entry(
                quotas, "person", date, "UTC", nb_frames, nb_drawings, 25
            )

        entry = quotas["person"]
        self.assertEqual(
            entry["day"],
            {
                "frames": {
                    "2024-01-08": 150,
                    "2024-01-09": 25,
                    "2024-02-05": 75,
                },
                "seconds": {
                    "2024-01-08": 6,
                    "2024-01-09": 1,
                    "2024-02-05": 3,
                },
                "count": {"2024-01-08": 2, "2024-01-09": 1, "2024-02-05": 1},
                "drawings": {
                    "2024-01-08": 5,
                    "2024-01-09": 1,
                    "2024-02-05": 4,
                },
                "entries": {"2024-01": 2, "2024-02": 1},
            },
        )
        self.assertEqual(
            entry["week"],
            {
                "frames": {"2024-2": 175, "2024-6": 75},
                "seconds": {"2024-2": 7, "2024-6": 3},
                "count": {"2024-2": 3, "2024-6": 1},
                "drawings": {"2024-2": 6, "2024-6": 4},
                "entries": {"2024": 2},
            },
        )
        self.assertEqual(
            entry["month"],
            {
                "frames": {"2024-01": 175, "2024-02": 75},
                "seconds": {"2024-01": 7, "2024-02": 3},
                "count": {"2024-01": 3, "2024-02": 1},
                "drawings": {"2024-01": 6, "2024-02": 4},
                "entries": {"2024": 2},
            },
        )
        self.assertEqual(
            entry["year"],
            {
                "frames": {"2024": 250},
                "seconds": {"2024": 10},
                "count": {"2024": 4},
                "drawings": {"2024": 10},
            },
        )

    def test_a_time_spent_day_is_not_shifted_by_the_timezone(self):
        """
        A time spent is logged against a calendar day, not an instant:
        west of UTC it must stay on the day the artist picked instead of
        sliding to the previous one.
        """
        quotas = {}
        quotas_service._add_quota_entry(
            quotas,
            "person",
            datetime.date(2024, 1, 8),
            "America/New_York",
            100,
            2,
            25,
        )
        self.assertEqual(
            quotas["person"]["day"]["frames"], {"2024-01-08": 100}
        )

    def test_an_end_date_lands_on_the_local_day_and_week(self):
        """
        End dates are UTC instants: a feedback given Sunday evening UTC is
        Monday in Kuala Lumpur, and the week bucket must follow that local
        day or the day and week totals disagree.
        """
        quotas = {}
        quotas_service._add_quota_entry(
            quotas,
            "person",
            datetime.datetime(2024, 12, 15, 18, 0),
            "Asia/Kuala_Lumpur",
            100,
            2,
            25,
        )
        entry = quotas["person"]
        self.assertEqual(entry["day"]["frames"], {"2024-12-16": 100})
        self.assertEqual(entry["week"]["frames"], {"2024-51": 100})

    def test_the_day_list_agrees_with_the_day_the_shot_is_counted_on(self):
        """
        The issue 1612 symptom: the aggregate counted a shot on the right
        local day but the day detail list queried the raw UTC day, so the
        shot was missing from the list. A feedback at 18:00 UTC is the
        17th in Kuala Lumpur: the 17th's list must hold it, the 16th's
        must not.
        """
        self.generate_shot_task()
        task = self.generate_fixture_shot_task(
            name="quota", shot_id=self.shot.id
        )
        task.update(
            {
                "end_date": fields.get_date_object(
                    "2024-12-16T18:00:00", "%Y-%m-%dT%H:%M:%S"
                )
            }
        )
        args = dict(
            project_id=str(self.project.id),
            task_type_id=str(self.task_type_animation.id),
            weighted=False,
            timezone="Asia/Kuala_Lumpur",
        )

        counted_day = quotas_service.get_day_quota_shots(
            str(self.person.id), 2024, 12, 17, **args
        )
        wrong_day = quotas_service.get_day_quota_shots(
            str(self.person.id), 2024, 12, 16, **args
        )

        self.assertEqual([shot["name"] for shot in counted_day], ["P01"])
        self.assertEqual(wrong_day, [])

    def test_a_shot_is_weighted_by_the_share_of_the_task_it_took(self):
        """
        The shots a person worked on in the window, weighted by the share of
        the task duration they logged, and returned in full name order.
        """
        self.generate_shot_task()

        # Named to come first while created last, so the sort has work to
        # do. generate_fixture_shot repoints self.shot, hence the local.
        first_shot = self.shot
        shots = [first_shot, self.generate_fixture_shot("A01")]
        tasks = {}
        for shot in shots:
            task = self.generate_fixture_shot_task(
                name=f"quota {shot.name}", shot_id=shot.id
            )
            task.update({"end_date": fields.get_date_object("2018-06-10")})
            # The task duration is the sum of every time spent on it, so a
            # second worker is what makes the share below one.
            time_spents_service.create_or_update_time_spent(
                str(task.id), str(self.person.id), "2018-06-04", 250
            )
            time_spents_service.create_or_update_time_spent(
                str(task.id), self.user["id"], "2018-06-04", 750
            )
            tasks[shot.name] = task

        # A second day logged on one shot, for the same duration as the
        # first: the two shares have to add up rather than the last one
        # winning, and the rows must stay apart even though everything the
        # query selects of them is equal.
        time_spents_service.create_or_update_time_spent(
            str(tasks["A01"].id), str(self.person.id), "2018-06-05", 250
        )

        quota_shots = quotas_service.get_weighted_quota_shots_between(
            str(self.person.id),
            "2018-06-01T00:00:00",
            "2018-06-30T00:00:00",
            project_id=str(self.project.id),
            task_type_id=str(self.task_type_animation.id),
        )

        self.assertEqual(
            [(shot["name"], shot["weight"]) for shot in quota_shots],
            [("A01", 0.4), ("P01", 0.25)],
        )

    def test_a_shot_logged_whole_in_the_window_weighs_one(self):
        """
        Three days of the same length make the whole task: rounded one by
        one, their shares added up to 0.99.
        """
        task = self.generate_shot_task()
        task.update({"end_date": fields.get_date_object("2018-06-10")})
        for day in ["2018-06-04", "2018-06-05", "2018-06-06"]:
            time_spents_service.create_or_update_time_spent(
                str(task.id), str(self.person.id), day, 480
            )

        quota_shots = quotas_service.get_weighted_quota_shots_between(
            str(self.person.id),
            "2018-06-01T00:00:00",
            "2018-06-30T00:00:00",
            project_id=str(self.project.id),
            task_type_id=str(self.task_type_animation.id),
        )

        self.assertEqual(
            [(shot["name"], shot["weight"]) for shot in quota_shots],
            [("P01", 1.0)],
        )

    def test_a_shot_outside_the_window_is_not_counted(self):
        self.generate_shot_task()
        task = self.generate_fixture_shot_task(
            name="quota", shot_id=self.shot.id
        )
        task.update({"end_date": fields.get_date_object("2018-06-10")})
        time_spents_service.create_or_update_time_spent(
            str(task.id), str(self.person.id), "2018-06-04", 250
        )

        self.assertEqual(
            quotas_service.get_weighted_quota_shots_between(
                str(self.person.id),
                "2018-07-01T00:00:00",
                "2018-07-30T00:00:00",
                project_id=str(self.project.id),
                task_type_id=str(self.task_type_animation.id),
            ),
            [],
        )

    def test_a_logged_task_without_duration_is_left_out(self):
        """
        A manager can set the duration of a task to 0, or to null, once
        time was logged on it. The list divided each time spent by it and
        failed, and a null duration failed the quotas too: both leave such
        a task out.
        """
        task = self.generate_shot_task()
        task.update({"end_date": datetime.datetime(2024, 6, 5, 10, 0)})
        time_spents_service.create_or_update_time_spent(
            str(task.id), str(self.person.id), "2024-06-04", 120
        )

        for duration in [0, None]:
            with self.subTest(duration=duration):
                task.update({"duration": duration})
                quota_shots = quotas_service.get_week_quota_shots(
                    str(self.person.id),
                    2024,
                    23,
                    project_id=str(self.project.id),
                    task_type_id=str(self.task_type_animation.id),
                    timezone="Europe/Paris",
                )
                quotas = quotas_service.get_weighted_quotas(
                    str(self.project.id), str(self.task_type_animation.id)
                )
                self.assertEqual(quota_shots, [])
                self.assertEqual(quotas, {})

    def a_shot_without_time_spent(self, start_date, end_date):
        """
        The shot task of the person, worked from start_date to end_date
        with no time spent logged on it.
        """
        task = self.generate_shot_task()
        task.update({"real_start_date": start_date, "end_date": end_date})
        return task

    def test_a_shot_weighs_its_working_days_in_the_week(self):
        """
        Worked from Monday 3 to Friday 14 June 2024, ten working days, a
        shot weighs half in the week of the 3rd, sent to feedback or
        approved. The bounds of a week are dates, not datetimes: comparing
        them with the task dates raised.
        """
        task = self.a_shot_without_time_spent(
            datetime.datetime(2024, 6, 3, 10, 0),
            datetime.datetime(2024, 6, 14, 10, 0),
        )
        task.update({"done_date": datetime.datetime(2024, 6, 14, 10, 0)})

        for feedback in [True, False]:
            with self.subTest(feedback=feedback):
                quota_shots = quotas_service.get_week_quota_shots(
                    str(self.person.id),
                    2024,
                    23,
                    project_id=str(self.project.id),
                    task_type_id=str(self.task_type_animation.id),
                    feedback=feedback,
                    timezone="Europe/Paris",
                )
                self.assertEqual(
                    [(shot["name"], shot["weight"]) for shot in quota_shots],
                    [("P01", 0.5)],
                )

    def test_a_task_longer_than_the_period_weighs_its_days_in_it(self):
        """
        Worked from 6 May to 26 July 2024, sixty working days of which June
        holds twenty: a third of the shot. It weighed one day out of sixty.
        """
        self.a_shot_without_time_spent(
            datetime.datetime(2024, 5, 6, 10, 0),
            datetime.datetime(2024, 7, 26, 10, 0),
        )

        quota_shots = quotas_service.get_month_quota_shots(
            str(self.person.id),
            2024,
            6,
            project_id=str(self.project.id),
            task_type_id=str(self.task_type_animation.id),
            timezone="Europe/Paris",
        )

        self.assertEqual(
            [(shot["name"], shot["weight"]) for shot in quota_shots],
            [("P01", 0.33)],
        )

    def test_a_spread_keeps_the_whole_amount(self):
        self.assertEqual(quotas_service._spread(10, 3), [3, 3, 4])
        self.assertEqual(quotas_service._spread(100, 5), [20] * 5)
        self.assertEqual(
            quotas_service._spread(5, 11), [0, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1]
        )

    def test_time_spent_shares_keep_the_whole_amount(self):
        self.assertEqual(
            quotas_service._share_out(10, [120, 120, 120], 360), [3, 4, 3]
        )
        self.assertEqual(
            quotas_service._share_out(10, [80, 80, 340], 500), [2, 1, 7]
        )
        # The two middle time spents make half of the task, 5 frames:
        # rounded half to even, the running sum would give them 6.
        self.assertEqual(
            quotas_service._share_out(10, [480] * 4, 1920), [3, 2, 3, 2]
        )
        # 30 minutes out of 148.8 make 12.5 of the 62 frames, computed a
        # hair below: the first time spent still gets 13, the second 16.
        self.assertEqual(
            quotas_service._share_out(62, [30, 38.4, 80.4], 148.8),
            [13, 16, 33],
        )
        # Two time spents of half the task add up to the 7 frames.
        self.assertEqual(quotas_service._share_out(7, [300, 300], 600), [4, 3])

    def test_the_working_days_are_calendar_days_of_the_user(self):
        """
        A task set to WIP on Tuesday 09:30 in Sydney, Monday 23:30 in UTC,
        and ended on Wednesday 08:00, Tuesday 22:00 in UTC: its working
        days are the Tuesday and the Wednesday of Sydney.
        """
        days = quotas_service._get_working_days(
            datetime.datetime(2026, 9, 14, 23, 30),
            datetime.datetime(2026, 9, 15, 22, 0),
            "Australia/Sydney",
        )
        self.assertEqual(
            days, [datetime.date(2026, 9, 15), datetime.date(2026, 9, 16)]
        )

    def test_a_task_run_over_a_weekend_lands_on_its_end_day(self):
        days = quotas_service._get_working_days(
            datetime.datetime(2026, 9, 12, 10, 0),
            datetime.datetime(2026, 9, 13, 10, 0),
            "Europe/Paris",
        )
        self.assertEqual(days, [datetime.date(2026, 9, 13)])

    def test_the_day_list_spreads_a_shot_over_the_days_of_the_user(self):
        """
        The quota-shots routes pass no timezone, so the one of the user
        finds the working days too. Worked from Monday to Thursday 00:30
        in Paris, a shot weighs a quarter on the Thursday.
        """
        self.a_shot_without_time_spent(
            datetime.datetime(2024, 6, 3, 10, 0),
            datetime.datetime(2024, 6, 5, 22, 30),
        )

        quota_shots = quotas_service.get_day_quota_shots(
            str(self.person.id),
            2024,
            6,
            6,
            project_id=str(self.project.id),
            task_type_id=str(self.task_type_animation.id),
        )

        self.assertEqual(
            [(shot["name"], shot["weight"]) for shot in quota_shots],
            [("P01", 0.25)],
        )

    def test_a_task_that_went_wip_after_its_end_weighs_whole_on_it(self):
        """
        A task sent to feedback, or approved, before it went WIP is listed
        whole on its end day, the day the quotas count it on.
        """
        task = self.a_shot_without_time_spent(
            datetime.datetime(2024, 6, 12, 10, 0),
            datetime.datetime(2024, 6, 5, 10, 0),
        )
        task.update({"done_date": datetime.datetime(2024, 6, 5, 10, 0)})

        for feedback in [True, False]:
            with self.subTest(feedback=feedback):
                quota_shots = quotas_service.get_day_quota_shots(
                    str(self.person.id),
                    2024,
                    6,
                    5,
                    project_id=str(self.project.id),
                    task_type_id=str(self.task_type_animation.id),
                    feedback=feedback,
                    timezone="Europe/Paris",
                )
                self.assertEqual(
                    [(shot["name"], shot["weight"]) for shot in quota_shots],
                    [("P01", 1.0)],
                )

    def test_a_task_that_never_went_wip_weighs_whole_on_its_end_day(self):
        self.a_shot_without_time_spent(
            None, datetime.datetime(2024, 6, 5, 10, 0)
        )

        quota_shots = quotas_service.get_day_quota_shots(
            str(self.person.id),
            2024,
            6,
            5,
            project_id=str(self.project.id),
            task_type_id=str(self.task_type_animation.id),
            timezone="Europe/Paris",
        )

        self.assertEqual(
            [(shot["name"], shot["weight"]) for shot in quota_shots],
            [("P01", 1.0)],
        )

    def test_the_list_adds_up_the_tasks_of_a_shot(self):
        """
        Without a task type, a shot holds a task of each type. The list kept
        the first task of a shot only, where the quotas count every task,
        and two tasks worked on the same dates came out of the query as one
        row. Worked from Monday 3 to Friday 7 June, each task weighs a fifth
        of the shot on the 5th.
        """
        self.a_shot_without_time_spent(
            datetime.datetime(2024, 6, 3, 10, 0),
            datetime.datetime(2024, 6, 7, 10, 0),
        )
        layout_task = self.generate_fixture_shot_task(
            name="layout",
            shot_id=self.shot.id,
            task_type_id=self.task_type_layout.id,
        )
        layout_task.update(
            {
                "real_start_date": datetime.datetime(2024, 6, 3, 10, 0),
                "end_date": datetime.datetime(2024, 6, 7, 10, 0),
            }
        )

        quota_shots = quotas_service.get_day_quota_shots(
            str(self.person.id),
            2024,
            6,
            5,
            project_id=str(self.project.id),
            timezone="Europe/Paris",
        )
        quotas = quotas_service.get_weighted_quotas(
            str(self.project.id), person_id=str(self.person.id)
        )

        self.assertEqual(
            [(shot["name"], shot["weight"]) for shot in quota_shots],
            [("P01", 0.4)],
        )
        self.assertEqual(quotas["total"]["day"]["count"]["2024-06-05"], 0.4)

    def test_the_list_rounds_the_weight_of_a_shot_once(self):
        """
        A third of the animation logged on Monday 3 June, and a layout
        worked from Monday to Wednesday without time spent: the shot weighs
        0.67 on the Monday, as in the quotas. Rounded task by task, it would
        weigh 0.66.
        """
        task = self.generate_shot_task()
        task.update({"end_date": datetime.datetime(2024, 6, 5, 10, 0)})
        for day in ["2024-06-03", "2024-06-04", "2024-06-05"]:
            time_spents_service.create_or_update_time_spent(
                str(task.id), str(self.person.id), day, 60
            )
        layout_task = self.generate_fixture_shot_task(
            name="layout",
            shot_id=self.shot.id,
            task_type_id=self.task_type_layout.id,
        )
        layout_task.update(
            {
                "real_start_date": datetime.datetime(2024, 6, 3, 10, 0),
                "end_date": datetime.datetime(2024, 6, 5, 10, 0),
            }
        )

        quota_shots = quotas_service.get_day_quota_shots(
            str(self.person.id),
            2024,
            6,
            3,
            project_id=str(self.project.id),
            timezone="Europe/Paris",
        )
        quotas = quotas_service.get_weighted_quotas(
            str(self.project.id), person_id=str(self.person.id)
        )

        self.assertEqual(
            [(shot["name"], shot["weight"]) for shot in quota_shots],
            [("P01", 0.67)],
        )
        self.assertEqual(quotas["total"]["day"]["count"]["2024-06-03"], 0.67)

    def test_the_list_adds_a_task_without_time_spent_to_a_logged_one(self):
        """
        A shot listed for the time logged on one of its tasks left out its
        other tasks without time spent: the layout below, sent to feedback
        without going WIP, weighs whole on its end day next to the logged
        animation.
        """
        task = self.generate_shot_task()
        task.update({"end_date": datetime.datetime(2024, 6, 5, 10, 0)})
        time_spents_service.create_or_update_time_spent(
            str(task.id), str(self.person.id), "2024-06-05", 60
        )
        layout_task = self.generate_fixture_shot_task(
            name="layout",
            shot_id=self.shot.id,
            task_type_id=self.task_type_layout.id,
        )
        layout_task.update({"end_date": datetime.datetime(2024, 6, 5, 10, 0)})

        quota_shots = quotas_service.get_day_quota_shots(
            str(self.person.id),
            2024,
            6,
            5,
            project_id=str(self.project.id),
            timezone="Europe/Paris",
        )
        quotas = quotas_service.get_weighted_quotas(
            str(self.project.id), person_id=str(self.person.id)
        )

        self.assertEqual(
            [(shot["name"], shot["weight"]) for shot in quota_shots],
            [("P01", 2.0)],
        )
        self.assertEqual(quotas["total"]["day"]["count"]["2024-06-05"], 2)

    def test_the_raw_list_counts_every_task_of_a_shot(self):
        """
        The raw list selected the shots alone, and the legacy Query.all()
        returns each of them once: without a task type, a shot with a
        layout and an animation task done in June weighed 1, where the raw
        quotas count 2. Another assignee on one of the tasks changes nothing
        for the person.
        """
        task = self.generate_shot_task()
        tasks_service.assign_task(str(task.id), self.user["id"])
        layout_task = self.generate_fixture_shot_task(
            name="layout",
            shot_id=self.shot.id,
            task_type_id=self.task_type_layout.id,
        )
        for each, day in [(task, 5), (layout_task, 6)]:
            date = datetime.datetime(2024, 6, day, 10, 0)
            each.update({"end_date": date, "done_date": date})

        for feedback in [True, False]:
            with self.subTest(feedback=feedback):
                quota_shots = quotas_service.get_month_quota_shots(
                    str(self.person.id),
                    2024,
                    6,
                    project_id=str(self.project.id),
                    weighted=False,
                    feedback=feedback,
                    timezone="Europe/Paris",
                )
                quotas = quotas_service.get_raw_quotas(
                    str(self.project.id),
                    person_id=str(self.person.id),
                    feedback=feedback,
                )
                self.assertEqual(
                    [(shot["name"], shot["weight"]) for shot in quota_shots],
                    [("P01", 2)],
                )
                self.assertEqual(
                    quotas["total"]["month"]["count"], {"2024-06": 2}
                )

    def test_the_raw_list_ends_before_its_end_bound(self):
        """
        A task sent to feedback, or approved, at midnight in Paris belongs
        to the day that starts then, where the raw quotas count it. The
        list of the day before held it too, its end bound included.
        """
        task = self.generate_shot_task()
        date = datetime.datetime(2024, 6, 5, 22, 0)
        task.update({"end_date": date, "done_date": date})

        for feedback in [True, False]:
            with self.subTest(feedback=feedback):
                quotas = quotas_service.get_raw_quotas(
                    str(self.project.id),
                    person_id=str(self.person.id),
                    feedback=feedback,
                )
                weights = {}
                for day in [5, 6]:
                    quota_shots = quotas_service.get_day_quota_shots(
                        str(self.person.id),
                        2024,
                        6,
                        day,
                        project_id=str(self.project.id),
                        weighted=False,
                        feedback=feedback,
                        timezone="Europe/Paris",
                    )
                    weights[day] = {
                        shot["name"]: shot["weight"] for shot in quota_shots
                    }
                self.assertEqual(
                    quotas["total"]["day"]["count"], {"2024-06-06": 1}
                )
                self.assertEqual(weights, {5: {}, 6: {"P01": 1}})

    def test_the_lists_hold_the_first_hour_of_a_day_met_twice(self):
        """
        In Havana, clocks go back from 01:00 to 00:00 on Sunday 1 November
        2026. Sent to feedback at 00:30, the first time, a task that never
        went WIP belongs to that Sunday, where the quotas count it. The
        lists started the day at the second midnight: the weighted one left
        the task out, the raw one put it on the Saturday.
        """
        end_date = datetime.datetime(2026, 11, 1, 4, 30)
        self.a_shot_without_time_spent(None, end_date)
        self.assertEqual(
            quotas_service._get_working_days(None, end_date, "America/Havana"),
            [datetime.date(2026, 11, 1)],
        )

        for weighted in [True, False]:
            with self.subTest(weighted=weighted):
                weights = {}
                for month, day in [(10, 31), (11, 1)]:
                    quota_shots = quotas_service.get_day_quota_shots(
                        str(self.person.id),
                        2026,
                        month,
                        day,
                        project_id=str(self.project.id),
                        weighted=weighted,
                        timezone="America/Havana",
                    )
                    weights[day] = {
                        shot["name"]: shot["weight"] for shot in quota_shots
                    }
                self.assertEqual(weights, {31: {}, 1: {"P01": 1}})

    def test_the_working_days_of_a_task_that_never_went_wip(self):
        """
        Without a start date, the task lands on its end day: an absent date
        must not be read as now, so the clock is set before the end day.
        """
        with freeze_time("2026-09-01T12:00:00"):
            days = quotas_service._get_working_days(
                None, datetime.datetime(2026, 9, 9, 10, 0), "Europe/Paris"
            )
        self.assertEqual(days, [datetime.date(2026, 9, 9)])

    def test_a_task_approved_from_todo_weighs_whole_on_its_approval_day(self):
        """
        In the done modes, the end day of a task is its approval day.
        Approved straight from todo, a task never went WIP and has no
        feedback date: it is listed and counted whole on that day.
        """
        task = self.generate_shot_task()
        self.shot.update({"nb_frames": 10})
        task.update({"done_date": datetime.datetime(2024, 6, 12, 10, 0)})

        quota_shots = quotas_service.get_day_quota_shots(
            str(self.person.id),
            2024,
            6,
            12,
            project_id=str(self.project.id),
            task_type_id=str(self.task_type_animation.id),
            feedback=False,
            timezone="Europe/Paris",
        )
        quotas = quotas_service.get_weighted_quotas(
            str(self.project.id),
            str(self.task_type_animation.id),
            feedback=False,
        )

        self.assertEqual(
            [(shot["name"], shot["weight"]) for shot in quota_shots],
            [("P01", 1.0)],
        )
        self.assertEqual(quotas["total"]["day"]["frames"], {"2024-06-12": 10})
        self.assertEqual(quotas["total"]["day"]["count"], {"2024-06-12": 1})

    def test_a_weighted_shot_counts_as_the_share_logged_each_day(self):
        """
        In weighted mode a shot is split over the days time was logged on
        it, the same way its frames are: the shares add up to one shot.
        """
        task = self.generate_shot_task()
        self.shot.update({"nb_frames": 100})
        task.update({"end_date": fields.get_date_object("2024-06-10")})
        time_spents_service.create_or_update_time_spent(
            str(task.id), str(self.person.id), "2024-06-03", 60
        )
        time_spents_service.create_or_update_time_spent(
            str(task.id), str(self.person.id), "2024-06-04", 40
        )

        quotas = quotas_service.get_weighted_quotas(
            str(self.project.id), str(self.task_type_animation.id)
        )

        entry = quotas[str(self.person.id)]
        self.assertEqual(
            entry["day"]["frames"], {"2024-06-03": 60, "2024-06-04": 40}
        )
        self.assertEqual(
            entry["day"]["count"], {"2024-06-03": 0.6, "2024-06-04": 0.4}
        )
        self.assertEqual(entry["week"]["count"], {"2024-23": 1})
        self.assertEqual(entry["month"]["count"], {"2024-06": 1})

    def test_each_person_keeps_their_share_of_a_shared_shot(self):
        """
        28 frames over an 8 hour task, logged on alternate days by two
        people, 4 hours each: 14 frames each. Rounded one by one, the time
        spents gave one of them 15. Shared out in date order, the running
        sum would give them 15 and 13.
        """
        task = self.generate_shot_task()
        self.shot.update({"nb_frames": 28})
        task.update({"end_date": datetime.datetime(2024, 6, 7, 10, 0)})
        for person_id, day, duration in [
            (str(self.person.id), "2024-06-03", 60),
            (self.user["id"], "2024-06-04", 60),
            (str(self.person.id), "2024-06-05", 60),
            (self.user["id"], "2024-06-06", 180),
            (str(self.person.id), "2024-06-07", 120),
        ]:
            time_spents_service.create_or_update_time_spent(
                str(task.id), person_id, day, duration
            )

        quotas = quotas_service.get_weighted_quotas(
            str(self.project.id), str(self.task_type_animation.id)
        )

        for person_id in [str(self.person.id), self.user["id"]]:
            self.assertEqual(quotas[person_id]["year"]["frames"], {"2024": 14})

    def test_a_tie_does_not_always_favor_the_same_person(self):
        """
        Two people logging half of each of two 7-frame shots: in the order
        of their ids, the first of them would take the frame left over by
        each tie, 8 frames against 6. The order is drawn for each task, and
        on these two tasks each of them takes one frame: 7 frames each.
        """
        self.generate_shot_task()
        people = [
            Person.create(
                id="0a1b2c3d-0000-4000-8000-000000000001",
                first_name="Ann",
                last_name="First",
            ),
            Person.create(
                id="f0e1d2c3-0000-4000-8000-000000000002",
                first_name="Bob",
                last_name="Second",
            ),
        ]
        for name, task_id in [
            ("P02", "00000000-0000-4000-8000-000000000001"),
            ("P03", "00000000-0000-4000-8000-000000000002"),
        ]:
            shot = self.generate_fixture_shot(name, nb_frames=7)
            Task.create(
                id=task_id,
                name="Master",
                project_id=self.project.id,
                task_type_id=self.task_type_animation.id,
                task_status_id=self.task_status.id,
                entity_id=shot.id,
                end_date=datetime.datetime(2024, 6, 7, 10, 0),
            )
            for person, day in zip(people, ["2024-06-03", "2024-06-04"]):
                time_spents_service.create_or_update_time_spent(
                    task_id, str(person.id), day, 300
                )

        quotas = quotas_service.get_weighted_quotas(
            str(self.project.id), str(self.task_type_animation.id)
        )

        for person in people:
            self.assertEqual(
                quotas[str(person.id)]["year"]["frames"], {"2024": 7}
            )

    def test_a_shot_without_time_spent_is_split_over_its_working_days(self):
        """
        Without time spent, the shot is spread over the business days from
        the wip date to the feedback date, like its frames.
        """
        task = self.generate_shot_task()
        self.shot.update({"nb_frames": 90})
        task.update(
            {
                "real_start_date": datetime.datetime(2024, 6, 3, 10, 0),
                "end_date": datetime.datetime(2024, 6, 5, 10, 0),
            }
        )

        quotas = quotas_service.get_weighted_quotas(
            str(self.project.id), str(self.task_type_animation.id)
        )

        entry = quotas[str(self.person.id)]
        self.assertEqual(
            entry["day"]["count"],
            {"2024-06-03": 0.33, "2024-06-04": 0.33, "2024-06-05": 0.33},
        )
        self.assertAlmostEqual(entry["month"]["count"]["2024-06"], 1)

    def test_a_person_quota_counts_tasks_without_time_spent(self):
        """
        The person quotas query no task type: the pass for tasks without
        time spent used to filter on a null task type and drop them all.
        """
        task = self.generate_shot_task()
        self.shot.update({"nb_frames": 100})
        task.update(
            {
                "real_start_date": datetime.datetime(2024, 6, 3, 10, 0),
                "end_date": datetime.datetime(2024, 6, 3, 18, 0),
            }
        )

        quotas = quotas_service.get_weighted_quotas(
            str(self.project.id), person_id=str(self.person.id)
        )

        for entry in [str(self.task_type_animation.id), "total"]:
            self.assertEqual(
                quotas[entry]["day"]["frames"], {"2024-06-03": 100}
            )
            self.assertEqual(quotas[entry]["day"]["count"], {"2024-06-03": 1})

    def test_a_person_quota_counts_a_shared_task_once(self):
        """
        A task without time spent shared with another assignee is one shot
        on the page of a person, not one per assignee.
        """
        task = self.generate_shot_task()
        self.shot.update({"nb_frames": 100})
        tasks_service.assign_task(str(task.id), self.user["id"])
        task.update(
            {
                "real_start_date": datetime.datetime(2024, 6, 3, 10, 0),
                "end_date": datetime.datetime(2024, 6, 7, 10, 0),
            }
        )

        quotas = quotas_service.get_weighted_quotas(
            str(self.project.id), person_id=str(self.person.id)
        )

        entry = quotas[str(self.task_type_animation.id)]
        self.assertEqual(entry["year"]["frames"], {"2024": 100})
        self.assertEqual(entry["year"]["count"], {"2024": 1})

    def test_the_total_of_a_task_type_counts_a_shared_task_once(self):
        """
        A task shared by two people is one shot in the total of a task
        type, while each of them counts it whole. The total counted it once
        per assignee in the raw modes, and in the weighted ones for a task
        without time spent.
        """
        task = self.generate_shot_task()
        self.shot.update({"nb_frames": 100})
        tasks_service.assign_task(str(task.id), self.user["id"])
        task.update(
            {
                "real_start_date": datetime.datetime(2024, 6, 3, 10, 0),
                "end_date": datetime.datetime(2024, 6, 7, 10, 0),
            }
        )

        for get_quotas in [
            quotas_service.get_weighted_quotas,
            quotas_service.get_raw_quotas,
        ]:
            with self.subTest(get_quotas=get_quotas.__name__):
                quotas = get_quotas(
                    str(self.project.id), str(self.task_type_animation.id)
                )
                total = quotas["total"]["year"]
                self.assertEqual(total["frames"], {"2024": 100})
                self.assertEqual(total["count"], {"2024": 1})
                for person_id in [str(self.person.id), self.user["id"]]:
                    row = quotas[person_id]["year"]
                    self.assertEqual(row["frames"], {"2024": 100})
                    self.assertEqual(row["count"], {"2024": 1})

    def test_the_quota_shots_of_every_task_type_without_a_filter(self):
        """
        Without a task type, the listing holds the shots of every task type
        the person worked on.
        """
        self.generate_shot_task()
        # generate_fixture_shot repoints self.shot, hence the local.
        anim_shot = self.shot
        layout_shot = self.generate_fixture_shot("L01")
        layout_task = self.generate_fixture_shot_task(
            name="layout",
            shot_id=layout_shot.id,
            task_type_id=self.task_type_layout.id,
        )
        anim_task = self.generate_fixture_shot_task(
            name="anim", shot_id=anim_shot.id
        )
        for task in [anim_task, layout_task]:
            task.update(
                {
                    "real_start_date": datetime.datetime(2024, 6, 3, 10, 0),
                    "end_date": fields.get_date_object("2024-06-04"),
                }
            )

        for weighted in [True, False]:
            with self.subTest(weighted=weighted):
                shots = quotas_service.get_month_quota_shots(
                    str(self.person.id),
                    2024,
                    6,
                    project_id=str(self.project.id),
                    weighted=weighted,
                )
                self.assertEqual(
                    [shot["name"] for shot in shots], ["L01", "P01"]
                )

    def test_the_quota_shots_of_every_project_without_a_filter(self):
        """
        Without a project, the listing holds the shots of every production,
        each one carrying its project so a client can link to it.
        """
        task = self.generate_shot_task()
        other_task = self.generate_fixture_shot_task_standard()
        for each in [task, other_task]:
            each.update(
                {
                    "real_start_date": datetime.datetime(2024, 6, 3, 10, 0),
                    "end_date": fields.get_date_object("2024-06-04"),
                }
            )

        for weighted in [True, False]:
            with self.subTest(weighted=weighted):
                shots = quotas_service.get_month_quota_shots(
                    str(self.person.id),
                    2024,
                    6,
                    task_type_id=str(self.task_type_animation.id),
                    weighted=weighted,
                )
                self.assertEqual(
                    sorted(shot["project_id"] for shot in shots),
                    sorted(
                        [str(self.project.id), str(self.project_standard.id)]
                    ),
                )

    def test_a_week_is_keyed_by_its_iso_year(self):
        """
        2025-12-30 belongs to ISO week 1 of 2026: keying it with the
        calendar year made it "2025-1", the first week of the year before.
        The month and year buckets stay on the calendar year.
        """
        quotas = {}
        quotas_service._add_quota_entry(
            quotas, "person", datetime.date(2025, 12, 30), "UTC", 100, 2, 25
        )
        entry = quotas["person"]
        self.assertEqual(entry["week"]["frames"], {"2026-1": 100})
        self.assertEqual(entry["week"]["entries"], {"2026": 1})
        self.assertEqual(entry["month"]["frames"], {"2025-12": 100})
        self.assertEqual(entry["month"]["entries"], {"2025": 1})
        self.assertEqual(entry["year"]["frames"], {"2025": 100})
