from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.services import assets_service, breakdown_service
from zou.app.services.exception import (
    AssetNotFoundException,
    AssetTypeNotFoundException,
)


class AssetsTestCase(ApiDBTestCase):
    """
    One production with a single asset type and a shot to cast into.
    Holds no test of its own.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

    def a_character(self):
        """
        A second asset, of a second type, so that a reading has something
        to order and something to leave out.
        """
        self.generate_fixture_asset_types()
        return self.generate_fixture_asset_character()


class AssetListTestCase(AssetsTestCase):
    """
    Listing assets of a production, which is the entity table minus
    everything positioned in time.
    """

    def test_get_assets(self):
        assets = assets_service.get_assets()
        self.assertEqual([asset["name"] for asset in assets], ["Tree"])

    def test_a_shot_is_not_an_asset(self):
        """
        Assets and shots share the entity table: the listing tells them
        apart by entity type, so the shot of the fixtures must not show
        up in it.
        """
        self.assertNotIn(
            str(self.shot.id),
            [asset["id"] for asset in assets_service.get_assets()],
        )

    def test_get_assets_with_episode_and_project_filters(self):
        """
        The episode criterion is a union of two sets: assets created in the
        episode, and assets cast into it. An asset of the production that is
        in neither does not appear.
        """
        episode = self.generate_fixture_episode()
        # generate_fixture_asset repoints self.asset on every named call.
        created_in = self.asset
        created_in.update({"source_id": episode.id})
        cast_in = self.generate_fixture_asset("Rock")
        self.generate_fixture_asset("Loose")
        breakdown_service.create_casting_link(episode.id, cast_in.id)

        assets = assets_service.get_assets(
            criterions={
                "episode_id": str(episode.id),
                "project_id": str(self.project.id),
            }
        )

        self.assertEqual(
            sorted(asset["name"] for asset in assets), ["Rock", "Tree"]
        )

    def test_get_assets_counts_an_asset_of_both_halves_once(self):
        """
        An asset created in an episode and also cast into it is in both
        halves of the union, and must come back once.
        """
        episode = self.generate_fixture_episode()
        created_in = self.asset
        created_in.update({"source_id": episode.id})
        breakdown_service.create_casting_link(episode.id, created_in.id)

        assets = assets_service.get_assets(
            criterions={"episode_id": str(episode.id)}
        )

        self.assertEqual(
            [asset["id"] for asset in assets], [str(created_in.id)]
        )

    def test_get_full_assets(self):
        """
        Ordered by production, then asset type, then asset name. Character
        sorts before Props, so the rabbit comes first whatever the order
        the rows were created in.
        """
        self.a_character()

        assets = assets_service.get_full_assets()

        self.assertEqual(
            [(asset["asset_type_name"], asset["name"]) for asset in assets],
            [("Character", "Rabbit"), ("Props", "Tree")],
        )
        self.assertEqual(assets[0]["project_name"], self.project.name)

    def test_get_assets_and_tasks(self):
        self.a_character()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_task()
        self.generate_fixture_task(name="Secondary")
        assets = assets_service.get_assets_and_tasks()

        # Ordered by asset type then name, so the rabbit leads. Sorting the
        # result here instead would hide the service losing that order.
        self.assertEqual(
            [asset["name"] for asset in assets], ["Rabbit", "Tree"]
        )
        tree_tasks = assets[1]["tasks"]
        self.assertEqual(len(tree_tasks), 2)
        self.assertEqual(tree_tasks[0]["assignees"][0], str(self.person.id))
        self.assertEqual(
            tree_tasks[0]["task_status_id"], str(self.task_status.id)
        )
        self.assertEqual(tree_tasks[0]["task_type_id"], str(self.task_type.id))

    def test_get_all_raw_assets(self):
        # The indexer walks every asset of the instance, productions included.
        assets = assets_service.get_all_raw_assets()
        self.assertEqual([asset.id for asset in assets], [self.asset.id])


class AssetTypeTestCase(AssetsTestCase):
    """
    Asset types are entity types minus the temporal ones. They belong to
    no production of their own: what a production holds is assets.
    """

    def test_get_asset_types(self):
        asset_types = assets_service.get_asset_types()
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
        asset_types = assets_service.get_asset_types({"name": "Character"})
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

        asset_types = assets_service.get_asset_types(
            {"project_id": str(self.project.id)}
        )

        self.assertEqual(
            sorted(asset_type["name"] for asset_type in asset_types),
            ["Character", "Props"],
        )

    def test_get_asset_types_for_project(self):
        asset_types = assets_service.get_asset_types_for_project(
            self.project.id
        )
        self.assertEqual(
            [asset_type["name"] for asset_type in asset_types], ["Props"]
        )

    def test_get_asset_types_for_shot(self):
        self.shot.entities_out = [self.asset]
        self.shot.save()
        asset_types = assets_service.get_asset_types_for_shot(self.shot.id)
        self.assertEqual(
            [asset_type["name"] for asset_type in asset_types], ["Props"]
        )

    def test_get_asset_types_for_episode(self):
        """
        The types of the assets an episode owns, which is source_id and not
        casting: an asset of another production cast into the episode does
        not count, and neither does one of this production filed under no
        episode at all.
        """
        self.generate_fixture_project_standard()
        self.generate_fixture_asset_types()
        self.generate_fixture_episode()
        episode_id = str(self.episode.id)
        own = self.generate_fixture_asset("Own")
        own.update({"source_id": episode_id})
        self.generate_fixture_asset(
            "Unfiled", asset_type_id=self.asset_type_character.id
        )
        elsewhere = self.generate_fixture_asset(
            "Elsewhere",
            asset_type_id=self.asset_type_environment.id,
            project_id=self.project_standard.id,
        )
        elsewhere.update({"source_id": episode_id})

        asset_types = assets_service.get_asset_types_for_episode(
            str(self.project.id), episode_id
        )

        self.assertEqual(
            [asset_type["name"] for asset_type in asset_types], ["Props"]
        )

    def test_get_asset_type(self):
        asset_type = assets_service.get_asset_type(self.asset_type.id)
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
            assets_service.get_asset_type,
            str(self.shot_type.id),
        )

    def test_get_asset_type_by_name(self):
        asset_type = assets_service.get_asset_type_by_name(
            self.asset_type.name
        )
        self.assertDictEqual(
            asset_type, self.asset_type.serialize(obj_type="AssetType")
        )

    def test_get_asset_type_by_name_of_a_temporal_type(self):
        self.assertRaises(
            AssetTypeNotFoundException,
            assets_service.get_asset_type_by_name,
            "Shot",
        )

    def test_get_or_create_asset_type(self):
        asset_type = assets_service.get_or_create_asset_type(
            self.asset_type.name
        )
        self.assertDictEqual(
            asset_type, self.asset_type.serialize(obj_type="AssetType")
        )
        asset_type = assets_service.get_or_create_asset_type("New asset type")
        self.assertEqual(asset_type["name"], "New asset type")

    def test_create_asset_types(self):
        assets_service.create_asset_types(["Type 01", "Type 02"])
        self.assertEqual(
            sorted(
                asset_type["name"]
                for asset_type in assets_service.get_asset_types()
            ),
            ["Props", "Type 01", "Type 02"],
        )

    def test_a_new_asset_type_shows_up_in_the_memoized_listing(self):
        """
        The criterionless listing is memoized, so creating a type has to
        drop it.
        """
        assets_service.get_asset_types()
        assets_service.get_or_create_asset_type("Vehicle")
        self.assertIn(
            "Vehicle",
            [
                asset_type["name"]
                for asset_type in assets_service.get_asset_types()
            ],
        )

    def test_is_asset_type(self):
        self.assertTrue(assets_service.is_asset_type(self.asset_type))
        self.assertFalse(assets_service.is_asset_type(self.shot_type))
        self.assertFalse(assets_service.is_asset_type(self.sequence_type))
        self.assertFalse(assets_service.is_asset_type(self.episode_type))

    def test_is_asset_type_of_a_serialized_type(self):
        """
        The importers hand over dicts rather than rows.
        """
        self.assertTrue(
            assets_service.is_asset_type(self.asset_type.serialize())
        )
        self.assertFalse(
            assets_service.is_asset_type(self.shot_type.serialize())
        )


class AssetReadTestCase(AssetsTestCase):
    """
    Reading one asset. Every one of these refuses a shot, since the two
    share a table and only the entity type tells them apart.
    """

    def test_get_asset(self):
        asset = assets_service.get_asset(self.asset.id)
        self.assertEqual(asset["id"], str(self.asset.id))

    def test_get_asset_of_a_shot(self):
        self.assertRaises(
            AssetNotFoundException,
            assets_service.get_asset,
            str(self.shot.id),
        )

    def test_get_asset_of_an_unparsable_id(self):
        """
        The id reaches the service straight from the path, so a value the
        driver cannot read as a uuid answers a 404 rather than a 500.
        """
        self.assertRaises(
            AssetNotFoundException, assets_service.get_asset, "not-an-id"
        )

    def test_get_asset_of_a_removed_asset(self):
        asset_id = str(self.asset.id)
        assets_service.get_asset(asset_id)
        assets_service.remove_asset(asset_id)
        self.assertRaises(
            AssetNotFoundException, assets_service.get_asset, asset_id
        )

    def test_get_full_asset(self):
        """
        The asset, plus what the asset page shows around it: the names of
        its production and type, and its tasks. The two entity columns that
        only mean something for a shot are dropped.
        """
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_task()

        asset = assets_service.get_full_asset(self.asset.id)

        self.assertEqual(asset["id"], str(self.asset.id))
        self.assertEqual(asset["project_name"], self.project.name)
        self.assertEqual(asset["asset_type_name"], self.asset_type.name)
        self.assertEqual(asset["asset_type_id"], str(self.asset_type.id))
        self.assertEqual(
            [task["id"] for task in asset["tasks"]], [str(self.task.id)]
        )
        self.assertNotIn("source_id", asset)
        self.assertNotIn("nb_frames", asset)

    def test_get_full_asset_of_a_shot(self):
        self.assertRaises(
            AssetNotFoundException,
            assets_service.get_full_asset,
            str(self.shot.id),
        )

    def test_get_asset_by_shotgun_id(self):
        self.shot.update({"shotgun_id": 1})
        self.asset.update({"shotgun_id": 1})
        asset = assets_service.get_asset_by_shotgun_id(1)
        self.assertEqual(asset["id"], str(self.asset.id))
        assets_service.remove_asset(asset["id"])
        self.assertRaises(
            AssetNotFoundException, assets_service.get_asset_by_shotgun_id, 1
        )

    def test_get_asset_instance(self):
        self.generate_fixture_scene()
        self.generate_fixture_scene_asset_instance()
        self.generate_fixture_shot_asset_instance(
            self.shot, self.asset_instance
        )
        asset_instance = assets_service.get_asset_instance(
            self.asset_instance.id
        )
        self.assertDictEqual(asset_instance, self.asset_instance.serialize())

    def test_is_asset(self):
        self.assertTrue(assets_service.is_asset(self.asset))
        self.assertFalse(assets_service.is_asset(self.shot))

    def test_is_asset_dict(self):
        self.assertTrue(assets_service.is_asset_dict(self.asset.serialize()))
        self.assertFalse(assets_service.is_asset_dict(self.shot.serialize()))


class AssetWriteTestCase(AssetsTestCase):
    """
    Creating, updating and taking an asset out of a production.
    """

    def test_create_asset(self):
        asset = assets_service.create_asset(
            self.project.id,
            self.asset_type.id,
            "New asset",
            "Description test",
            {},
        )
        self.assertDictEqual(asset, assets_service.get_asset(asset["id"]))

    def test_create_asset_in_an_episode(self):
        episode = self.generate_fixture_episode()
        asset = assets_service.create_asset(
            self.project.id,
            self.asset_type.id,
            "New asset",
            "",
            {},
            source_id=str(episode.id),
        )
        self.assertEqual(asset["source_id"], str(episode.id))

    def test_create_asset_with_a_source_that_is_not_an_id(self):
        """
        The episode arrives as a string from the client, and the empty
        marker the web client sends is not a uuid.
        """
        asset = assets_service.create_asset(
            self.project.id,
            self.asset_type.id,
            "New asset",
            "",
            {},
            source_id="",
        )
        self.assertIsNone(asset["source_id"])

    def test_update_asset(self):
        asset_id = str(self.asset.id)
        assets_service.get_asset(asset_id)
        asset = assets_service.update_asset(asset_id, {"name": "New name"})
        self.assertEqual(asset["name"], "New name")
        # Read back through the memoized path, which the update has to drop.
        self.assertEqual(
            assets_service.get_asset(asset_id)["name"], "New name"
        )

    def test_remove_asset(self):
        asset_id = self.asset.id
        assets_service.remove_asset(asset_id)
        self.assertRaises(
            AssetNotFoundException, assets_service.get_asset, asset_id
        )

    def test_remove_asset_carrying_tasks(self):
        """
        An asset someone has worked on is kept and marked canceled, so the
        history of those tasks survives. Only force really deletes it.
        """
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_task()
        asset_id = str(self.asset.id)
        assets_service.get_asset(asset_id)

        assets_service.remove_asset(asset_id)
        self.assertTrue(assets_service.get_asset(asset_id)["canceled"])

        assets_service.remove_asset(asset_id, force=True)
        self.assertRaises(
            AssetNotFoundException, assets_service.get_asset, asset_id
        )

    def test_remove_asset_reparents_its_children(self):
        child = Entity.create(
            name="Child",
            entity_type_id=self.asset_type.id,
            project_id=self.project.id,
            parent_id=self.asset.id,
        )
        assets_service.remove_asset(self.asset.id)
        self.assertIsNone(Entity.get(child.id).parent_id)

    def test_cancel_asset(self):
        asset_id = str(self.asset.id)
        # Read it once so the serialization is memoized: canceling writes
        # the same column as the canceling branch of remove_asset and drops
        # the same cache.
        assets_service.get_asset(asset_id)
        assets_service.cancel_asset(asset_id)
        self.assertTrue(assets_service.get_asset(asset_id)["canceled"])

    def test_add_asset_link(self):
        character = self.a_character()
        assets_service.add_asset_link(self.asset.id, character.id)
        asset = assets_service.get_asset(self.asset.id, relations=True)
        self.assertEqual(asset["entities_out"], [str(character.id)])

    def test_add_asset_link_twice(self):
        character = self.a_character()
        assets_service.add_asset_link(self.asset.id, character.id)
        assets_service.add_asset_link(self.asset.id, character.id)
        self.assertEqual(
            len(Entity.get(self.asset.id).entities_out),
            1,
        )

    def test_remove_asset_link(self):
        character = self.a_character()
        assets_service.add_asset_link(self.asset.id, character.id)
        assets_service.remove_asset_link(self.asset.id, character.id)
        self.assertEqual(Entity.get(self.asset.id).entities_out, [])


class SharedAssetTestCase(AssetsTestCase):
    """
    An asset of one production cast into the shots of another one.
    """

    def test_set_shared_assets_of_an_asset_type(self):
        character = self.a_character()
        assets_service.set_shared_assets(
            asset_type_id=self.asset_type_character.id
        )
        self.assertTrue(
            assets_service.get_asset(str(character.id))["is_shared"]
        )
        self.assertFalse(
            assets_service.get_asset(str(self.asset.id))["is_shared"]
        )

    def test_set_shared_assets_of_a_project(self):
        # generate_fixture_asset repoints self.asset on every named call.
        own_id = str(self.asset.id)
        self.generate_fixture_project_standard()
        elsewhere = self.generate_fixture_asset(
            "Elsewhere", project_id=self.project_standard.id
        )
        assets_service.set_shared_assets(project_id=self.project.id)
        self.assertTrue(assets_service.get_asset(own_id)["is_shared"])
        self.assertFalse(
            assets_service.get_asset(str(elsewhere.id))["is_shared"]
        )

    def test_unset_shared_assets_of_a_list(self):
        tree_id = str(self.asset.id)
        character = self.a_character()
        # The invalidation keys on the string id, as the routes pass it.
        character_id = str(character.id)
        assets_service.set_shared_assets(asset_ids=[character_id])
        self.assertTrue(assets_service.get_asset(character_id)["is_shared"])
        self.assertFalse(assets_service.get_asset(tree_id)["is_shared"])

        assets_service.set_shared_assets(
            is_shared=False, asset_ids=[character_id]
        )
        self.assertFalse(assets_service.get_asset(character_id)["is_shared"])

    def test_get_shared_assets_used_in_project(self):
        """
        Assets living in another production and cast into this one. An
        asset of the production itself is not shared into it however many
        shots use it, and neither is one of the other production that was
        never flagged as shared.
        """
        self.generate_fixture_project_standard()
        borrowed = self.generate_fixture_asset(
            "Borrowed", project_id=self.project_standard.id
        )
        borrowed.update({"is_shared": True})
        private = self.generate_fixture_asset(
            "Private", project_id=self.project_standard.id
        )
        own = self.generate_fixture_asset("Own")
        own.update({"is_shared": True})
        breakdown_service.update_casting(
            self.shot.id,
            [
                {"asset_id": str(borrowed.id), "nb_occurences": 1},
                {"asset_id": str(private.id), "nb_occurences": 1},
                {"asset_id": str(own.id), "nb_occurences": 1},
            ],
        )

        assets = assets_service.get_shared_assets_used_in_project(
            str(self.project.id)
        )

        self.assertEqual([asset["name"] for asset in assets], ["Borrowed"])

        # Read from the lending production, the shot belongs elsewhere.
        self.assertEqual(
            assets_service.get_shared_assets_used_in_project(
                str(self.project_standard.id)
            ),
            [],
        )

    def test_a_canceled_shared_asset_is_not_used_anymore(self):
        self.generate_fixture_project_standard()
        borrowed = self.generate_fixture_asset(
            "Borrowed", project_id=self.project_standard.id
        )
        borrowed.update({"is_shared": True, "canceled": True})
        breakdown_service.update_casting(
            self.shot.id,
            [{"asset_id": str(borrowed.id), "nb_occurences": 1}],
        )
        self.assertEqual(
            assets_service.get_shared_assets_used_in_project(
                str(self.project.id)
            ),
            [],
        )

    def test_get_shared_assets_used_in_one_episode(self):
        """
        The casting is read through the shot, so the episode is the one of
        the sequence the shot hangs under.
        """
        self.generate_fixture_project_standard()
        borrowed = self.generate_fixture_asset(
            "Borrowed", project_id=self.project_standard.id
        )
        borrowed.update({"is_shared": True})
        breakdown_service.update_casting(
            self.shot.id,
            [{"asset_id": str(borrowed.id), "nb_occurences": 1}],
        )
        episode = self.generate_fixture_episode()
        other_episode = self.generate_fixture_episode("E02")
        Entity.get(self.shot.parent_id).update({"parent_id": episode.id})

        self.assertEqual(
            [
                asset["name"]
                for asset in assets_service.get_shared_assets_used_in_project(
                    str(self.project.id), episode_id=str(episode.id)
                )
            ],
            ["Borrowed"],
        )
        self.assertEqual(
            assets_service.get_shared_assets_used_in_project(
                str(self.project.id), episode_id=str(other_episode.id)
            ),
            [],
        )
