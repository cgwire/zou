from tests.base import ApiDBTestCase

from zou.app.models.person import Person

from zou.app.services import breakdown_service


class AssetRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_asset_character()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()
        self.generate_fixture_task()
        self.project_id = str(self.project.id)
        self.asset_id = str(self.asset.id)
        self.shot_id = str(self.shot.id)

    def _set_casting(self):
        self.put(
            f"/data/projects/{self.project_id}"
            f"/entities/{self.shot_id}/casting",
            [{"asset_id": self.asset_id, "nb_occurences": 1}],
        )

    def cast_the_character_in_the_asset(self):
        self.put(
            f"/data/assets/{self.asset_id}/casting",
            [{"asset_id": str(self.asset_character.id), "nb_occurences": 2}],
        )

    def test_get_asset_casting(self):
        self.cast_the_character_in_the_asset()

        result = self.get(f"/data/assets/{self.asset_id}/casting")

        self.assertEqual(
            [(cast["asset_id"], cast["nb_occurences"]) for cast in result],
            [(str(self.asset_character.id), 2)],
        )

    def test_update_asset_casting(self):
        result = self.put(
            f"/data/assets/{self.asset_id}/casting",
            [
                {
                    "asset_id": str(self.asset_character.id),
                    "nb_occurences": 2,
                }
            ],
        )
        self.assertIsInstance(result, list)
        casting = self.get(f"/data/assets/{self.asset_id}/casting")
        asset_ids = [c["asset_id"] for c in casting]
        self.assertIn(str(self.asset_character.id), asset_ids)

    def test_get_asset_cast_in(self):
        self._set_casting()
        result = self.get(f"/data/assets/{self.asset_id}/cast-in")
        self.assertIsInstance(result, list)
        self.assertGreater(len(result), 0)

    def test_get_asset_shot_asset_instances(self):
        self.generate_fixture_scene_asset_instance()
        self.generate_fixture_shot_asset_instance(
            self.shot, self.asset_instance
        )
        result = self.get(f"/data/assets/{self.asset_id}/shot-asset-instances")
        self.assertIn(self.shot_id, result)
        instances = result[self.shot_id]
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]["asset_id"], self.asset_id)

    def test_get_asset_scene_asset_instances(self):
        self.generate_fixture_scene_asset_instance()
        scene_id = str(self.scene.id)
        result = self.get(
            f"/data/assets/{self.asset_id}/scene-asset-instances"
        )
        self.assertIn(scene_id, result)
        instances = result[scene_id]
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]["asset_id"], self.asset_id)

    def test_get_asset_asset_instances(self):
        self.generate_fixture_asset_asset_instance(
            asset=self.asset_character, target_asset=self.asset
        )
        character_id = str(self.asset_character.id)
        result = self.get(
            f"/data/assets/{self.asset_id}/asset-asset-instances"
        )
        self.assertIn(character_id, result)
        instances = result[character_id]
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]["asset_id"], character_id)

    def test_create_asset_asset_instance(self):
        result = self.post(
            f"/data/assets/{self.asset_id}/asset-asset-instances",
            {
                "asset_to_instantiate_id": str(self.asset_character.id),
                "description": "Instance in asset",
            },
        )
        self.assertIsNotNone(result.get("id"))
        instances = self.get(
            f"/data/assets/{self.asset_id}/asset-asset-instances"
        )
        self.assertEqual(len(instances), 1)

    def test_get_asset_assets(self):
        self.cast_the_character_in_the_asset()

        result = self.get(f"/data/assets/{self.asset_id}/assets")

        self.assertEqual(
            [asset["id"] for asset in result], [str(self.asset_character.id)]
        )

    def test_share_assets(self):
        result = self.post(
            "/actions/assets/share",
            {
                "asset_ids": [self.asset_id],
                "is_shared": True,
            },
            200,
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["is_shared"])
        asset = self.get(f"/data/assets/{self.asset_id}")
        self.assertTrue(asset["is_shared"])

    def test_share_project_assets(self):
        result = self.post(
            f"/actions/projects/{self.project_id}/assets/share",
            {"is_shared": True},
            200,
        )
        self.assertGreater(len(result), 0)
        self.assertTrue(all(a["is_shared"] for a in result))
        asset = self.get(f"/data/assets/{self.asset_id}")
        self.assertTrue(asset["is_shared"])

    def test_share_project_asset_type_assets(self):
        result = self.post(
            f"/actions/projects/{self.project_id}"
            f"/asset-types/{self.asset_type.id}/assets/share",
            {"is_shared": True},
            200,
        )
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0]["is_shared"])
        asset = self.get(f"/data/assets/{self.asset_id}")
        self.assertTrue(asset["is_shared"])

    def share_an_asset_of_another_production_in_this_shot(self):
        """
        The listing is about assets owned elsewhere: one marked shared in
        another production and cast in a shot of this one. An asset of this
        production, shared or not, must stay out.
        """
        # generate_fixture_asset repoints self.asset, so hold on to this
        # production's own asset before making the other one.
        here = self.asset
        self.generate_fixture_project_standard()
        elsewhere = self.generate_fixture_asset(
            "Rock", project_id=self.project_standard.id
        )
        unshared = self.generate_fixture_asset(
            "Pebble", project_id=self.project_standard.id
        )
        elsewhere.update({"is_shared": True})
        here.update({"is_shared": True})
        for asset in [elsewhere, here, unshared]:
            breakdown_service.create_casting_link(self.shot.id, asset.id)
        return elsewhere

    def test_get_project_shared_used_assets(self):
        elsewhere = self.share_an_asset_of_another_production_in_this_shot()

        result = self.get(
            f"/data/projects/{self.project_id}/assets/shared-used"
        )

        self.assertEqual(
            [asset["id"] for asset in result], [str(elsewhere.id)]
        )

    def test_get_project_episode_shared_used_assets(self):
        elsewhere = self.share_an_asset_of_another_production_in_this_shot()
        self.generate_fixture_episode()
        self.sequence.update({"parent_id": self.episode.id})

        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/episodes/{self.episode.id}/assets/shared-used"
        )

        self.assertEqual(
            [asset["id"] for asset in result], [str(elsewhere.id)]
        )

    def test_list_routes_scope_to_user_projects(self):
        list_paths = ["data/assets/all", "data/assets/with-tasks"]
        self.generate_fixture_project_standard()
        self.generate_fixture_asset(
            name="Elsewhere", project_id=self.project_standard.id
        )
        self.generate_fixture_user_cg_artist()

        for path in list_paths:
            names = {asset["name"] for asset in self.get(path)}
            self.assertEqual(names, {"Tree", "Rabbit", "Elsewhere"})

        self.log_in_cg_artist()
        for path in list_paths:
            self.assertEqual(self.get(path), [])

        self.project.team.append(Person.get(self.user_cg_artist["id"]))
        self.project.save()
        self.log_in_cg_artist()
        for path in list_paths:
            names = {asset["name"] for asset in self.get(path)}
            self.assertEqual(names, {"Tree", "Rabbit"})
