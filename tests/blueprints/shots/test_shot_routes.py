import datetime

from tests.base import ApiDBTestCase
from zou.app.models.entity import Entity, EntityVersion
from zou.app.models.studio import Studio
from zou.app.services import (
    metadata_descriptors_service,
    projects_service,
    tasks_service,
)
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

    def generate_second_row_of_each_kind(self):
        """
        Give the production two episodes, sequences, scenes and shots, all
        the shots in the first sequence of the first episode and in the
        first scene, and two versions to the first shot.
        """
        episode = self.episode
        sequence = self.sequence
        shot = self.shot
        scene = self.generate_fixture_scene()
        self.generate_fixture_scene("SC02")
        second_shot = self.generate_fixture_shot(
            "P02", sequence_id=sequence.id
        )
        self.generate_fixture_sequence("S02", episode_id=episode.id)
        self.generate_fixture_episode("E02")
        for entity in [shot, second_shot]:
            entity.update({"source_id": scene.id})
        for index in range(2):
            EntityVersion.create(
                name=shot.name, entity_id=shot.id, data={"index": index}
            )
        return episode, sequence, scene, shot

    def test_entity_listings_paginate_on_demand(self):
        episode, sequence, scene, shot = (
            self.generate_second_row_of_each_kind()
        )
        project_path = f"/data/projects/{self.project.id}"
        for path in [
            f"{project_path}/shots",
            f"{project_path}/sequences",
            f"{project_path}/scenes",
            f"{project_path}/episodes",
            f"/data/episodes/{episode.id}/shots",
            f"/data/episodes/{episode.id}/sequences",
            f"/data/sequences/{sequence.id}/shots",
            f"/data/sequences/{sequence.id}/scenes",
            f"/data/scenes/{scene.id}/shots",
            "/data/shots",
            f"/data/shots/all?project_id={self.project.id}",
            "/data/scenes/all",
            "/data/episodes",
            "/data/sequences",
            f"/data/shots/{shot.id}/versions",
        ]:
            with self.subTest(path=path):
                self.assert_opt_in_pagination(path)

    def test_a_vendor_page_is_scoped_and_masked(self):
        """
        A page served to a vendor holds only what they are assigned to, and
        the metadata of departments they do not belong to stays hidden.
        """
        self.generate_second_row_of_each_kind()
        self.generate_fixture_department()
        project_id = str(self.project.id)
        vendor_id = self.generate_fixture_user_vendor()["id"]
        projects_service.add_team_member(project_id, vendor_id)
        # Two tasks on the same shot: the shot still counts once.
        first_task = self.shot_task
        second_task = self.generate_fixture_shot_task(
            name="Secondary", shot_id=first_task.entity_id
        )
        for task in [first_task, second_task]:
            tasks_service.assign_task(task.id, vendor_id)
        shot = Entity.get(first_task.entity_id)
        # The shot is linked to a scene through its source: the vendor
        # episode lookup used to list that scene as an episode.
        self.assertIsNotNone(shot.source_id)
        sequence = Entity.get(shot.parent_id)
        for entity, entity_type in [(shot, "Shot"), (sequence, "Sequence")]:
            descriptor = metadata_descriptors_service.add_metadata_descriptor(
                project_id,
                entity_type,
                "Rig",
                "string",
                [],
                False,
                [str(self.department_animation.id)],
            )
            entity.update({"data": {descriptor["field_name"]: "secret"}})
        self.log_in_vendor()
        for path, expected_id in [
            (f"/data/projects/{project_id}/shots", shot.id),
            (f"/data/projects/{project_id}/sequences", sequence.id),
            (f"/data/shots?project_id={project_id}", shot.id),
            (f"/data/sequences/{sequence.id}/shots", shot.id),
            (f"/data/projects/{project_id}/episodes", sequence.parent_id),
            (f"/data/episodes/{sequence.parent_id}/sequences", sequence.id),
        ]:
            with self.subTest(path=path):
                separator = "&" if "?" in path else "?"
                result = self.get(f"{path}{separator}page=1&limit=10")
                self.assertEqual(result["total"], 1)
                self.assertEqual(
                    [row["id"] for row in result["data"]], [str(expected_id)]
                )
                self.assertNotIn(
                    descriptor["field_name"], result["data"][0]["data"] or {}
                )
                self.assert_opt_in_pagination(path)
