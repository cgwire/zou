from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.services import (
    assets_service,
    breakdown_service,
    entities_service,
    projects_service,
    tasks_service,
)


class BreakdownServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
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
        self.sequence_id = str(self.sequence.id)

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
        self.assertIn(self.shot_id, casting)
        self.assertIn(str(self.shot.id), casting)
        self.assertEqual(len(casting[self.shot_id]), 2)
        self.assertEqual(len(casting[str(self.shot.id)]), 1)

    def test_get_all_sequence_casting(self):
        self.sequence_id = str(self.sequence.id)
        casting = breakdown_service.get_casting(self.shot.id)
        self.assertListEqual(casting, [])
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 3},
        ]
        breakdown_service.update_casting(self.shot.id, new_casting)
        self.generate_fixture_sequence("SE02")
        self.generate_fixture_shot("SH02")
        new_casting = [{"asset_id": self.asset_id, "nb_occurences": 1}]
        breakdown_service.update_casting(self.shot.id, new_casting)
        casting = breakdown_service.get_all_sequences_casting(self.project_id)
        self.assertIn(self.shot_id, casting)
        self.assertIn(str(self.shot.id), casting)
        self.assertEqual(len(casting[self.shot_id]), 2)
        self.assertEqual(len(casting[str(self.shot.id)]), 1)

        episode = self.generate_fixture_episode("E01")
        self.generate_fixture_sequence("E01SE01")
        self.generate_fixture_shot("E01SH01")
        new_casting = [{"asset_id": self.asset_id, "nb_occurences": 1}]
        breakdown_service.update_casting(self.shot.id, new_casting)
        casting = breakdown_service.get_all_sequences_casting(None, episode.id)
        self.assertEqual(len(casting.keys()), 1)
        self.assertEqual(len(casting[str(self.shot.id)]), 1)

    def test_get_asset_type_casting(self):
        self.asset_type_environment_id = str(self.asset_type_environment.id)
        self.asset_props_id = str(self.asset.id)
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
        self.park_id = str(self.asset.id)
        new_casting = [{"asset_id": self.asset_props_id, "nb_occurences": 1}]
        breakdown_service.update_casting(self.asset.id, new_casting)

        # An environment of another production, cast the same way.
        self.generate_fixture_project_standard()
        elsewhere = self.generate_fixture_asset(
            "Lake",
            "",
            self.asset_type_environment_id,
            project_id=self.project_standard.id,
        )
        breakdown_service.update_casting(
            elsewhere.id,
            [{"asset_id": self.asset_props_id, "nb_occurences": 1}],
        )

        casting = breakdown_service.get_asset_type_casting(
            self.project_id, self.asset_type_environment_id
        )
        self.assertEqual(
            sorted(casting.keys()), sorted([self.forest_id, self.park_id])
        )
        # Each list is ordered by asset type name, then by asset name, so
        # the character comes before the props whatever order they were cast
        # in.
        self.assertEqual(
            [
                (entry["asset_type_name"], entry["asset_name"])
                for entry in casting[self.forest_id]
            ],
            [("Character", "Rabbit"), ("Props", "Tree")],
        )
        self.assertEqual(len(casting[self.park_id]), 1)

    def test_get_production_episodes_casting(self):
        """
        The casting of every episode of one production, keyed by episode.
        An episode of another production stays out.
        """
        episode_id = str(self.episode.id)
        breakdown_service.update_casting(
            episode_id, [{"asset_id": self.asset_id, "nb_occurences": 2}]
        )

        self.generate_fixture_project_standard()
        elsewhere = self.generate_fixture_episode(
            name="E99", project_id=self.project_standard.id
        )
        breakdown_service.update_casting(
            elsewhere.id,
            [{"asset_id": self.asset_id, "nb_occurences": 1}],
        )

        castings = breakdown_service.get_production_episodes_casting(
            self.project_id
        )

        self.assertEqual(list(castings.keys()), [episode_id])
        casting = castings[episode_id]
        self.assertEqual(
            [
                (entry["asset_name"], entry["nb_occurences"])
                for entry in casting
            ],
            [("Tree", 2)],
        )

    def new_shot_instance(self, asset_instance_id):
        return breakdown_service.add_asset_instance_to_shot(
            self.shot_id, asset_instance_id
        )

    def new_scene_instance(self, asset_id):
        return breakdown_service.add_asset_instance_to_scene(
            self.scene_id, asset_id
        )

    def test_update_casting(self):
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

    def test_update_casting_event_payload_diff(self):
        """
        casting-update events must include added_asset_ids and
        removed_asset_ids so listeners know what changed without having
        to keep a client-side snapshot (cgwire/gazu#393).
        """
        captured = self.capture_events("shot:casting-update")

        shot_id = str(self.shot.id)
        asset_id = str(self.asset.id)
        asset_character_id = str(self.asset_character.id)

        # Initial casting: both assets added.
        breakdown_service.update_casting(
            self.shot.id,
            [
                {"asset_id": asset_id, "nb_occurences": 1},
                {"asset_id": asset_character_id, "nb_occurences": 3},
            ],
        )
        self.assertEqual(len(captured), 1)
        first = captured[0]
        self.assertEqual(first["shot_id"], shot_id)
        self.assertEqual(first["nb_entities_out"], 2)
        # Sorted on both sides: the service sorts these ids, but they are
        # random UUIDs, so an unsorted pair matches the sorted one half the
        # time and the order cannot be pinned without flakiness.
        self.assertEqual(
            sorted(first["added_asset_ids"]),
            sorted([asset_id, asset_character_id]),
        )
        self.assertEqual(first["removed_asset_ids"], [])

        # Replace casting: drop asset_character, keep asset.
        breakdown_service.update_casting(
            self.shot.id,
            [{"asset_id": asset_id, "nb_occurences": 1}],
        )
        self.assertEqual(len(captured), 2)
        second = captured[1]
        self.assertEqual(second["shot_id"], shot_id)
        self.assertEqual(second["nb_entities_out"], 1)
        self.assertEqual(second["added_asset_ids"], [])
        self.assertEqual(second["removed_asset_ids"], [asset_character_id])

        # Cast the character again and drop both, so the removal diff is
        # computed over two ids rather than one.
        breakdown_service.update_casting(
            self.shot.id,
            [
                {"asset_id": asset_id, "nb_occurences": 1},
                {"asset_id": asset_character_id, "nb_occurences": 3},
            ],
        )
        breakdown_service.update_casting(self.shot.id, [])
        last = captured[-1]
        self.assertEqual(last["nb_entities_out"], 0)
        self.assertEqual(last["added_asset_ids"], [])
        self.assertEqual(
            sorted(last["removed_asset_ids"]),
            sorted([asset_id, asset_character_id]),
        )

    def test_update_casting_keeps_asset_in_episode_while_another_shot_uses_it(
        self,
    ):
        """
        Casting an asset in a shot auto-casts it in the parent episode too.
        Removing that asset from one shot must not detach it from the
        episode while another shot of that episode still casts it
        (cgwire/kitsu#1388).
        """
        asset_id = str(self.asset.id)
        # generate_fixture_shot() reassigns self.shot to the newly created
        # shot, so keep an explicit reference to the original one.
        first_shot = self.shot
        other_shot = self.generate_fixture_shot("SH02")

        breakdown_service.update_casting(
            first_shot.id, [{"asset_id": asset_id, "nb_occurences": 1}]
        )
        breakdown_service.update_casting(
            other_shot.id, [{"asset_id": asset_id, "nb_occurences": 1}]
        )
        episode_casting = breakdown_service.get_casting(self.episode.id)
        self.assertEqual(
            [cast["asset_id"] for cast in episode_casting], [asset_id]
        )

        # Un-cast the asset from the first shot only: the episode still
        # casts it through the second shot.
        breakdown_service.update_casting(first_shot.id, [])
        episode_casting = breakdown_service.get_casting(self.episode.id)
        self.assertEqual(
            [cast["asset_id"] for cast in episode_casting], [asset_id]
        )

        # Un-cast the asset from the last remaining shot: it must now
        # disappear from the episode casting (and asset list) too.
        breakdown_service.update_casting(other_shot.id, [])
        episode_casting = breakdown_service.get_casting(self.episode.id)
        self.assertEqual(episode_casting, [])
        episode = entities_service.get_entity(self.episode.id)
        self.assertEqual(episode["nb_entities_out"], 0)

    def test_update_casting_removal_from_shot_emits_episode_event(self):
        """
        Detaching the asset from the episode (because it is no longer
        casted in any of its shots) must emit an episode:casting-update
        event, the same way casting it in a shot emits an asset:update
        event, so listeners can refresh the episode's asset list.
        """
        captured = self.capture_events("episode:casting-update")

        asset_id = str(self.asset.id)
        breakdown_service.update_casting(
            self.shot.id, [{"asset_id": asset_id, "nb_occurences": 1}]
        )
        self.assertEqual(captured, [])

        breakdown_service.update_casting(self.shot.id, [])
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["episode_id"], str(self.episode.id))
        self.assertEqual(captured[0]["removed_asset_ids"], [asset_id])
        self.assertEqual(captured[0]["nb_entities_out"], 0)

    def test_update_casting_removal_from_shot_without_episode_does_not_fail(
        self,
    ):
        """
        A shot whose sequence has no parent episode (non-episodic
        production) must not break when an asset is un-cast from it.
        """
        no_episode_sequence = Entity.create(
            name="NoEpisodeSequence",
            project_id=self.project.id,
            entity_type_id=self.sequence_type.id,
        )
        no_episode_shot = Entity.create(
            name="NoEpisodeShot",
            project_id=self.project.id,
            entity_type_id=self.shot_type.id,
            parent_id=no_episode_sequence.id,
        )
        asset_id = str(self.asset.id)
        breakdown_service.update_casting(
            no_episode_shot.id,
            [{"asset_id": asset_id, "nb_occurences": 1}],
        )
        breakdown_service.update_casting(no_episode_shot.id, [])
        casting = breakdown_service.get_casting(no_episode_shot.id)
        self.assertEqual(casting, [])

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
        self.assertNotIn(self.asset_character_id, instances)

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

    def test_get_entity_link(self):
        breakdown_service.update_casting(
            self.shot.id,
            [{"asset_id": self.asset_id, "nb_occurences": 3}],
        )
        link = breakdown_service.get_entity_link(self.shot_id, self.asset_id)
        self.assertEqual(link["nb_occurences"], 3)
        self.assertIsNone(
            breakdown_service.get_entity_link(
                self.shot_id, self.asset_character_id
            )
        )

    def test_refresh_all_shot_casting_stats(self):
        """
        The command that rebuilds the casting stats of the whole instance,
        used after a change that invalidates them in bulk.
        """
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        projects_service.create_project_task_type_link(
            self.project_id, str(self.task_type_animation.id), 1
        )
        task = self.generate_fixture_shot_task(
            task_type_id=str(self.task_type_animation.id)
        )
        self.asset.update({"ready_for": str(self.task_type_animation.id)})
        breakdown_service.update_casting(
            self.shot.id, [{"asset_id": self.asset_id, "nb_occurences": 1}]
        )
        task.update({"nb_assets_ready": 0})

        breakdown_service.refresh_all_shot_casting_stats()

        self.assertEqual(
            tasks_service.get_task(str(task.id))["nb_assets_ready"], 1
        )


class CastingReadyStatsTestCase(ApiDBTestCase):
    """
    An asset counts as ready for a task when the step it is ready for comes
    at or after that task in the pipeline order, which the project task type
    links define. refresh_casting_stats stores the count on each shot task.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset_types()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_asset()
        self.generate_fixture_asset_character()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.project_id = str(self.project.id)
        self.shot_id = str(self.shot.id)
        self.asset_id = str(self.asset.id)
        self.asset_character_id = str(self.asset_character.id)

        compositing = tasks_service.get_or_create_task_type(
            self.department_animation.serialize(),
            "compositing",
            color="#FFFFFF",
            short_name="compo",
            for_entity="Shot",
        )
        self.layout_id = str(self.task_type_layout.id)
        self.animation_id = str(self.task_type_animation.id)
        self.compositing_id = compositing["id"]
        for position, task_type_id in enumerate(
            [self.layout_id, self.animation_id, self.compositing_id], start=1
        ):
            projects_service.create_project_task_type_link(
                self.project_id, task_type_id, position
            )
        self.task_layout = self.generate_fixture_shot_task(
            task_type_id=self.layout_id
        )
        self.task_animation = self.generate_fixture_shot_task(
            task_type_id=self.animation_id
        )
        self.task_compositing = self.generate_fixture_shot_task(
            task_type_id=self.compositing_id
        )
        self.priority_map = breakdown_service._get_task_type_priority_map(
            self.project_id
        )

    def assert_ready_counts(self, layout, animation, compositing):
        counts = [
            tasks_service.get_task(str(task.id))["nb_assets_ready"]
            for task in [
                self.task_layout,
                self.task_animation,
                self.task_compositing,
            ]
        ]
        self.assertEqual(counts, [layout, animation, compositing])

    def cast_in_the_shot(self, *asset_ids):
        breakdown_service.update_casting(
            self.shot_id,
            [{"asset_id": str(a), "nb_occurences": 1} for a in asset_ids],
        )

    def set_ready_for(self, asset_id, task_type_id):
        assets_service.get_asset_raw(asset_id).update(
            {"ready_for": task_type_id}
        )

    def test_priority_map_follows_the_project_task_type_links(self):
        self.assertEqual(
            [
                self.priority_map[self.layout_id],
                self.priority_map[self.animation_id],
                self.priority_map[self.compositing_id],
            ],
            [1, 2, 3],
        )

        # Another production ordering the same task types differently does
        # not reach this one.
        self.generate_fixture_project_standard()
        projects_service.create_project_task_type_link(
            str(self.project_standard.id), self.compositing_id, 9
        )
        self.assertEqual(
            breakdown_service._get_task_type_priority_map(self.project_id)[
                self.compositing_id
            ],
            3,
        )

    def test_an_asset_is_ready_up_to_the_step_it_is_ready_for(self):
        asset = {"ready_for": self.animation_id, "is_shared": False}
        ready = [
            breakdown_service._is_asset_ready(asset, task, self.priority_map)
            for task in [
                self.task_layout,
                self.task_animation,
                self.task_compositing,
            ]
        ]
        self.assertEqual(ready, [True, True, False])

    def test_a_shared_asset_is_ready_everywhere_outside_its_production(self):
        """
        Inside its own production a shared asset follows the same order as
        any other. Borrowed by another production, the order does not apply.
        """
        asset = {
            "ready_for": self.animation_id,
            "is_shared": True,
            "project_id": self.project_id,
        }
        self.assertFalse(
            breakdown_service._is_asset_ready(
                asset, self.task_compositing, self.priority_map
            )
        )

        asset["project_id"] = "000000000000000000000000"
        self.assertTrue(
            breakdown_service._is_asset_ready(
                asset, self.task_compositing, self.priority_map
            )
        )

    def test_refresh_casting_stats_counts_the_ready_assets(self):
        self.cast_in_the_shot(self.asset_id, self.asset_character_id)
        self.set_ready_for(self.asset_id, self.animation_id)
        self.set_ready_for(self.asset_character_id, self.compositing_id)

        breakdown_service.refresh_casting_stats(
            assets_service.get_asset(self.asset_id)
        )

        # Both are ready for layout and animation, only the character is
        # ready for compositing.
        self.assert_ready_counts(2, 2, 1)

    def test_an_archived_asset_stops_counting(self):
        self.cast_in_the_shot(self.asset_id, self.asset_character_id)
        self.set_ready_for(self.asset_id, self.animation_id)
        self.set_ready_for(self.asset_character_id, self.compositing_id)
        breakdown_service.refresh_casting_stats(
            assets_service.get_asset(self.asset_id)
        )

        # A task on the asset makes the removal a cancellation.
        self.generate_fixture_task(
            name="Asset Task",
            entity_id=self.asset_id,
            task_type_id=self.layout_id,
        )
        assets_service.remove_asset(self.asset_id, force=False)

        self.assert_ready_counts(1, 1, 1)

    def test_a_deleted_asset_stops_counting(self):
        temp_asset = self.generate_fixture_asset("TempAsset")
        temp_asset_id = str(temp_asset.id)
        self.cast_in_the_shot(temp_asset_id, self.asset_character_id)
        self.set_ready_for(temp_asset_id, self.animation_id)
        self.set_ready_for(self.asset_character_id, self.compositing_id)
        breakdown_service.refresh_casting_stats(
            assets_service.get_asset(temp_asset_id)
        )
        self.assert_ready_counts(2, 2, 1)

        assets_service.remove_asset(temp_asset_id)

        self.assert_ready_counts(1, 1, 1)
