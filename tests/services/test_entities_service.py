import pytest

from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity, EntityLink
from zou.app.services import (
    assets_service,
    deletion_service,
    entities_service,
    entity_types_service,
)

from zou.app.exceptions import (
    EntityLinkNotFoundException,
    EntityNotFoundException,
    PreviewFileNotFoundException,
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

    def test_update_entity_preview(self):
        entities_service.update_entity_preview(
            self.asset_id, self.preview_file_id
        )

        asset = assets_service.get_asset(self.asset_id)
        self.assertEqual(asset["preview_file_id"], self.preview_file_id)

    def test_update_entity_preview_refuses_what_it_cannot_find(self):
        with pytest.raises(EntityNotFoundException):
            entities_service.update_entity_preview(
                self.preview_file_id, self.preview_file_id
            )

        with pytest.raises(PreviewFileNotFoundException):
            entities_service.update_entity_preview(
                self.asset_id, self.asset_id
            )

    def test_setting_a_preview_announces_it_under_the_entity_kind(self):
        """
        Two events: the generic one, and one named after the kind of
        entity, which is what each listing subscribes to. An asset type is
        any name the studio invented, so it is announced as "asset".
        """
        main = self.capture_events("preview-file:set-main")

        entities_service.update_entity_preview(
            self.asset_id, self.preview_file_id
        )

        self.assertEqual(
            [
                (
                    event["entity_id"],
                    event["preview_file_id"],
                    event["project_id"],
                )
                for event in main
            ],
            [
                (
                    self.asset_id,
                    self.preview_file_id,
                    str(self.asset.project_id),
                )
            ],
        )

    def test_setting_a_processing_preview_tells_its_status(self):
        """
        The pictures of a processing preview are not built yet: the event
        and the answer say so, for the clients to wait for them instead
        of asking for them.
        """
        preview_file_id = str(
            self.generate_fixture_preview_file(
                revision=2, status="processing"
            ).id
        )
        main = self.capture_events("preview-file:set-main")

        entity = entities_service.update_entity_preview(
            self.asset_id, preview_file_id
        )

        statuses = [event["preview_file_status"] for event in main]
        statuses.append(entity["preview_file_status"])
        self.assertEqual(statuses, ["processing", "processing"])
        # A Choice compares equal to its code: only its type tells it apart.
        self.assertEqual([type(status) for status in statuses], [str, str])

    def test_a_shot_is_announced_as_a_shot(self):
        captured = self.capture_events("shot:update")
        shot_id = str(self.shot.id)

        entities_service.update_entity_preview(shot_id, self.preview_file_id)

        self.assertEqual([event["shot_id"] for event in captured], [shot_id])

    def test_an_asset_is_announced_as_an_asset(self):
        captured = self.capture_events("asset:update")

        entities_service.update_entity_preview(
            self.asset_id, self.preview_file_id
        )

        self.assertEqual(
            [event["asset_id"] for event in captured], [self.asset_id]
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

        tasks = entities_service.get_entity_tasks(entity)

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

        self.assertEqual(entities_service.get_entity_tasks(shot), [])

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

    def test_remove_entity_link(self):
        link = self.a_link()

        removed = entities_service.remove_entity_link(str(link.id))

        self.assertEqual(removed["id"], str(link.id))
        with pytest.raises(EntityLinkNotFoundException):
            entities_service.get_entity_link(str(link.id))

    def test_remove_entity_link_refreshes_the_casting_of_the_shot(self):
        """
        Same path as uncasting from the breakdown: the shot counter the
        shots page divides by, and the casting-update its listeners wait for.
        """
        link = self.a_link()
        self.shot.update({"nb_entities_out": 1})
        captured = self.capture_events("shot:casting-update")

        entities_service.remove_entity_link(str(link.id))

        self.assertEqual(Entity.get(self.shot.id).nb_entities_out, 0)
        self.assertEqual(
            [event["removed_asset_ids"] for event in captured],
            [[str(self.asset.id)]],
        )

    def test_remove_entity_link_of_an_episode_leaves_its_shots_cast(self):
        self.a_link()
        episode = self.generate_fixture_episode("E99")
        self.sequence.update({"parent_id": episode.id})
        link = EntityLink.create(
            entity_in_id=episode.id, entity_out_id=self.asset.id
        )

        entities_service.remove_entity_link(str(link.id))

        self.assertIsNotNone(
            EntityLink.get_by(
                entity_in_id=self.shot.id, entity_out_id=self.asset.id
            )
        )

    def test_remove_entity_link_that_is_not_there(self):
        with pytest.raises(EntityLinkNotFoundException):
            entities_service.remove_entity_link(UNKNOWN)

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
    names_service builds the breadcrumbs of the news feed, the
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

        shots_service.remove_shot(shot_id)

        self.assertTrue(entities_service.get_entity(shot_id)["canceled"])

    def test_renaming_an_asset_is_visible_through_the_entity(self):
        asset_id = str(self.asset.id)
        self.assertEqual(entities_service.get_entity(asset_id)["name"], "Tree")

        assets_service.update_asset(asset_id, {"name": "Rock"})

        self.assertEqual(entities_service.get_entity(asset_id)["name"], "Rock")
