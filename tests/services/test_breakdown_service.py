from tests.base import ApiDBTestCase

from zou.app.services import (
    assets_service,
    breakdown_service,
    projects_service,
    tasks_service,
)


class BreakdownServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(BreakdownServiceTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset_types()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()
        self.generate_fixture_asset()
        self.generate_fixture_asset_character()
        self.project_id = str(self.project.id)
        self.shot_id = str(self.shot.id)
        self.scene_id = str(self.scene.id)
        self.asset_id = str(self.asset.id)
        self.asset_character_id = str(self.asset_character.id)

    def test_get_sequence_casting(self):
        self.shot_id = str(self.shot.id)
        self.sequence_id = str(self.sequence.id)
        self.asset_id = str(self.asset.id)
        self.asset_character_id = str(self.asset_character.id)

        casting = breakdown_service.get_casting(self.shot.id)
        self.assertListEqual(casting, [])
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 3},
        ]
        breakdown_service.update_casting(self.shot.id, new_casting)
        self.generate_fixture_shot("SH02")
        new_casting = [{"asset_id": self.asset_id, "nb_occurences": 1}]
        breakdown_service.update_casting(self.shot.id, new_casting)
        casting = breakdown_service.get_sequence_casting(self.sequence.id)
        self.maxDiff = 10000
        self.assertTrue(self.shot_id in casting)
        self.assertTrue(str(self.shot.id) in casting)
        self.assertEqual(len(casting[self.shot_id]), 2)
        self.assertEqual(len(casting[str(self.shot.id)]), 1)

    def test_get_asset_type_casting(self):
        self.shot_id = str(self.shot.id)
        self.sequence_id = str(self.sequence.id)
        self.asset_type_environment_id = str(self.asset_type_environment.id)
        self.asset_props_id = str(self.asset.id)
        self.asset_character_id = str(self.asset_character.id)
        self.generate_fixture_asset(
            "Forest", "", self.asset_type_environment_id
        )
        self.forest_id = str(self.asset.id)

        casting = breakdown_service.get_asset_type_casting(
            self.project_id, self.asset_type_environment_id
        )
        self.assertDictEqual(casting, {})
        new_casting = [
            {"asset_id": self.asset_props_id, "nb_occurences": 3},
            {"asset_id": self.asset_character_id, "nb_occurences": 1},
        ]
        breakdown_service.update_casting(self.asset.id, new_casting)
        self.generate_fixture_asset("Park", "", self.asset_type_environment_id)
        new_casting = [{"asset_id": self.asset_props_id, "nb_occurences": 1}]
        breakdown_service.update_casting(self.asset.id, new_casting)
        casting = breakdown_service.get_asset_type_casting(
            self.project_id, self.asset_type_environment_id
        )
        self.maxDiff = 10000
        self.assertTrue(self.forest_id in casting)
        self.assertTrue(str(self.asset.id) in casting)
        self.assertEqual(len(casting[self.forest_id]), 2)
        self.assertEqual(len(casting[str(self.asset.id)]), 1)

    def new_shot_instance(self, asset_instance_id):
        return breakdown_service.add_asset_instance_to_shot(
            self.shot_id, asset_instance_id
        )

    def new_scene_instance(self, asset_id):
        return breakdown_service.add_asset_instance_to_scene(
            self.scene_id, asset_id
        )

    def test_update_casting(self):
        self.shot_id = str(self.shot.id)
        self.asset_id = str(self.asset.id)
        self.asset_character_id = str(self.asset_character.id)

        casting = breakdown_service.get_casting(self.shot.id)
        self.assertListEqual(casting, [])
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 3},
        ]
        breakdown_service.update_casting(self.shot.id, new_casting)

        casting = breakdown_service.get_casting(self.shot.id)
        casting = sorted(casting, key=lambda x: x["nb_occurences"])
        self.assertEqual(casting[0]["asset_id"], new_casting[0]["asset_id"])
        self.assertEqual(
            casting[0]["nb_occurences"], new_casting[0]["nb_occurences"]
        )
        self.assertEqual(casting[1]["asset_id"], new_casting[1]["asset_id"])
        self.assertEqual(
            casting[1]["nb_occurences"], new_casting[1]["nb_occurences"]
        )
        self.assertEqual(casting[1]["asset_name"], self.asset_character.name)
        self.assertEqual(
            casting[1]["asset_type_name"], self.asset_type_character.name
        )

        cast_in = breakdown_service.get_cast_in(self.asset_character.id)
        self.assertEqual(cast_in[0]["shot_name"], self.shot.name)
        self.assertEqual(cast_in[0]["sequence_name"], self.sequence.name)
        self.assertEqual(cast_in[0]["episode_name"], self.episode.name)

    def test_add_instance_to_shot(self):
        instances = breakdown_service.get_asset_instances_for_shot(
            self.shot.id
        )
        self.assertEqual(instances, {})

        asset_instance = self.new_scene_instance(self.asset_id)
        self.new_shot_instance(asset_instance["id"])
        asset_instance = self.new_scene_instance(self.asset_id)
        self.new_shot_instance(asset_instance["id"])
        asset_instance = self.new_scene_instance(self.asset_character_id)
        self.new_shot_instance(asset_instance["id"])

        instances = breakdown_service.get_asset_instances_for_shot(
            self.shot.id
        )
        self.assertEqual(len(instances[self.asset_id]), 2)
        self.assertEqual(len(instances[self.asset_character_id]), 1)
        self.assertEqual(instances[self.asset_id][0]["number"], 1)
        self.assertEqual(instances[self.asset_id][1]["number"], 2)
        self.assertEqual(instances[self.asset_id][1]["name"], "Tree_0002")
        self.assertEqual(instances[self.asset_character_id][0]["number"], 1)

        instances = breakdown_service.remove_asset_instance_for_shot(
            self.shot.id, asset_instance["id"]
        )
        instances = breakdown_service.get_asset_instances_for_shot(
            self.shot.id
        )
        self.assertTrue(self.asset_character_id not in instances)

    def test_build_asset_instance_name(self):
        name = breakdown_service.build_asset_instance_name(self.asset_id, 3)
        self.assertEqual(name, "Tree_0003")
        name = breakdown_service.build_asset_instance_name(
            self.asset_character_id, 5
        )
        self.assertEqual(name, "Rabbit_0005")

    def test_get_shot_asset_instances_for_asset(self):
        instances = breakdown_service.get_shot_asset_instances_for_asset(
            self.asset.id
        )
        self.assertEqual(instances, {})

        asset_instance = self.new_scene_instance(self.asset_id)
        self.new_shot_instance(asset_instance["id"])
        asset_instance = self.new_scene_instance(self.asset_id)
        self.new_shot_instance(asset_instance["id"])
        asset_instance = self.new_scene_instance(self.asset_character_id)
        self.new_shot_instance(asset_instance["id"])

        instances = breakdown_service.get_shot_asset_instances_for_asset(
            self.asset.id
        )
        self.assertEqual(len(instances[self.shot_id]), 2)

    def test_add_instance_to_scene(self):
        instances = breakdown_service.get_asset_instances_for_scene(
            self.scene.id
        )
        self.assertEqual(instances, {})

        self.new_scene_instance(self.asset_id)
        self.new_scene_instance(self.asset_id)
        self.new_scene_instance(self.asset_character_id)

        instances = breakdown_service.get_asset_instances_for_scene(
            self.scene.id
        )
        self.assertEqual(len(instances[self.asset_id]), 2)
        self.assertEqual(len(instances[self.asset_character_id]), 1)
        self.assertEqual(instances[self.asset_id][0]["number"], 1)
        self.assertEqual(instances[self.asset_id][1]["number"], 2)
        self.assertEqual(instances[self.asset_character_id][0]["number"], 1)

    def test_get_scene_asset_instances_for_asset(self):
        instances = breakdown_service.get_scene_asset_instances_for_asset(
            self.asset.id
        )
        self.assertEqual(instances, {})

        self.new_scene_instance(self.asset.id)
        self.new_scene_instance(self.asset.id)
        self.new_scene_instance(self.asset_character.id)
        instances = breakdown_service.get_scene_asset_instances_for_asset(
            self.asset.id
        )
        self.assertEqual(len(instances[self.scene_id]), 2)

    def test_is_asset_ready(self):
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.task_type_compositing = tasks_service.get_or_create_task_type(
            self.department_animation.serialize(),
            "compositing",
            color="#FFFFFF",
            short_name="compo",
            for_entity="Shot",
        )
        self.task_type_layout_id = str(self.task_type_layout.id)
        self.task_type_animation_id = str(self.task_type_animation.id)
        self.task_type_compositing_id = self.task_type_compositing["id"]
        projects_service.create_project_task_type_link(
            self.project_id, self.task_type_layout_id, 1
        )
        projects_service.create_project_task_type_link(
            self.project_id, self.task_type_animation_id, 2
        )
        projects_service.create_project_task_type_link(
            self.project_id, self.task_type_compositing_id, 3
        )
        self.task_layout = self.generate_fixture_shot_task(
            task_type_id=self.task_type_layout_id
        )
        self.task_animation = self.generate_fixture_shot_task(
            task_type_id=self.task_type_animation_id
        )
        self.task_compositing = self.generate_fixture_shot_task(
            task_type_id=self.task_type_compositing_id
        )
        priority_map = breakdown_service._get_task_type_priority_map(
            self.project_id
        )
        self.assertEqual(priority_map[self.task_type_layout_id], 1)
        self.assertEqual(priority_map[self.task_type_animation_id], 2)
        self.assertEqual(priority_map[self.task_type_compositing_id], 3)
        asset = {"ready_for": str(self.task_type_animation.id)}
        self.assertTrue(
            breakdown_service._is_asset_ready(
                asset, self.task_layout, priority_map
            )
        )
        self.assertTrue(
            breakdown_service._is_asset_ready(
                asset, self.task_animation, priority_map
            )
        )
        self.assertFalse(
            breakdown_service._is_asset_ready(
                asset, self.task_compositing, priority_map
            )
        )

        self.shot_id = str(self.shot.id)
        self.sequence_id = str(self.sequence.id)
        self.asset_id = str(self.asset.id)
        self.asset_character_id = str(self.asset_character.id)
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 3},
        ]
        breakdown_service.update_casting(self.shot_id, new_casting)
        asset = assets_service.get_asset_raw(self.asset_id)
        asset.update({"ready_for": self.task_type_animation_id})
        char = assets_service.get_asset_raw(self.asset_character_id)
        char.update({"ready_for": self.task_type_compositing_id})

        breakdown_service.refresh_casting_stats(asset.serialize())
        self.task_layout = tasks_service.get_task(self.task_layout.id)
        self.task_animation = tasks_service.get_task(self.task_animation.id)
        self.task_compositing = tasks_service.get_task(
            self.task_compositing.id
        )
        self.assertEqual(self.task_layout["nb_assets_ready"], 2)
        self.assertEqual(self.task_animation["nb_assets_ready"], 2)
        self.assertEqual(self.task_compositing["nb_assets_ready"], 1)
