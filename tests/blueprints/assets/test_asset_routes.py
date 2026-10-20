from tests.base import ApiDBTestCase
from zou.app.models.entity import EntityLink
from zou.app.models.person import Person
from zou.app.services import (
    breakdown_service,
    projects_service,
    tasks_service,
)


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
        """
        Each new instance takes the number after the highest one already
        there. Three of them, because with a single instance around any of
        them is the highest and the ordering that finds it never shows.
        """
        path = f"/data/assets/{self.asset_id}/asset-asset-instances"
        character_id = str(self.asset_character.id)
        created = [
            self.post(
                path,
                {
                    "asset_to_instantiate_id": character_id,
                    "description": "Instance in asset",
                },
            )
            for _ in range(3)
        ]

        self.assertEqual([held["number"] for held in created], [1, 2, 3])
        instances = self.get(path)
        self.assertEqual(
            [held["number"] for held in instances[character_id]], [1, 2, 3]
        )

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

    def generate_assets_to_page_through(self):
        """
        Two props, two assets in the episode (one belonging to it and cast
        in it, listed once), and two shared assets of another production,
        each cast in two shots of this one.
        """
        tree, rabbit = self.asset, self.asset_character
        self.generate_fixture_asset("Bush")
        episode = self.generate_fixture_episode()
        tree.update({"source_id": episode.id})
        for asset in [tree, rabbit]:
            EntityLink.create(entity_in_id=episode.id, entity_out_id=asset.id)
        rock = self.share_an_asset_of_another_production_in_this_shot()
        pebble = self.asset
        pebble.update({"is_shared": True})
        other_shot = self.generate_fixture_shot("P02")
        for asset in [rock, pebble]:
            breakdown_service.create_casting_link(other_shot.id, asset.id)
        self.sequence.update({"parent_id": episode.id})
        return episode

    def test_asset_listings_paginate_on_demand(self):
        episode = self.generate_assets_to_page_through()
        project_path = f"/data/projects/{self.project_id}"
        for path in [
            "/data/assets",
            "/data/assets/all",
            f"/data/assets?episode_id={episode.id}",
            f"{project_path}/assets",
            f"{project_path}/assets?episode_id={episode.id}",
            f"{project_path}/asset-types/{self.asset_type.id}/assets",
            f"{project_path}/assets/shared-used",
            f"{project_path}/episodes/{episode.id}/assets/shared-used",
        ]:
            with self.subTest(path=path):
                self.assert_opt_in_pagination(path)

    def test_a_vendor_page_matches_their_full_list(self):
        """
        A vendor holding two tasks on the same asset gets it once per
        page, and the pages walk the very list they get without them.
        """
        episode = self.generate_assets_to_page_through()
        vendor_id = self.generate_fixture_user_vendor()["id"]
        projects_service.add_team_member(self.project_id, vendor_id)
        second_task = self.generate_fixture_task(
            name="Second", entity_id=self.asset_id
        )
        for task in [self.task, second_task]:
            tasks_service.assign_task(task.id, vendor_id)
        self.log_in_vendor()
        project_path = f"/data/projects/{self.project_id}"
        for path in [
            f"{project_path}/assets",
            f"{project_path}/assets?episode_id={episode.id}",
        ]:
            with self.subTest(path=path):
                self.assert_opt_in_pagination(path)

        # The character is cast in the episode but the vendor holds no
        # task on it: it stays out of their list, paged or not.
        path = f"{project_path}/assets?episode_id={episode.id}"
        self.assertEqual(
            [asset["id"] for asset in self.get(path)], [self.asset_id]
        )
        self.assertEqual(self.get(f"{path}&page=1&limit=10")["total"], 1)
