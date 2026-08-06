from tests.base import ApiDBTestCase

from zou.app.services import assets_service, breakdown_service
from zou.app.services.exception import AssetNotFoundException


class AssetServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

    def test_get_assets(self):
        assets = assets_service.get_assets()
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["name"], "Tree")

    def test_get_assets_with_episode_and_project_filters(self):
        self.generate_fixture_episode()
        assets = assets_service.get_assets(
            criterions={
                "episode_id": str(self.episode.id),
                "project_id": str(self.project.id),
            }
        )
        self.assertIsInstance(assets, list)

    def test_get_full_assets(self):
        """
        Ordered by production, then asset type, then asset name. Character
        sorts before Props, so the rabbit comes first whatever the order
        the rows were created in.
        """
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()

        assets = assets_service.get_full_assets()

        self.assertEqual(
            [(asset["asset_type_name"], asset["name"]) for asset in assets],
            [("Character", "Rabbit"), ("Props", "Tree")],
        )
        self.assertEqual(assets[0]["project_name"], self.project.name)

    def test_get_assets_and_tasks(self):
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()
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

    def test_get_asset_types(self):
        asset_types = assets_service.get_asset_types()
        self.assertEqual(len(asset_types), 1)
        self.assertEqual(asset_types[0]["name"], "Props")

    def test_get_asset_types_for_project(self):
        asset_types = assets_service.get_asset_types_for_project(
            self.project.id
        )
        self.assertEqual(len(asset_types), 1)
        self.assertEqual(asset_types[0]["name"], "Props")

    def test_get_asset_types_for_shot(self):
        self.shot.entities_out = [self.asset]
        self.shot.save()
        asset_types = assets_service.get_asset_types_for_shot(self.shot.id)
        self.assertEqual(len(asset_types), 1)
        self.assertEqual(asset_types[0]["name"], "Props")

    def test_get_asset(self):
        asset = assets_service.get_asset(self.asset.id)
        self.assertEqual(asset["id"], str(self.asset.id))

        assets_service.remove_asset(asset["id"])
        self.assertRaises(
            AssetNotFoundException,
            assets_service.get_asset,
            str(self.asset.id),
        )

    def test_get_asset_full(self):
        asset = assets_service.get_full_asset(self.asset.id)
        self.assertEqual(asset["id"], str(self.asset.id))
        self.assertEqual(asset["project_name"], str(self.project.name))

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

    def test_get_asset_type(self):
        asset_type = assets_service.get_asset_type(self.asset_type.id)
        self.assertDictEqual(
            asset_type,
            self.asset_type.serialize(obj_type="AssetType", relations=True),
        )

    def test_get_asset_type_by_name(self):
        asset_type = assets_service.get_asset_type_by_name(
            self.asset_type.name
        )
        self.assertDictEqual(
            asset_type, self.asset_type.serialize(obj_type="AssetType")
        )

    def test_get_or_create_asset_type(self):
        new_name = "New asset type"
        asset_type = assets_service.get_or_create_asset_type(
            self.asset_type.name
        )
        self.assertDictEqual(
            asset_type, self.asset_type.serialize(obj_type="AssetType")
        )
        asset_type = assets_service.get_or_create_asset_type("New asset type")
        self.assertEqual(asset_type["name"], new_name)

    def test_is_asset(self):
        self.assertTrue(assets_service.is_asset(self.asset))
        self.assertFalse(assets_service.is_asset(self.shot))

    def test_is_asset_type(self):
        self.assertTrue(assets_service.is_asset_type(self.asset_type))
        self.assertFalse(assets_service.is_asset_type(self.shot_type))
        self.assertFalse(assets_service.is_asset_type(self.sequence_type))
        self.assertFalse(assets_service.is_asset_type(self.episode_type))

    def test_create_asset_types(self):
        asset_type_names = ["Type 01", "Type 02", "Type 03"]
        assets_service.create_asset_types(asset_type_names)
        asset_type = assets_service.get_asset_type_by_name(asset_type_names[0])
        self.assertIsNotNone(asset_type)
        asset_type = assets_service.get_asset_type_by_name(asset_type_names[1])
        self.assertIsNotNone(asset_type)
        asset_type = assets_service.get_asset_type_by_name(asset_type_names[2])
        self.assertIsNotNone(asset_type)

    def test_create_asset(self):
        asset = assets_service.create_asset(
            self.project.id,
            self.asset_type.id,
            "New asset",
            "Description test",
            {},
        )
        asset_again = assets_service.get_asset(asset["id"])
        self.assertDictEqual(asset, asset_again)

    def test_update_asset(self):
        asset = self.asset.serialize(obj_type="Asset")
        asset = assets_service.update_asset(asset["id"], {"name": "New name"})
        asset_again = assets_service.get_asset(asset["id"])
        self.assertDictEqual(asset, asset_again)

    def test_remove_asset(self):
        asset_id = self.asset.id
        assets_service.remove_asset(asset_id)
        self.assertRaises(
            AssetNotFoundException, assets_service.get_asset, asset_id
        )

    def test_cancel_asset(self):
        asset_id = self.asset.id
        assets_service.cancel_asset(asset_id)
        asset = assets_service.get_asset(asset_id)
        self.assertTrue(asset["canceled"])

    def test_get_all_raw_assets(self):
        # The indexer walks every asset of the instance, productions included.
        assets = assets_service.get_all_raw_assets()
        self.assertEqual([asset.id for asset in assets], [self.asset.id])

    def test_set_shared_assets(self):
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()
        # The invalidation keys on the string id, as the routes pass it.
        character_id = str(self.asset_character.id)

        assets_service.set_shared_assets(
            asset_type_id=self.asset_type_character.id
        )
        self.assertTrue(assets_service.get_asset(character_id)["is_shared"])
        self.assertFalse(
            assets_service.get_asset(str(self.asset.id))["is_shared"]
        )

        assets_service.set_shared_assets(
            is_shared=False, asset_ids=[character_id]
        )
        self.assertFalse(assets_service.get_asset(character_id)["is_shared"])

    def test_add_asset_link(self):
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()
        assets_service.add_asset_link(self.asset.id, self.asset_character.id)
        asset = assets_service.get_asset(
            self.asset.id,
            relations=True,
        )
        self.assertEqual(
            asset["entities_out"][0], str(self.asset_character.id)
        )

    def test_remove_asset_link(self):
        self.generate_fixture_asset_types()
        self.generate_fixture_asset_character()
        assets_service.add_asset_link(self.asset.id, self.asset_character.id)
        assets_service.remove_asset_link(
            self.asset.id, self.asset_character.id
        )
        asset = assets_service.get_asset(
            self.asset.id,
            relations=True,
        )
        self.assertEqual(asset["entities_out"], [])

    def test_get_shared_assets_used_in_project(self):
        """
        Assets living in another production and cast into this one. An
        asset of the production itself is not shared into it, however many
        shots use it.
        """
        self.generate_fixture_project_standard()
        borrowed = self.generate_fixture_asset(
            "Borrowed", project_id=self.project_standard.id
        )
        borrowed.update({"is_shared": True})
        own = self.generate_fixture_asset("Own")
        own.update({"is_shared": True})
        breakdown_service.update_casting(
            self.shot.id,
            [
                {"asset_id": str(borrowed.id), "nb_occurences": 1},
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

    def test_get_asset_types_for_episode(self):
        """
        The types of the assets an episode owns, which is source_id and not
        casting: an asset of another production cast into the episode does
        not count, and neither does one of this production filed under
        another episode.
        """
        self.generate_fixture_project_standard()
        self.generate_fixture_asset_types()
        self.generate_fixture_episode()
        episode_id = str(self.episode.id)
        own = self.generate_fixture_asset("Own")
        own.update({"source_id": episode_id})
        elsewhere = self.generate_fixture_asset(
            "Elsewhere",
            asset_type_id=self.asset_type_character.id,
            project_id=self.project_standard.id,
        )
        elsewhere.update({"source_id": episode_id})

        asset_types = assets_service.get_asset_types_for_episode(
            str(self.project.id), episode_id
        )

        self.assertEqual(
            [asset_type["name"] for asset_type in asset_types], ["Props"]
        )
