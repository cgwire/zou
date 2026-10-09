import pytest
from tests.base import ApiDBTestCase

from zou.app.services import entity_types_service, concepts_service
from zou.app.exceptions import (
    AssetTypeNotFoundException,
    EntityTypeNotFoundException,
)
from tests.services.cases import AssetsTestCase, ShotsTestCase

UNKNOWN = "00000000-0000-0000-0000-000000000000"


class AssetTypeTestCase(AssetsTestCase):
    def test_get_asset_types(self):
        asset_types = entity_types_service.get_asset_types()
        self.assertEqual(
            [asset_type["name"] for asset_type in asset_types], ["Props"]
        )

    def test_get_asset_types_by_name(self):
        """
        A criterion is read off the asset types themselves. Read off the
        assets instead, the two tables cross joined and the name of a type
        matched no asset, so the listing came back empty.
        """
        self.a_character()
        asset_types = entity_types_service.get_asset_types(
            {"name": "Character"}
        )
        self.assertEqual(
            [asset_type["name"] for asset_type in asset_types], ["Character"]
        )

    def test_get_asset_types_by_project(self):
        """
        A production is not a column of the asset type table: the criterion
        is which types the production has assets of. Handed to the generic
        criterion helper it restricted nothing, and the route documenting
        it listed every type of the instance.
        """
        self.a_character()
        self.generate_fixture_project_standard()
        self.generate_fixture_asset(
            "Elsewhere",
            asset_type_id=self.asset_type_environment.id,
            project_id=self.project_standard.id,
        )

        asset_types = entity_types_service.get_asset_types(
            {"project_id": str(self.project.id)}
        )

        self.assertEqual(
            sorted(asset_type["name"] for asset_type in asset_types),
            ["Character", "Props"],
        )

    def test_get_asset_type(self):
        asset_type = entity_types_service.get_asset_type(self.asset_type.id)
        self.assertDictEqual(
            asset_type,
            self.asset_type.serialize(obj_type="AssetType", relations=True),
        )

    def test_get_asset_type_of_a_temporal_type(self):
        """
        A shot type is an entity type too, and reading it as an asset type
        would let the asset routes serve shots.
        """
        self.assertRaises(
            AssetTypeNotFoundException,
            entity_types_service.get_asset_type,
            str(self.shot_type.id),
        )

    def test_get_or_create_asset_type(self):
        asset_type = entity_types_service.get_or_create_asset_type(
            self.asset_type.name
        )
        self.assertDictEqual(
            asset_type, self.asset_type.serialize(obj_type="AssetType")
        )
        asset_type = entity_types_service.get_or_create_asset_type(
            "New asset type"
        )
        self.assertEqual(asset_type["name"], "New asset type")

    def test_a_new_asset_type_shows_up_in_the_memoized_listing(self):
        """
        The criterionless listing is memoized, so creating a type has to
        drop it.
        """
        entity_types_service.get_asset_types()
        entity_types_service.get_or_create_asset_type("Vehicle")
        self.assertIn(
            "Vehicle",
            [
                asset_type["name"]
                for asset_type in entity_types_service.get_asset_types()
            ],
        )

    def test_is_asset_type(self):
        self.assertTrue(entity_types_service.is_asset_type(self.asset_type))
        self.assertFalse(entity_types_service.is_asset_type(self.shot_type))
        self.assertFalse(
            entity_types_service.is_asset_type(self.sequence_type)
        )
        self.assertFalse(entity_types_service.is_asset_type(self.episode_type))

    def test_is_asset_type_of_a_serialized_type(self):
        """
        The importers hand over dicts rather than rows.
        """
        self.assertTrue(
            entity_types_service.is_asset_type(self.asset_type.serialize())
        )
        self.assertFalse(
            entity_types_service.is_asset_type(self.shot_type.serialize())
        )


class AssetReadTestCase(AssetsTestCase):
    def test_is_asset(self):
        self.assertTrue(entity_types_service.is_asset(self.asset))
        self.assertFalse(entity_types_service.is_asset(self.shot))

    def test_is_asset_dict(self):
        self.assertTrue(
            entity_types_service.is_asset_dict(self.asset.serialize())
        )
        self.assertFalse(
            entity_types_service.is_asset_dict(self.shot.serialize())
        )


class ConceptsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()

    def a_concept(self, name, project=None, **kwargs):
        return concepts_service.create_concept(
            str((project or self.project).id), name, **kwargs
        )

    def a_concept_with_a_task(self, name):
        """
        A concept and one task on it, with the whole chain a task needs.
        """
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        concept = self.a_concept(name)
        task = self.generate_fixture_task(
            entity_id=concept["id"], task_type_id=self.task_type.id
        )
        return concept, task

    def test_create_concept(self):
        concept = self.a_concept("Concept 1", description="A cool concept")

        self.assertEqual(concept["name"], "Concept 1")
        self.assertEqual(concept["project_id"], str(self.project.id))
        self.assertEqual(concept["description"], "A cool concept")
        self.assertEqual(
            concept["entity_type_id"],
            entity_types_service.get_concept_type()["id"],
        )

    def test_is_concept(self):
        concept = self.a_concept("Is Concept")
        self.assertTrue(entity_types_service.is_concept(concept))

        self.generate_fixture_asset()
        asset = self.asset.serialize()
        self.assertFalse(entity_types_service.is_concept(asset))


class EditUtilsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_episode()
        self.generate_fixture_edit(parent_id=self.episode.id)
        self.generate_fixture_asset()

    def the_chain_a_task_needs(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()

    def test_get_edit_type(self):
        edit_type = entity_types_service.get_edit_type()
        self.assertEqual(edit_type["name"], "Edit")

    def test_is_edit(self):
        self.assertTrue(entity_types_service.is_edit(self.edit.serialize()))
        self.assertFalse(entity_types_service.is_edit(self.asset.serialize()))


class EntityTypeTestCase(ApiDBTestCase):
    """
    Entity types are a tiny, heavily read table: every lookup is memoized
    for four minutes, and two of the three lookups create the row they do
    not find.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset_type()

    def test_get_entity_type(self):
        self.assertEqual(
            entity_types_service.get_entity_type(self.asset_type.id),
            self.asset_type.serialize(),
        )

        with pytest.raises(EntityTypeNotFoundException):
            entity_types_service.get_entity_type(UNKNOWN)

    def test_get_entity_type_by_name(self):
        self.assertEqual(
            entity_types_service.get_entity_type_by_name(self.asset_type.name),
            self.asset_type.serialize(),
        )

    def test_get_entity_type_by_name_creates_what_it_cannot_find(self):
        entity_type = entity_types_service.get_entity_type_by_name("Matte")

        self.assertEqual(entity_type["name"], "Matte")
        self.assertEqual(
            entity_types_service.get_entity_type_by_name("Matte")["id"],
            entity_type["id"],
        )

    def test_get_entity_type_by_name_or_not_found(self):
        self.assertEqual(
            entity_types_service.get_entity_type_by_name_or_not_found(
                self.asset_type.name
            )["id"],
            str(self.asset_type.id),
        )

        with pytest.raises(EntityTypeNotFoundException):
            entity_types_service.get_entity_type_by_name_or_not_found("Matte")

    def test_a_renamed_type_is_read_again_after_the_cache_is_dropped(self):
        entity_types_service.get_entity_type(self.asset_type.id)

        self.asset_type.update({"name": "Sets"})
        entity_types_service.clear_entity_type_cache(str(self.asset_type.id))

        self.assertEqual(
            entity_types_service.get_entity_type(self.asset_type.id)["name"],
            "Sets",
        )
        self.assertEqual(
            entity_types_service.get_entity_type_by_name("Sets")["id"],
            str(self.asset_type.id),
        )

    def test_get_temporal_entity_type_by_name(self):
        """
        Meant to drop a cached None left by an older lookup and try again.
        The retry is unreachable today, since get_entity_type_by_name
        creates the row it cannot find and so never answers None: only the
        first half is pinned here.
        """
        self.assertEqual(
            entity_types_service.get_temporal_entity_type_by_name("Edit")[
                "name"
            ],
            "Edit",
        )

    def test_is_edit(self):
        edit_type = entity_types_service.get_temporal_entity_type_by_name(
            "Edit"
        )

        self.assertTrue(
            entity_types_service.is_edit({"entity_type_id": edit_type["id"]})
        )
        self.assertFalse(
            entity_types_service.is_edit(
                {"entity_type_id": str(self.asset_type.id)}
            )
        )


class EntityTypeMovedTestCase(ShotsTestCase):
    """
    Shots, sequences, episodes and scenes are all rows of the entity table:
    only the entity type tells them apart.
    """

    def test_each_temporal_type_is_named_after_itself(self):
        for get_type, name in [
            (entity_types_service.get_shot_type, "Shot"),
            (entity_types_service.get_sequence_type, "Sequence"),
            (entity_types_service.get_episode_type, "Episode"),
            (entity_types_service.get_scene_type, "Scene"),
            (entity_types_service.get_edit_type, "Edit"),
        ]:
            with self.subTest(name=name):
                self.assertEqual(get_type()["name"], name)

    def test_an_entity_is_recognized_by_its_type(self):
        entities = {
            "shot": self.shot,
            "sequence": self.sequence,
            "scene": self.scene,
            "episode": self.episode,
            "asset": self.asset,
        }
        predicates = {
            "shot": entity_types_service.is_shot,
            "sequence": entity_types_service.is_sequence,
            "scene": entity_types_service.is_scene,
            "episode": entity_types_service.is_episode,
        }
        for kind, is_kind in predicates.items():
            for name, entity in entities.items():
                with self.subTest(predicate=kind, entity=name):
                    self.assertEqual(is_kind(entity.serialize()), kind == name)
