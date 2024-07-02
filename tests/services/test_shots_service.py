import pytest

from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.services import breakdown_service, shots_service
from zou.app.services.exception import (
    SceneNotFoundException,
    ShotNotFoundException,
    SequenceNotFoundException,
)


class ShotUtilsTestCase(ApiDBTestCase):
    def setUp(self):
        super(ShotUtilsTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()
        self.generate_fixture_asset()

    def test_get_shot_type(self):
        shot_type = shots_service.get_shot_type()
        self.assertEqual(shot_type["name"], "Shot")

    def test_get_episode_type(self):
        episode_type = shots_service.get_episode_type()
        self.assertEqual(episode_type["name"], "Episode")

    def test_get_scene_type(self):
        scene_type = shots_service.get_scene_type()
        self.assertEqual(scene_type["name"], "Scene")

    def test_get_episodes(self):
        episodes = shots_service.get_episodes()
        self.assertEqual(len(episodes), 1)
        self.assertEqual(episodes[0]["id"], str(self.episode.id))

    def test_get_sequences(self):
        sequences = shots_service.get_sequences()
        self.assertEqual(len(sequences), 1)
        self.assertEqual(sequences[0]["id"], str(self.sequence.id))

    def test_get_shots(self):
        shots = shots_service.get_shots()
        self.shot_dict = self.shot.serialize(obj_type="Shot")
        self.shot_dict["project_name"] = self.project.name
        self.shot_dict["sequence_name"] = self.sequence.name
        self.assertDictEqual(shots[0], self.shot_dict)

    def test_get_scenes(self):
        scenes = shots_service.get_scenes()
        self.assertEqual(len(scenes), 1)
        self.assertEqual(scenes[0]["id"], str(self.scene.id))

    def test_get_episode_map(self):
        self.generate_fixture_episode("E02")
        episode_map = shots_service.get_episode_map()
        self.assertEqual(len(episode_map.keys()), 2)
        self.assertEqual(
            episode_map[str(self.episode.id)]["name"], self.episode.name
        )

    def test_get_shots_and_tasks(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task()
        self.generate_fixture_shot_task(name="Secondary")
        self.generate_fixture_shot("P02")

        shots = shots_service.get_shots_and_tasks()
        shots = sorted(shots, key=lambda s: s["name"])
        self.assertEqual(len(shots), 2)
        self.assertEqual(len(shots[0]["tasks"]), 2)
        self.assertEqual(len(shots[1]["tasks"]), 0)
        self.assertEqual(shots[0]["episode_id"], str(self.episode.id))
        self.assertEqual(shots[0]["sequence_id"], str(self.sequence.id))
        self.assertEqual(
            shots[0]["tasks"][0]["assignees"][0], str(self.person.id)
        )
        self.assertEqual(
            shots[0]["tasks"][0]["task_status_id"],
            str(self.shot_task.task_status_id),
        )
        self.assertEqual(
            shots[0]["tasks"][0]["task_type_id"],
            str(self.shot_task.task_type_id),
        )

    def test_get_shot(self):
        self.assertEqual(
            str(self.shot.id), shots_service.get_shot(self.shot.id)["id"]
        )

    def test_get_full_shot(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_shot_task()

        shot = shots_service.get_full_shot(self.shot.id)
        self.assertEqual(shot["id"], str(self.shot.id))
        self.assertEqual(shot["sequence_name"], str(self.sequence.name))
        self.assertEqual(shot["episode_name"], str(self.episode.name))
        self.assertEqual(len(shot["tasks"]), 1)

    def test_get_scene(self):
        self.assertEqual(
            str(self.scene.id), shots_service.get_scene(self.scene.id)["id"]
        )

    def test_get_full_scene(self):
        scene = shots_service.get_full_scene(self.scene.id)
        self.assertEqual(scene["id"], str(self.scene.id))
        self.assertEqual(scene["sequence_name"], str(self.sequence.name))
        self.assertEqual(scene["episode_name"], str(self.episode.name))

    def test_get_sequence(self):
        self.assertEqual(
            str(self.sequence.id),
            shots_service.get_sequence(self.sequence.id)["id"],
        )

    def test_get_full_sequence(self):
        sequence = shots_service.get_full_sequence(self.sequence.id)
        self.assertEqual(sequence["id"], str(self.sequence.id))
        self.assertEqual(sequence["episode_name"], str(self.episode.name))

    def test_get_episode(self):
        self.assertEqual(
            str(self.episode.id),
            shots_service.get_episode(self.episode.id)["id"],
        )

    def test_get_full_episode(self):
        episode = shots_service.get_full_episode(self.episode.id)
        self.assertEqual(episode["id"], str(self.episode.id))
        self.assertEqual(episode["project_name"], str(self.project.name))

    def test_is_shot(self):
        self.assertTrue(shots_service.is_shot(self.shot.serialize()))
        self.assertFalse(shots_service.is_shot(self.asset.serialize()))

    def test_is_scene(self):
        self.assertTrue(shots_service.is_scene(self.scene.serialize()))
        self.assertFalse(shots_service.is_scene(self.asset.serialize()))

    def test_is_sequence(self):
        self.assertTrue(shots_service.is_sequence(self.sequence.serialize()))
        self.assertFalse(shots_service.is_sequence(self.asset.serialize()))

    def test_get_sequence_from_shot(self):
        sequence = shots_service.get_sequence_from_shot(self.shot.serialize())
        self.assertEqual(sequence["name"], "S01")

    def test_get_episode_from_shot(self):
        episode = shots_service.get_episode_from_sequence(
            self.sequence.serialize()
        )
        self.assertEqual(episode["name"], "E01")

    def test_get_sequence_from_shot_no_sequence(self):
        self.shot_noseq = Entity.create(
            name="P01NOSEQ",
            project_id=self.project.id,
            entity_type_id=self.shot_type.id,
        )
        self.assertRaises(
            SequenceNotFoundException,
            shots_service.get_sequence_from_shot,
            self.shot_noseq,
        )

    def test_get_sequence_type(self):
        sequence_type = shots_service.get_sequence_type()
        self.assertEqual(sequence_type["name"], "Sequence")

    def test_create_episode(self):
        episode_name = "NE01"
        episode = shots_service.create_episode(self.project.id, episode_name)
        self.assertEqual(episode["name"], episode_name)

    def test_create_sequence(self):
        sequence_name = "NSE01"
        parent_id = str(self.episode.id)
        sequence = shots_service.create_sequence(
            self.project.id, parent_id, sequence_name
        )
        self.assertEqual(sequence["name"], sequence_name)
        self.assertEqual(sequence["parent_id"], parent_id)

    def test_create_shot(self):
        shot_name = "NSH01"
        parent_id = str(self.sequence.id)
        shot = shots_service.create_shot(self.project.id, parent_id, shot_name)
        self.assertEqual(shot["name"], shot_name)
        self.assertEqual(shot["parent_id"], parent_id)

    def test_create_scene(self):
        scene_name = "NSC01"
        parent_id = str(self.sequence.id)
        scene = shots_service.create_scene(
            str(self.project.id), parent_id, scene_name
        )
        self.assertEqual(scene["name"], scene_name)
        self.assertEqual(scene["parent_id"], parent_id)

    def test_remove_shot(self):
        shot_id = str(self.shot.id)
        asset_id = str(self.asset.id)
        breakdown_service.create_casting_link(shot_id, asset_id)
        shots_service.remove_shot(shot_id)
        with pytest.raises(ShotNotFoundException):
            shots_service.get_shot(shot_id)

    def test_remove_scene(self):
        scene_id = self.scene.id
        shots_service.remove_scene(scene_id)
        with pytest.raises(SceneNotFoundException):
            shots_service.get_scene(scene_id)

    def test_get_scenes_for_project(self):
        self.generate_fixture_project_standard()
        self.generate_fixture_scene(
            project_id=self.project_standard.id, sequence_id=self.sequence.id
        )
        scenes = shots_service.get_scenes_for_project(self.project.id)
        self.assertEqual(len(scenes), 1)

    def test_get_scenes_for_sequence(self):
        self.generate_fixture_project_standard()
        self.generate_fixture_sequence_standard()
        self.generate_fixture_sequence(name="SQ02")
        self.generate_fixture_scene(
            project_id=self.project_standard.id, sequence_id=self.sequence.id
        )
        scenes = shots_service.get_scenes_for_sequence(self.sequence.id)
        self.assertEqual(len(scenes), 1)

    def test_set_frames_from_task_type_previews(self):
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        project_id = str(self.project.id)
        task_type = self.task_type_animation
        task_type_id = str(task_type.id)
        print(task_type_id)
        (
            episode_01,
            episode_02,
            sequence_01,
            sequence_02,
            shot_01,
            shot_02,
            shot_03,
            shot_e201,
            task_shot_01,
            task_shot_02,
            task_shot_03,
            task_shot_e201,
            preview_01,
            preview_02,
            preview_03,
            preview_e201,
        ) = self.generate_fixture_shot_tasks_and_previews(
            task_type_id
        )

        shots_service.set_frames_from_task_type_preview_files(
            project_id,
            task_type_id,
            episode_id=episode_01.id
        )

        self.assertEqual(
            3, len(shots_service.get_shots_for_episode(episode_01.id))
        )
        self.assertEqual(
            1, len(shots_service.get_shots_for_episode(episode_02.id))
        )

        shot_01 = shots_service.get_shot(shot_01.id)
        shot_02 = shots_service.get_shot(shot_02.id)
        shot_03 = shots_service.get_shot(shot_03.id)
        shot_e201 = shots_service.get_shot(shot_e201.id)
        self.assertEqual(shot_01["nb_frames"], 750)
        self.assertEqual(shot_02["nb_frames"], 500)
        self.assertEqual(shot_03["nb_frames"], 250)
        self.assertEqual(shot_e201["nb_frames"], 0)

        shots_service.set_frames_from_task_type_preview_files(
            project_id,
            task_type_id
        )
        shot_e201 = shots_service.get_shot(shot_e201["id"])
        self.assertEqual(shot_e201["nb_frames"], 1000)