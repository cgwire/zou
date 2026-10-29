import datetime

from tests.base import ApiDBTestCase
from zou.app.models.studio import Studio
from zou.app.services import quotas_service, tasks_service, time_spents_service
from zou.app.utils import fields


class ShotRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_person()
        self.generate_fixture_task_type()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()

    def test_get_shot_preview_files(self):
        # Keyed by task type, and a task type appears only once it has a
        # preview: an empty shot answers nothing at all.
        self.assertEqual(
            self.get(f"/data/shots/{self.shot.id}/preview-files"), {}
        )

    def test_get_shot_preview_files_with_data(self):
        self.generate_fixture_preview_file(
            task_id=self.shot_task.id,
        )
        result = self.get(f"/data/shots/{self.shot.id}/preview-files")
        self.assertGreater(len(result), 0)

    def test_get_shot_versions(self):
        # Nothing has been published on this shot yet.
        self.assertEqual(self.get(f"/data/shots/{self.shot.id}/versions"), [])

    def test_get_episode_shot_tasks(self):
        result = self.get(f"/data/episodes/{self.episode.id}/shot-tasks")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_get_episode_asset_tasks(self):
        """
        The tasks of the assets that belong to the episode. An asset of the
        production that belongs to no episode is not one of them.
        """
        path = f"/data/episodes/{self.episode.id}/asset-tasks"
        self.assertEqual(self.get(path), [])
        self.asset.update({"source_id": self.episode.id})

        result = self.get(path)

        self.assertEqual(
            [entry["id"] for entry in result], [str(self.task.id)]
        )

    def test_get_sequence_shot_tasks(self):
        result = self.get(f"/data/sequences/{self.sequence.id}/shot-tasks")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def a_shot_closed_on(self, date, nb_frames=100):
        """
        A shot task assigned and given its feedback date, which is what a
        quota counts: the shot's frames land on that day.
        """
        self.shot.update({"nb_frames": nb_frames})
        tasks_service.assign_task(str(self.shot_task.id), str(self.person.id))
        self.shot_task.update({"end_date": fields.get_date_object(date)})

        # A second shot of the same size, same task type, assigned to the
        # same person but never given a feedback date: nothing of it may
        # reach the counts.
        closed_task = self.shot_task
        open_shot = self.generate_fixture_shot("SH02")
        open_shot.update({"nb_frames": nb_frames})
        open_task = self.generate_fixture_shot_task(shot_id=open_shot.id)
        tasks_service.assign_task(str(open_task.id), str(self.person.id))
        self.shot_task = closed_task

    def test_get_project_quotas(self):
        """
        Frames per person, per period, in raw mode: the whole shot counts on
        the day its task got its feedback.
        """
        self.a_shot_closed_on("2024-06-12")

        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/{self.task_type_animation.id}?count_mode=feedback"
        )

        for entry in [str(self.person.id), "total"]:
            # Whole buckets, so the unfinished shot cannot slip in under a
            # day of its own.
            self.assertEqual(
                result[entry]["day"]["frames"], {"2024-06-12": 100}
            )
            self.assertEqual(result[entry]["month"]["count"], {"2024-06": 1})

    def test_weighted_quotas_spread_the_shot_over_its_working_days(self):
        """
        Without time spents, the frames are spread evenly over the business
        days between the wip date and the feedback date. The cursor used to
        start at the feedback date, which pushed the whole shot past it.
        """
        self.shot.update({"nb_frames": 100})
        tasks_service.assign_task(str(self.shot_task.id), str(self.person.id))
        self.shot_task.update(
            {
                "real_start_date": datetime.datetime(2024, 6, 3, 10, 0),
                "end_date": datetime.datetime(2024, 6, 7, 10, 0),
            }
        )

        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/{self.task_type_animation.id}?count_mode=weighted"
        )

        self.assertEqual(
            result["total"]["day"]["frames"],
            {
                "2024-06-03": 20,
                "2024-06-04": 20,
                "2024-06-05": 20,
                "2024-06-06": 20,
                "2024-06-07": 20,
            },
        )

    def test_weighted_quotas_keep_every_frame_of_the_shot(self):
        """
        10 frames over three working days: rounding the share of each day
        on its own counted 3 a day, 9 in all.
        """
        self.shot.update({"nb_frames": 10})
        tasks_service.assign_task(str(self.shot_task.id), str(self.person.id))
        self.shot_task.update(
            {
                "real_start_date": datetime.datetime(2024, 6, 3, 10, 0),
                "end_date": datetime.datetime(2024, 6, 5, 10, 0),
            }
        )

        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/{self.task_type_animation.id}?count_mode=weighted"
        )

        self.assertEqual(
            result["total"]["day"]["frames"],
            {"2024-06-03": 3, "2024-06-04": 3, "2024-06-05": 4},
        )

    def test_weighted_quotas_spread_the_drawings_of_the_shot(self):
        """
        The drawings of a task without time spent are spread over its
        working days like its frames, every drawing kept: they used to be
        counted in full on each day, 30 for a 10-drawing task worked three
        days.
        """
        tasks_service.assign_task(str(self.shot_task.id), str(self.person.id))
        self.shot_task.update(
            {
                "nb_drawings": 10,
                "real_start_date": datetime.datetime(2024, 6, 3, 10, 0),
                "end_date": datetime.datetime(2024, 6, 5, 10, 0),
            }
        )

        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/{self.task_type_animation.id}?count_mode=weighted"
        )

        self.assertEqual(
            result["total"]["day"]["drawings"],
            {"2024-06-03": 3, "2024-06-04": 3, "2024-06-05": 4},
        )

    def test_weighted_quotas_keep_every_frame_of_the_time_spents(self):
        """
        Three equal time spents on a 10-frame shot: rounded one by one,
        each counted 3 frames, 9 in all. Its 10 drawings are shared out the
        same way.
        """
        self.shot.update({"nb_frames": 10})
        self.shot_task.update(
            {
                "nb_drawings": 10,
                "end_date": datetime.datetime(2024, 6, 5, 10, 0),
            }
        )
        for day in ["2024-06-03", "2024-06-04", "2024-06-05"]:
            time_spents_service.create_or_update_time_spent(
                str(self.shot_task.id), str(self.person.id), day, 120
            )

        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/{self.task_type_animation.id}?count_mode=weighted"
        )

        self.assertEqual(
            result["total"]["day"]["drawings"],
            {"2024-06-03": 3, "2024-06-04": 4, "2024-06-05": 3},
        )
        self.assertEqual(
            result["total"]["day"]["frames"],
            {"2024-06-03": 3, "2024-06-04": 4, "2024-06-05": 3},
        )
        # One shot, however many days were logged on it.
        self.assertEqual(result["total"]["year"]["count"], {"2024": 1})

    def test_weighted_quotas_share_a_shot_between_the_people_on_it(self):
        """
        Two people logged half of a 7-frame shot each. Shared out person by
        person, each share was rounded on its own, 4 + 4 = 8. Shared out
        together they add up to the shot, and a person reads the same share
        on their own page as on the task type one.
        """
        self.shot.update({"nb_frames": 7})
        self.shot_task.update(
            {"end_date": datetime.datetime(2024, 6, 5, 10, 0)}
        )
        time_spents_service.create_or_update_time_spent(
            str(self.shot_task.id), str(self.person.id), "2024-06-03", 300
        )
        time_spents_service.create_or_update_time_spent(
            str(self.shot_task.id), self.user["id"], "2024-06-04", 300
        )
        # The days of each person are shared out in an order drawn for the
        # task: the second person gets 3 frames, where their half read alone
        # on their own page rounded up to 4.
        second_id = max(
            str(self.person.id),
            self.user["id"],
            key=lambda person_id: quotas_service._get_block_key(
                self.shot_task.id, person_id
            ),
        )

        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/{self.task_type_animation.id}?count_mode=weighted"
        )
        person_result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/persons/{second_id}?count_mode=weighted"
        )

        frames = result["total"]["day"]["frames"]
        self.assertEqual(sorted(frames.values()), [3, 4])
        self.assertEqual(result["total"]["year"]["count"], {"2024": 1})
        self.assertEqual(result[second_id]["year"]["frames"], {"2024": 3})
        task_type_id = str(self.task_type_animation.id)
        self.assertEqual(
            person_result[task_type_id]["year"]["frames"], {"2024": 3}
        )

    def test_weighted_quotas_count_a_task_that_never_went_wip(self):
        """
        A task sent to feedback without ever being WIP has no start date to
        spread it from: it lands on its end day, as in the raw modes. The
        weighted modes used to leave it out.
        """
        self.shot.update({"nb_frames": 10})
        tasks_service.assign_task(str(self.shot_task.id), str(self.person.id))
        self.shot_task.update(
            {"end_date": datetime.datetime(2024, 6, 5, 10, 0)}
        )

        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/{self.task_type_animation.id}?count_mode=weighted"
        )

        self.assertEqual(result["total"]["day"]["frames"], {"2024-06-05": 10})
        self.assertEqual(result["total"]["day"]["count"], {"2024-06-05": 1})

    def test_weighted_quotas_leave_out_a_weekend_start(self):
        """
        A task started on a Saturday shares its frames between the working
        days that follow. The Saturday used to take a share of its own that
        no day was credited with.
        """
        self.shot.update({"nb_frames": 30})
        tasks_service.assign_task(str(self.shot_task.id), str(self.person.id))
        self.shot_task.update(
            {
                "real_start_date": datetime.datetime(2024, 6, 1, 10, 0),
                "end_date": datetime.datetime(2024, 6, 5, 10, 0),
            }
        )

        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/{self.task_type_animation.id}?count_mode=weighted"
        )

        self.assertEqual(
            result["total"]["day"]["frames"],
            {"2024-06-03": 10, "2024-06-04": 10, "2024-06-05": 10},
        )

    def test_weighted_quotas_spread_the_shot_over_the_local_days(self):
        """
        Sent to feedback on Wednesday 22:30 UTC, Thursday 00:30 in Paris,
        the timezone of the user: the shot is spread from Monday to
        Thursday, not over the three days of UTC.
        """
        self.shot.update({"nb_frames": 12})
        self.shot_task.update(
            {
                "real_start_date": datetime.datetime(2024, 6, 3, 10, 0),
                "end_date": datetime.datetime(2024, 6, 5, 22, 30),
            }
        )

        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/{self.task_type_animation.id}?count_mode=weighted"
        )

        self.assertEqual(
            result["total"]["day"]["frames"],
            {
                "2024-06-03": 3,
                "2024-06-04": 3,
                "2024-06-05": 3,
                "2024-06-06": 3,
            },
        )

    def test_get_project_quotas_of_a_studio(self):
        """
        The studio filter used to expand into one EXISTS per member of the
        studio; a studio without members then matched every task.
        """
        studio = Studio.create(name="Paris", color="#000000")
        self.person.update({"studio_id": studio.id})
        self.a_shot_closed_on("2024-06-12")
        path = (
            f"/data/projects/{self.project.id}"
            f"/quotas/{self.task_type_animation.id}?count_mode=feedback"
        )

        result = self.get(f"{path}&studio_id={studio.id}")
        self.assertEqual(result["total"]["day"]["frames"], {"2024-06-12": 100})

        empty_studio = Studio.create(name="Empty", color="#000000")
        result = self.get(f"{path}&studio_id={empty_studio.id}")
        self.assertEqual(result, {})

    def test_get_project_person_quotas(self):
        """
        The same figures for one person, keyed by task type rather than by
        person.
        """
        self.a_shot_closed_on("2024-06-12")

        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/persons/{self.person.id}?count_mode=feedback"
        )

        task_type_id = str(self.task_type_animation.id)
        self.assertEqual(
            result[task_type_id]["day"]["frames"], {"2024-06-12": 100}
        )
        self.assertEqual(result[task_type_id]["year"]["count"], {"2024": 1})

    def test_get_project_person_quotas_count_a_shared_task_once(self):
        """
        A task shared with another assignee is one shot on the page of a
        person, not one per assignee.
        """
        self.a_shot_closed_on("2024-06-12")
        tasks_service.assign_task(str(self.shot_task.id), self.user["id"])

        result = self.get(
            f"/data/projects/{self.project.id}"
            f"/quotas/persons/{self.person.id}?count_mode=feedback"
        )

        task_type_id = str(self.task_type_animation.id)
        self.assertEqual(
            result[task_type_id]["day"]["frames"], {"2024-06-12": 100}
        )
        self.assertEqual(result[task_type_id]["year"]["count"], {"2024": 1})

    def test_set_shot_nb_frames(self):
        """
        Backfill the frame count of each shot from the duration of its last
        preview, at the production's frame rate.
        """
        # A longer preview on the same shot under another task type: the
        # backfill asked about animation must not read its duration.
        # generate_fixture_shot_task repoints self.shot_task.
        animation_task = self.shot_task
        self.generate_fixture_preview_file(task_id=animation_task.id).update(
            {"duration": 4.0}
        )
        # A newer, longer preview on the same shot under another task type.
        # The newest preview is picked per task type, so this one is not the
        # animation answer even though it is the latest of the shot.
        other_task = self.generate_fixture_shot_task(
            name="Layout", task_type_id=self.task_type.id
        )
        self.generate_fixture_preview_file(
            task_id=other_task.id, revision=2
        ).update({"duration": 8.0})

        result = self.post(
            f"/actions/projects/{self.project.id}"
            f"/task-types/{self.task_type_animation.id}"
            f"/set-shot-nb-frames",
            {},
            200,
        )

        # The fixture production runs at 25 fps.
        self.assertEqual(
            [(str(update["id"]), update["nb_frames"]) for update in result],
            [(str(self.shot.id), 100)],
        )
        shot = self.get(f"/data/shots/{self.shot.id}")
        self.assertEqual(shot["nb_frames"], 100)
