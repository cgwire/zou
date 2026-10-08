import datetime

from zou.app.services import quotas_service, time_spents_service
from zou.app.utils import fields
from tests.services.cases import ShotsTestCase


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
