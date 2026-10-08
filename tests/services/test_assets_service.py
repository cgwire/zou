from zou.app.models.entity import Entity
from zou.app.services import (
    assets_service,
    breakdown_service,
    entity_types_service,
    cascade_deletion_service,
)
from zou.app.exceptions import (
    AssetNotFoundException,
)
from tests.services.cases import AssetsTestCase


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


class AssetTypeTestCase(AssetsTestCase):
    """
    Asset types are entity types minus the temporal ones. They belong to
    no production of their own: what a production holds is assets.
    """

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

    def test_create_asset_types(self):
        assets_service.create_asset_types(["Type 01", "Type 02"])
        self.assertEqual(
            sorted(
                asset_type["name"]
                for asset_type in entity_types_service.get_asset_types()
            ),
            ["Props", "Type 01", "Type 02"],
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
        cascade_deletion_service.remove_asset(asset_id)
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
        cascade_deletion_service.remove_asset(asset["id"])
        self.assertRaises(
            AssetNotFoundException, assets_service.get_asset_by_shotgun_id, 1
        )


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
