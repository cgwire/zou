from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.services import (
    assets_service,
    breakdown_service,
    entities_service,
    projects_service,
    shots_service,
    tasks_service,
)


class BreakdownTestCase(ApiDBTestCase):
    """
    One episode holding a sequence, a shot and a scene, and two assets of
    two types: enough to cast, to instantiate, and to tell the two apart.
    """

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
        self.episode_id = str(self.episode.id)
        self.sequence_id = str(self.sequence.id)
        self.shot_id = str(self.shot.id)
        self.scene_id = str(self.scene.id)
        self.asset_id = str(self.asset.id)
        self.asset_character_id = str(self.asset_character.id)

    def cast(self, entity_id, *asset_ids, nb_occurences=1):
        return breakdown_service.update_casting(
            str(entity_id),
            [
                {"asset_id": str(asset_id), "nb_occurences": nb_occurences}
                for asset_id in asset_ids
            ],
        )

    def cast_asset_ids(self, entity_id):
        return [
            cast["asset_id"]
            for cast in breakdown_service.get_casting(str(entity_id))
        ]


class CastingTestCase(BreakdownTestCase):
    """
    The assets an entity is made of.
    """

    def test_a_casting_is_read_back_with_the_names_of_its_assets(self):
        self.assertEqual(breakdown_service.get_casting(self.shot_id), [])

        breakdown_service.update_casting(
            self.shot_id,
            [
                {"asset_id": self.asset_id, "nb_occurences": 1},
                {"asset_id": self.asset_character_id, "nb_occurences": 3},
            ],
        )

        casting = sorted(
            breakdown_service.get_casting(self.shot_id),
            key=lambda cast: cast["nb_occurences"],
        )
        self.assertEqual(
            [
                (
                    cast["asset_id"],
                    cast["nb_occurences"],
                    cast["asset_name"],
                    cast["asset_type_name"],
                )
                for cast in casting
            ],
            [
                (self.asset_id, 1, self.asset.name, self.asset_type.name),
                (
                    self.asset_character_id,
                    3,
                    self.asset_character.name,
                    self.asset_type_character.name,
                ),
            ],
        )

    def test_a_new_casting_replaces_the_previous_one(self):
        self.cast(self.shot_id, self.asset_id, self.asset_character_id)

        self.cast(self.shot_id, self.asset_id)

        self.assertEqual(self.cast_asset_ids(self.shot_id), [self.asset_id])
        self.assertEqual(
            entities_service.get_entity(self.shot_id)["nb_entities_out"], 1
        )

    def test_the_number_of_occurrences_is_kept(self):
        self.cast(self.shot_id, self.asset_id, nb_occurences=3)
        link = breakdown_service.get_entity_link(self.shot_id, self.asset_id)
        self.assertEqual(link["nb_occurences"], 3)
        self.assertIsNone(
            breakdown_service.get_entity_link(
                self.shot_id, self.asset_character_id
            )
        )

    def test_casting_an_asset_already_cast_updates_the_link(self):
        """
        update_casting wipes the links before writing the new ones, so this
        is the path of a caller adding one asset to a casting: the CSV
        import, and the plugins.
        """
        breakdown_service.create_casting_link(
            self.shot_id, self.asset_id, nb_occurences=1, label="fixed"
        )

        breakdown_service.create_casting_link(
            self.shot_id, self.asset_id, nb_occurences=5, label="moving"
        )

        link = breakdown_service.get_entity_link(self.shot_id, self.asset_id)
        self.assertEqual(link["nb_occurences"], 5)
        self.assertEqual(link["label"], "moving")

    def test_a_cast_entry_missing_its_count_is_left_out(self):
        breakdown_service.update_casting(
            self.shot_id,
            [
                {"asset_id": self.asset_id, "nb_occurences": 1},
                {"asset_id": self.asset_character_id},
            ],
        )

        self.assertEqual(self.cast_asset_ids(self.shot_id), [self.asset_id])

    def test_a_casting_change_says_what_changed(self):
        """
        casting-update events must include added_asset_ids and
        removed_asset_ids so listeners know what changed without having
        to keep a client-side snapshot (cgwire/gazu#393).
        """
        captured = self.capture_events("shot:casting-update")

        self.cast(self.shot_id, self.asset_id, self.asset_character_id)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["shot_id"], self.shot_id)
        self.assertEqual(captured[0]["nb_entities_out"], 2)
        # Sorted on both sides: the service sorts these ids, but they are
        # random UUIDs, so an unsorted pair matches the sorted one half the
        # time and the order cannot be pinned without flakiness.
        self.assertEqual(
            sorted(captured[0]["added_asset_ids"]),
            sorted([self.asset_id, self.asset_character_id]),
        )
        self.assertEqual(captured[0]["removed_asset_ids"], [])

        self.cast(self.shot_id, self.asset_id)

        self.assertEqual(len(captured), 2)
        self.assertEqual(captured[1]["nb_entities_out"], 1)
        self.assertEqual(captured[1]["added_asset_ids"], [])
        self.assertEqual(
            captured[1]["removed_asset_ids"], [self.asset_character_id]
        )

        self.cast(self.shot_id, self.asset_id, self.asset_character_id)
        self.cast(self.shot_id)

        self.assertEqual(captured[-1]["nb_entities_out"], 0)
        self.assertEqual(captured[-1]["added_asset_ids"], [])
        self.assertEqual(
            sorted(captured[-1]["removed_asset_ids"]),
            sorted([self.asset_id, self.asset_character_id]),
        )

    def test_the_casting_of_an_asset_is_announced_as_its_own(self):
        captured = self.capture_events("asset:casting-update")
        self.cast(self.asset_id, self.asset_character_id)
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["asset_id"], self.asset_id)

    def test_a_shot_hanging_from_no_sequence_can_still_be_cast(self):
        """
        Casting an asset in a shot casts it in the parent episode too. A
        shot with no sequence leads to no episode, so there is nothing to
        do there: reading the sequence anyway turned the whole casting into
        a 404.
        """
        orphan = Entity.create(
            name="NOSEQ",
            project_id=self.project.id,
            entity_type_id=self.shot_type.id,
        )

        self.cast(orphan.id, self.asset_id)
        self.assertEqual(self.cast_asset_ids(orphan.id), [self.asset_id])

        self.cast(orphan.id)
        self.assertEqual(self.cast_asset_ids(orphan.id), [])

    def test_a_shot_whose_sequence_has_no_episode_can_still_be_cast(self):
        """
        The same, one level down: a production that does not cut its
        sequences into episodes.
        """
        sequence = Entity.create(
            name="NoEpisodeSequence",
            project_id=self.project.id,
            entity_type_id=self.sequence_type.id,
        )
        shot = Entity.create(
            name="NoEpisodeShot",
            project_id=self.project.id,
            entity_type_id=self.shot_type.id,
            parent_id=sequence.id,
        )

        self.cast(shot.id, self.asset_id)
        self.cast(shot.id)

        self.assertEqual(self.cast_asset_ids(shot.id), [])


class EpisodeCastingTestCase(BreakdownTestCase):
    """
    Casting an asset in a shot casts it in the parent episode too, and
    dropping it from the last shot that used it takes it back out.
    """

    def test_an_asset_cast_in_a_shot_is_cast_in_its_episode(self):
        self.cast(self.shot_id, self.asset_id)
        self.assertEqual(self.cast_asset_ids(self.episode_id), [self.asset_id])

    def test_the_episode_keeps_the_asset_while_another_shot_uses_it(self):
        """
        Removing an asset from one shot must not detach it from the episode
        while another shot of that episode still casts it
        (cgwire/kitsu#1388).
        """
        first_shot_id = self.shot_id
        other_shot_id = str(self.generate_fixture_shot("SH02").id)
        self.cast(first_shot_id, self.asset_id)
        self.cast(other_shot_id, self.asset_id)
        # Read before the change, so the count below comes from a cache
        # that has something to invalidate.
        self.assertEqual(
            entities_service.get_entity(self.episode_id)["nb_entities_out"], 1
        )

        self.cast(first_shot_id)

        self.assertEqual(self.cast_asset_ids(self.episode_id), [self.asset_id])

        self.cast(other_shot_id)

        self.assertEqual(self.cast_asset_ids(self.episode_id), [])
        self.assertEqual(
            entities_service.get_entity(self.episode_id)["nb_entities_out"], 0
        )

    def test_the_episode_keeps_an_asset_it_was_given_by_hand(self):
        """
        Only the episode links derived from a shot casting follow the shots.
        One a manager set from the episode breakdown is a decision of its
        own: dropping the asset from its last shot must not undo it.
        """
        self.cast(self.episode_id, self.asset_id)
        self.cast(self.shot_id, self.asset_id)

        self.cast(self.shot_id)

        self.assertEqual(self.cast_asset_ids(self.episode_id), [self.asset_id])
        self.assertEqual(
            entities_service.get_entity(self.episode_id)["nb_entities_out"], 1
        )

    def test_saving_the_episode_casting_makes_its_assets_its_own(self):
        """
        An asset that reached the episode through a shot becomes a decision
        of the episode once its casting is saved from the episode side.
        """
        self.cast(self.shot_id, self.asset_id)
        self.cast(self.episode_id, self.asset_id)

        self.cast(self.shot_id)

        self.assertEqual(self.cast_asset_ids(self.episode_id), [self.asset_id])

    def test_the_episode_losing_an_asset_is_announced(self):
        """
        The same way casting it in a shot emits an asset:update event, so
        listeners can refresh the asset list of the episode.
        """
        captured = self.capture_events("episode:casting-update")

        self.cast(self.shot_id, self.asset_id)
        self.assertEqual(captured, [])

        self.cast(self.shot_id)

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["episode_id"], self.episode_id)
        self.assertEqual(captured[0]["removed_asset_ids"], [self.asset_id])
        self.assertEqual(captured[0]["nb_entities_out"], 0)

    def test_an_asset_dropped_from_an_episode_leaves_its_shots(self):
        """
        The casting of an episode is the union of the castings of its
        shots: taking an asset out of the episode takes it out of every
        shot that used it.
        """
        self.cast(self.shot_id, self.asset_id)
        # Read before the change, so the count below comes from a cache
        # that has something to invalidate.
        self.assertEqual(
            shots_service.get_shot(self.shot_id)["nb_entities_out"], 1
        )

        self.cast(self.episode_id)

        self.assertEqual(self.cast_asset_ids(self.shot_id), [])
        self.assertEqual(
            shots_service.get_shot(self.shot_id)["nb_entities_out"], 0
        )
        self.assertEqual(
            entities_service.get_entity(self.shot_id)["nb_entities_out"], 0
        )


class AssetCastingTestCase(BreakdownTestCase):
    """
    Casting one asset at a time, the way the breakdown page works: the
    other assets of the entity are left as they are, whatever the caller
    believes the casting to be.
    """

    def test_casting_one_more_asset_leaves_the_others_alone(self):
        self.cast(self.shot_id, self.asset_id)

        breakdown_service.cast_asset(self.shot_id, self.asset_character_id)

        self.assertEqual(
            sorted(self.cast_asset_ids(self.shot_id)),
            sorted([self.asset_id, self.asset_character_id]),
        )
        self.assertEqual(
            entities_service.get_entity(self.shot_id)["nb_entities_out"], 2
        )

    def test_uncasting_an_asset_drops_it_alone(self):
        self.cast(self.shot_id, self.asset_id, self.asset_character_id)
        # Read before the change, so the count below comes from a cache
        # that has something to invalidate.
        self.assertEqual(
            entities_service.get_entity(self.shot_id)["nb_entities_out"], 2
        )

        breakdown_service.uncast_asset(self.shot_id, self.asset_id)

        self.assertEqual(
            self.cast_asset_ids(self.shot_id), [self.asset_character_id]
        )
        self.assertEqual(
            entities_service.get_entity(self.shot_id)["nb_entities_out"], 1
        )

    def test_casting_an_asset_again_sets_its_count_and_keeps_its_label(self):
        breakdown_service.cast_asset(
            self.shot_id, self.asset_id, 1, label="animate"
        )

        breakdown_service.cast_asset(self.shot_id, self.asset_id, 3)

        link = breakdown_service.get_entity_link(self.shot_id, self.asset_id)
        self.assertEqual(link["nb_occurences"], 3)
        self.assertEqual(link["label"], "animate")

        breakdown_service.cast_asset(
            self.shot_id, self.asset_id, label="fixed"
        )

        link = breakdown_service.get_entity_link(self.shot_id, self.asset_id)
        self.assertEqual(link["nb_occurences"], 3)
        self.assertEqual(link["label"], "fixed")

    def test_dropping_an_asset_from_an_episode_leaves_the_others_as_they_were(
        self,
    ):
        """
        The assets the episode got through its shots keep following the
        shots after one of them is dropped from the episode side.
        """
        other_shot_id = str(self.generate_fixture_shot("SH02").id)
        self.cast(self.shot_id, self.asset_id)
        self.cast(other_shot_id, self.asset_character_id)

        breakdown_service.uncast_asset(
            self.episode_id, self.asset_character_id
        )

        self.assertEqual(self.cast_asset_ids(other_shot_id), [])
        self.assertEqual(self.cast_asset_ids(self.episode_id), [self.asset_id])

        self.cast(self.shot_id)

        self.assertEqual(self.cast_asset_ids(self.episode_id), [])


class CastingListingTestCase(BreakdownTestCase):
    """
    The casting of a whole branch of the production, keyed by the entity it
    belongs to.
    """

    def test_the_casting_of_a_sequence_is_keyed_by_shot(self):
        first_shot_id = self.shot_id
        other_shot_id = str(self.generate_fixture_shot("SH02").id)
        self.cast(first_shot_id, self.asset_id, self.asset_character_id)
        self.cast(other_shot_id, self.asset_id)

        casting = breakdown_service.get_sequence_casting(self.sequence_id)

        self.assertEqual(len(casting[first_shot_id]), 2)
        self.assertEqual(len(casting[other_shot_id]), 1)

    def test_the_casting_of_every_sequence_is_scoped(self):
        first_shot_id = self.shot_id
        self.cast(first_shot_id, self.asset_id, self.asset_character_id)
        other_sequence = self.generate_fixture_sequence("SE02")
        other_shot_id = str(
            self.generate_fixture_shot(
                "SH02", sequence_id=other_sequence.id
            ).id
        )
        self.cast(other_shot_id, self.asset_id)

        casting = breakdown_service.get_all_sequences_casting(self.project_id)

        self.assertEqual(len(casting[first_shot_id]), 2)
        self.assertEqual(len(casting[other_shot_id]), 1)

    def test_the_casting_of_every_sequence_can_be_scoped_to_an_episode(self):
        self.cast(self.shot_id, self.asset_id)
        other_episode = self.generate_fixture_episode("E02")
        other_sequence = self.generate_fixture_sequence(
            "E02SE01", episode_id=other_episode.id
        )
        other_shot_id = str(
            self.generate_fixture_shot(
                "E02SH01", sequence_id=other_sequence.id
            ).id
        )
        self.cast(other_shot_id, self.asset_id)

        casting = breakdown_service.get_all_sequences_casting(
            None, other_episode.id
        )

        self.assertEqual(list(casting.keys()), [other_shot_id])

    def test_the_casting_of_an_asset_type_is_keyed_by_asset(self):
        environment_id = str(self.asset_type_environment.id)
        forest_id = str(
            self.generate_fixture_asset("Forest", "", environment_id).id
        )
        park_id = str(
            self.generate_fixture_asset("Park", "", environment_id).id
        )
        self.assertEqual(
            breakdown_service.get_asset_type_casting(
                self.project_id, environment_id
            ),
            {},
        )
        self.cast(forest_id, self.asset_id, self.asset_character_id)
        self.cast(park_id, self.asset_id)

        # An environment of another production, cast the same way.
        self.generate_fixture_project_standard()
        elsewhere = self.generate_fixture_asset(
            "Lake", "", environment_id, project_id=self.project_standard.id
        )
        self.cast(elsewhere.id, self.asset_id)

        casting = breakdown_service.get_asset_type_casting(
            self.project_id, environment_id
        )

        self.assertEqual(sorted(casting.keys()), sorted([forest_id, park_id]))
        # Each list is ordered by asset type name, then by asset name, so
        # the character comes before the props whatever order they were cast
        # in.
        self.assertEqual(
            [
                (entry["asset_type_name"], entry["asset_name"])
                for entry in casting[forest_id]
            ],
            [("Character", "Rabbit"), ("Props", "Tree")],
        )
        self.assertEqual(len(casting[park_id]), 1)

    def test_the_casting_of_every_episode_is_keyed_by_episode(self):
        """
        An episode of another production stays out.
        """
        self.cast(self.episode_id, self.asset_id, nb_occurences=2)

        self.generate_fixture_project_standard()
        elsewhere = self.generate_fixture_episode(
            name="E99", project_id=self.project_standard.id
        )
        self.cast(elsewhere.id, self.asset_id)

        castings = breakdown_service.get_production_episodes_casting(
            self.project_id
        )

        self.assertEqual(list(castings.keys()), [self.episode_id])
        self.assertEqual(
            [
                (entry["asset_name"], entry["nb_occurences"])
                for entry in castings[self.episode_id]
            ],
            [("Tree", 2)],
        )

    def test_where_an_asset_is_cast_comes_in_reading_order(self):
        """
        The shots first, ordered by episode, then sequence, then shot name,
        and the assets after them, ordered by asset type then asset name.
        Both halves are built in the order that disagrees with the answer,
        so the ordering has to do the work.
        """
        character_id = self.asset_character_id

        # generate_fixture_shot and generate_fixture_asset both repoint the
        # attribute they name, hence the locals.
        late_shot = self.shot
        early_shot = self.generate_fixture_shot("A01")
        for shot in [late_shot, early_shot]:
            self.cast(shot.id, character_id)

        late_asset = self.asset
        early_asset = self.generate_fixture_asset(
            "Forest", "", str(self.asset_type_environment.id)
        )
        for asset in [late_asset, early_asset]:
            self.cast(asset.id, character_id)

        cast_in = breakdown_service.get_cast_in(character_id)

        self.assertEqual(
            [
                entry.get("shot_name")
                for entry in cast_in
                if "shot_id" in entry
            ],
            [early_shot.name, late_shot.name],
        )
        self.assertEqual(
            [
                (entry["asset_type_name"], entry["asset_name"])
                for entry in cast_in
                if "asset_id" in entry
            ],
            [("Environment", early_asset.name), ("Props", late_asset.name)],
        )

    def test_where_an_asset_is_cast_names_its_whole_branch(self):
        self.cast(self.shot_id, self.asset_character_id)

        cast_in = breakdown_service.get_cast_in(self.asset_character_id)

        self.assertEqual(cast_in[0]["shot_name"], self.shot.name)
        self.assertEqual(cast_in[0]["sequence_name"], self.sequence.name)
        self.assertEqual(cast_in[0]["episode_name"], self.episode.name)


class AssetInstanceTestCase(BreakdownTestCase):
    """
    An instance is one copy of an asset dropped into a scene or a shot.
    Each is numbered inside the asset it copies.
    """

    def new_scene_instance(self, asset_id):
        return breakdown_service.add_asset_instance_to_scene(
            self.scene_id, str(asset_id)
        )

    def new_shot_instance(self, asset_instance_id):
        return breakdown_service.add_asset_instance_to_shot(
            self.shot_id, asset_instance_id
        )

    def test_an_instance_is_named_after_its_asset_and_its_number(self):
        self.assertEqual(
            breakdown_service.build_asset_instance_name(self.asset_id, 3),
            "Tree_0003",
        )
        self.assertEqual(
            breakdown_service.build_asset_instance_name(
                self.asset_character_id, 5
            ),
            "Rabbit_0005",
        )

    def test_the_instances_of_a_scene_are_numbered_in_order(self):
        self.assertEqual(
            breakdown_service.get_asset_instances_for_scene(self.scene_id), {}
        )
        # Three of the same asset, not two: the number of a new instance is
        # read off the highest existing one, and with a single instance
        # around any of them is the highest.
        for _ in range(3):
            self.new_scene_instance(self.asset_id)
        self.new_scene_instance(self.asset_character_id)

        instances = breakdown_service.get_asset_instances_for_scene(
            self.scene_id
        )

        self.assertEqual(
            [held["number"] for held in instances[self.asset_id]], [1, 2, 3]
        )
        self.assertEqual(
            [held["name"] for held in instances[self.asset_id]],
            ["Tree_0001", "Tree_0002", "Tree_0003"],
        )
        self.assertEqual(
            [held["number"] for held in instances[self.asset_character_id]],
            [1],
        )

    def test_an_instance_of_a_scene_is_added_to_a_shot(self):
        self.assertEqual(
            breakdown_service.get_asset_instances_for_shot(self.shot_id), {}
        )
        for asset_id in [
            self.asset_id,
            self.asset_id,
            self.asset_character_id,
        ]:
            instance = self.new_scene_instance(asset_id)
            self.new_shot_instance(instance["id"])

        instances = breakdown_service.get_asset_instances_for_shot(
            self.shot_id
        )

        self.assertEqual(
            [held["number"] for held in instances[self.asset_id]], [1, 2]
        )
        self.assertEqual(instances[self.asset_id][1]["name"], "Tree_0002")
        self.assertEqual(
            [held["number"] for held in instances[self.asset_character_id]],
            [1],
        )

        breakdown_service.remove_asset_instance_for_shot(
            self.shot_id, instance["id"]
        )

        self.assertNotIn(
            self.asset_character_id,
            breakdown_service.get_asset_instances_for_shot(self.shot_id),
        )

    def test_the_instances_of_an_asset_are_keyed_by_shot(self):
        self.assertEqual(
            breakdown_service.get_shot_asset_instances_for_asset(
                self.asset_id
            ),
            {},
        )
        for asset_id in [
            self.asset_id,
            self.asset_id,
            self.asset_character_id,
        ]:
            instance = self.new_scene_instance(asset_id)
            self.new_shot_instance(instance["id"])

        instances = breakdown_service.get_shot_asset_instances_for_asset(
            self.asset_id
        )

        self.assertEqual(len(instances[self.shot_id]), 2)

    def test_the_instances_of_an_asset_are_keyed_by_scene(self):
        self.assertEqual(
            breakdown_service.get_scene_asset_instances_for_asset(
                self.asset_id
            ),
            {},
        )
        for _ in range(3):
            self.new_scene_instance(self.asset_id)
        self.new_scene_instance(self.asset_character_id)

        instances = breakdown_service.get_scene_asset_instances_for_asset(
            self.asset_id
        )

        # Grouped by scene, and numbered in order inside each scene.
        self.assertEqual(
            [held["number"] for held in instances[self.scene_id]], [1, 2, 3]
        )


class CastingStatsTestCase(BreakdownTestCase):
    """
    The count of ready assets stored on each shot task.
    """

    def test_the_stats_of_the_whole_instance_are_rebuilt(self):
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
        self.cast(self.shot_id, self.asset_id)
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
