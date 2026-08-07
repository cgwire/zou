from tests.base import ApiDBTestCase

from zou.app.services import tasks_service
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
