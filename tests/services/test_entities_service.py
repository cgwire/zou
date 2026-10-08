import pytest

from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity, EntityLink
from zou.app.services import (
    assets_service,
    deletion_service,
    entities_service,
    entity_types_service,
    cascade_deletion_service,
    tasks_service,
)

from zou.app.exceptions import (
    EntityLinkNotFoundException,
    EntityNotFoundException,
)
from zou.app.services import (
    assets_service,
    concepts_service,
    edits_service,
    entities_service,
    shots_service,
    entity_types_service,
)

UNKNOWN = "00000000-0000-0000-0000-000000000000"


class EntityTestCase(ApiDBTestCase):
    """
    The entity lookups every other service builds on, and the one write
    this service owns: setting an entity's main preview.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_task()
        self.generate_fixture_preview_file()
        self.asset_id = str(self.asset.id)
        self.preview_file_id = str(self.preview_file.id)

    def test_get_entity_raw(self):
        self.assertEqual(
            entities_service.get_entity_raw(self.asset.id).id, self.asset.id
        )

        with pytest.raises(EntityNotFoundException):
            entities_service.get_entity_raw(UNKNOWN)

    def test_get_entity(self):
        self.assertEqual(
            entities_service.get_entity(self.asset.id),
            self.asset.serialize(),
        )

        with pytest.raises(EntityNotFoundException):
            entities_service.get_entity(UNKNOWN)

    def test_a_renamed_entity_is_read_again_after_the_cache_is_dropped(self):
        # Warmed with the id read off the row, dropped with its string
        # form: the memoization keys on the argument, and the two callers
        # must not end up on two entries.
        entities_service.get_entity(self.asset.id)
        entities_service.get_entity(self.asset_id)

        self.asset.update({"name": "Rock"})
        entities_service.clear_entity_cache(self.asset_id)

        self.assertEqual(
            entities_service.get_entity(self.asset.id)["name"], "Rock"
        )
        self.assertEqual(
            entities_service.get_entity(self.asset_id)["name"], "Rock"
        )

    def test_get_for_entity_from_task(self):
        """
        The name of the kind of entity a task hangs on. Every asset type a
        studio invents comes back as "Asset"; the temporal ones keep their
        own name.
        """
        shot_task = self.generate_fixture_shot_task()

        self.assertEqual(
            entities_service.get_for_entity_from_task(self.task.serialize()),
            "Asset",
        )
        self.assertEqual(
            entities_service.get_for_entity_from_task(shot_task.serialize()),
            "Shot",
        )
        scene_task = self.generate_fixture_scene_task()
        self.assertEqual(
            entities_service.get_for_entity_from_task(scene_task.serialize()),
            "Scene",
        )


class EntityListingTestCase(ApiDBTestCase):
    """
    The entities of one production, of one type.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

    def test_get_entities_for_project(self):
        self.generate_fixture_project_standard()
        # Named to sort first while created last, and one asset of the same
        # name in another production, which must not show up.
        self.generate_fixture_asset("Anvil")
        self.generate_fixture_asset(
            "Anvil", project_id=self.project_standard.id
        )

        assets = entities_service.get_entities_for_project(
            str(self.project.id), str(self.asset_type.id), obj_type="Asset"
        )

        self.assertEqual(
            [asset["name"] for asset in assets], ["Anvil", "Tree"]
        )
        self.assertEqual(assets[0]["type"], "Asset")

    def test_get_entities_for_project_is_scoped_to_its_type(self):
        # The shot shares the production, not the type.
        assets = entities_service.get_entities_for_project(
            str(self.project.id), str(self.asset_type.id)
        )

        self.assertEqual([asset["name"] for asset in assets], ["Tree"])

    def test_get_entities_for_project_holds_one_episode(self):
        # Both generators repoint the attribute they name, so what belongs
        # to the first episode has to be read before the second is made.
        here, here_episode_id = self.sequence.name, str(self.episode.id)
        elsewhere = self.generate_fixture_episode("E02")
        self.generate_fixture_sequence("S02", episode_id=elsewhere.id)

        sequences = entities_service.get_entities_for_project(
            str(self.project.id),
            str(self.sequence_type.id),
            episode_id=here_episode_id,
        )

        self.assertEqual([sequence["name"] for sequence in sequences], [here])


class EntityTasksTestCase(ApiDBTestCase):
    """
    The tasks hanging off an entity, dispatched to the listing of the right
    kind.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()

    def assert_the_tasks_of_the_entity_are_listed(self, entity_id):
        """
        The listing carries every task of that entity and nothing else,
        whatever kind of entity it is.
        """
        entity = entities_service.get_entity(str(entity_id))

        tasks = tasks_service.get_entity_tasks(entity)

        self.assertGreater(len(tasks), 0)
        for task in tasks:
            self.assertEqual(task["entity_id"], str(entity_id))
            self.assertIn("task_type_name", task)
            self.assertIn("id", task)

    def test_get_entity_tasks_shot(self):
        self.assert_the_tasks_of_the_entity_are_listed(self.shot.id)

    def test_get_entity_tasks_asset(self):
        self.assert_the_tasks_of_the_entity_are_listed(self.asset.id)

    def test_get_entity_tasks_no_tasks(self):
        shot = entities_service.get_entity(str(self.shot.id))
        deletion_service.remove_task(str(self.shot_task.id), force=True)

        self.assertEqual(tasks_service.get_entity_tasks(shot), [])

    def test_get_entities_and_tasks(self):
        self.generate_fixture_sequence_task()

        sequences = entities_service.get_entities_and_tasks()

        # Every entity carrying a task, of whatever kind, each with its
        # own tasks and no other.
        by_name = {entity["name"]: entity for entity in sequences}
        self.assertEqual(sorted(by_name), ["P01", "S01", "Tree"])
        for name, entity in by_name.items():
            with self.subTest(name=name):
                self.assertEqual(
                    [task["entity_id"] for task in entity["tasks"]],
                    [entity["id"]],
                )


class EntityLinkTestCase(ApiDBTestCase):
    """
    The casting links between entities: which asset appears in which shot.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.project_id = str(self.project.id)

    def a_link(self, nb_occurences=1, label=""):
        return EntityLink.create(
            entity_in_id=self.shot.id,
            entity_out_id=self.asset.id,
            nb_occurences=nb_occurences,
            label=label,
        )

    def test_get_entity_link(self):
        link = self.a_link(nb_occurences=3, label="hero")

        result = entities_service.get_entity_link(str(link.id))

        self.assertEqual(result["entity_in_id"], str(self.shot.id))
        self.assertEqual(result["entity_out_id"], str(self.asset.id))
        self.assertEqual(result["nb_occurences"], 3)
        self.assertEqual(result["label"], "hero")

    def test_get_entity_link_that_is_not_there(self):
        with pytest.raises(EntityLinkNotFoundException):
            entities_service.get_entity_link(UNKNOWN)

    def test_get_entity_links_for_project(self):
        link = self.a_link(nb_occurences=2, label="hero")

        links = entities_service.get_entity_links_for_project(self.project_id)

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["id"], link.id)
        self.assertEqual(links[0]["nb_occurences"], 2)
        self.assertEqual(links[0]["label"], "hero")
        self.assertEqual(links[0]["type"], "EntityLink")

    def test_get_entity_links_for_project_is_scoped_to_its_production(self):
        self.a_link()
        elsewhere = self.generate_fixture_project_standard()

        self.assertEqual(
            entities_service.get_entity_links_for_project(str(elsewhere.id)),
            [],
        )

    def test_get_entity_links_for_project_is_bounded(self):
        self.a_link()
        second_shot = self.generate_fixture_shot("S02")
        EntityLink.create(
            entity_in_id=second_shot.id, entity_out_id=self.asset.id
        )

        self.assertEqual(
            len(
                entities_service.get_entity_links_for_project(
                    self.project_id, limit=1
                )
            ),
            1,
        )
        # The paged branch answers with the envelope the listings use.
        paged = entities_service.get_entity_links_for_project(
            self.project_id, page=1, limit=1
        )
        self.assertEqual(len(paged["data"]), 1)
        self.assertEqual(paged["nb_pages"], 2)


class EntityCacheInvalidationTestCase(ApiDBTestCase):
    """
    An asset, a shot, a sequence, an episode, an edit and a concept are all
    rows of the entity table. Each has a service of its own with its own
    memoized serialization, and the generic entities_service.get_entity
    reads the same row through a cache of its own.

    Whoever drops one has to drop the other, or a rename made through one
    service stays invisible to everything reading through the other:
    entities_service builds the breadcrumbs of the news feed, the
    notifications and the playlists that way.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

    def assert_the_rename_is_visible_through_both(self, entity_id, clear):
        """
        Warm both caches, rename the row underneath, then drop the caches
        the way the service does.
        """
        entity_id = str(entity_id)
        entities_service.get_entity(entity_id)
        entity = entities_service.get_entity_raw(entity_id)

        entity.update({"name": "Renamed"})
        clear(entity_id)

        self.assertEqual(
            entities_service.get_entity(entity_id)["name"], "Renamed"
        )

    def test_clearing_an_asset_clears_the_entity(self):
        self.assert_the_rename_is_visible_through_both(
            self.asset.id, assets_service.clear_asset_cache
        )

    def test_clearing_a_shot_clears_the_entity(self):
        self.assert_the_rename_is_visible_through_both(
            self.shot.id, shots_service.clear_shot_cache
        )

    def test_clearing_a_sequence_clears_the_entity(self):
        self.assert_the_rename_is_visible_through_both(
            self.sequence.id, shots_service.clear_sequence_cache
        )

    def test_clearing_an_episode_clears_the_entity(self):
        self.assert_the_rename_is_visible_through_both(
            self.episode.id, shots_service.clear_episode_cache
        )

    def test_clearing_an_edit_clears_the_entity(self):
        edit = self.generate_fixture_edit()
        self.assert_the_rename_is_visible_through_both(
            edit.id, edits_service.clear_edit_cache
        )

    def test_clearing_a_concept_clears_the_entity(self):
        concept = concepts_service.create_concept(
            str(self.project.id), "Concept"
        )
        self.assert_the_rename_is_visible_through_both(
            concept["id"], concepts_service.clear_concept_cache
        )

    def test_clearing_an_asset_type_clears_the_entity_type(self):
        # Asset types are rows of the entity type table.
        asset_type_id = str(self.asset_type.id)
        entity_types_service.get_entity_type(asset_type_id)

        self.asset_type.update({"name": "Sets"})
        entity_types_service.clear_asset_type_cache(asset_type_id)

        self.assertEqual(
            entity_types_service.get_entity_type(asset_type_id)["name"], "Sets"
        )

    def test_cancelling_a_shot_is_visible_through_the_entity(self):
        # The service path, end to end: nothing here calls the entity cache
        # itself.
        shot_id = str(self.shot.id)
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_shot_task()
        self.assertFalse(entities_service.get_entity(shot_id)["canceled"])

        cascade_deletion_service.remove_shot(shot_id)

        self.assertTrue(entities_service.get_entity(shot_id)["canceled"])

    def test_renaming_an_asset_is_visible_through_the_entity(self):
        asset_id = str(self.asset.id)
        self.assertEqual(entities_service.get_entity(asset_id)["name"], "Tree")

        assets_service.update_asset(asset_id, {"name": "Rock"})

        self.assertEqual(entities_service.get_entity(asset_id)["name"], "Rock")


class EntityNameTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_asset()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.sequence_dict = self.sequence.serialize()
        self.generate_fixture_task_type()
        self.task_type_dict = self.task_type_animation.serialize()
        self.asset_task = self.generate_fixture_task().serialize()
        self.shot_task = self.generate_fixture_shot_task().serialize()

    def a_sequence_under_no_episode(self, name="S02"):
        """
        generate_fixture_sequence reads episode_id=None as "the usual
        episode", so a sequence with nothing above it is built here.
        """
        return Entity.create(
            name=name,
            project_id=self.project.id,
            entity_type_id=self.sequence_type.id,
        )

    def test_get_full_entity_name(self):
        """
        Where an entity sits, read upwards: an asset under its type, a
        sequence and a shot under their episode, an episode alone.
        """
        cases = {
            self.asset.id: "Props / Tree",
            self.episode.id: "E01",
            self.sequence.id: "E01 / S01",
            self.shot.id: "E01 / S01 / P01",
        }
        for entity_id, expected in cases.items():
            with self.subTest(expected=expected):
                name, _, _ = entities_service.get_full_entity_name(entity_id)
                self.assertEqual(name, expected)

    def test_get_full_entity_name_of_a_flat_production(self):
        # A sequence with no episode above it, and the shot under it.
        sequence = self.a_sequence_under_no_episode()
        shot = self.generate_fixture_shot("P02", sequence_id=sequence.id)

        self.assertEqual(
            entities_service.get_full_entity_name(sequence.id)[0], "S02"
        )
        self.assertEqual(
            entities_service.get_full_entity_name(shot.id)[0], "S02 / P02"
        )

    def test_get_full_entity_names_agrees_with_the_single_lookup(self):
        """
        The batch version walks the same branches in its own code, so what
        matters is that the two never disagree. Every kind of entity is
        represented here, with and without an episode above it.
        """
        sequence = self.a_sequence_under_no_episode()
        flat_shot = self.generate_fixture_shot("P02", sequence_id=sequence.id)
        entity_ids = [
            str(entity.id)
            for entity in [
                self.asset,
                self.episode,
                self.sequence,
                self.shot,
                sequence,
                flat_shot,
            ]
        ]

        names = entities_service.get_full_entity_names(entity_ids)

        self.assertEqual(
            names,
            {
                entity_id: entities_service.get_full_entity_name(entity_id)
                for entity_id in entity_ids
            },
        )

    def test_get_full_entity_names_of_nothing(self):
        self.assertEqual(entities_service.get_full_entity_names([]), {})
