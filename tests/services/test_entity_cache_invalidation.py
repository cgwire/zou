from tests.base import ApiDBTestCase

from zou.app.services import (
    assets_service,
    concepts_service,
    edits_service,
    entities_service,
    shots_service,
)


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
        entities_service.get_entity_type(asset_type_id)

        self.asset_type.update({"name": "Sets"})
        assets_service.clear_asset_type_cache(asset_type_id)

        self.assertEqual(
            entities_service.get_entity_type(asset_type_id)["name"], "Sets"
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
