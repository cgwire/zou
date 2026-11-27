from tests.base import ApiDBTestCase
from zou.app.services import projects_service


class BreakdownRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
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

    def _set_shot_casting(self):
        new_casting = [
            {"asset_id": self.asset_id, "nb_occurences": 1},
            {"asset_id": self.asset_character_id, "nb_occurences": 2},
        ]
        self.put(
            f"/data/projects/{self.project_id}"
            f"/entities/{self.shot_id}/casting",
            new_casting,
        )

    def test_update_asset_casting_refuses_a_malformed_body(self):
        path = f"/data/assets/{self.asset_id}/casting"
        self.put(path, {"asset_id": self.asset_character_id}, 400)
        self.put(path, [{"asset_id": "not-a-uuid", "nb_occurences": 1}], 400)
        self.put(
            path,
            [{"asset_id": self.asset_character_id, "nb_occurences": "x"}],
            400,
        )

    def test_get_asset_type_casting(self):
        self.put(
            f"/data/projects/{self.project_id}"
            f"/entities/{self.asset_character_id}/casting",
            [{"asset_id": self.asset_id, "nb_occurences": 1}],
        )
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/asset-types/{self.asset_type_character.id}/casting"
        )
        self.assertIsInstance(result, dict)
        self.assertIn(self.asset_character_id, result)

    def test_update_entities_casting(self):
        castings = {
            self.shot_id: [{"asset_id": self.asset_id, "nb_occurences": 1}],
            self.asset_character_id: [
                {"asset_id": self.asset_id, "nb_occurences": 2}
            ],
        }
        result = self.put(
            f"/data/projects/{self.project_id}/entities/casting",
            castings,
            200,
        )
        self.assertEqual(set(result.keys()), set(castings.keys()))
        shot_casting = self.get(
            f"/data/projects/{self.project_id}"
            f"/entities/{self.shot_id}/casting"
        )
        self.assertEqual(shot_casting[0]["asset_id"], self.asset_id)
        character_casting = self.get(
            f"/data/projects/{self.project_id}"
            f"/entities/{self.asset_character_id}/casting"
        )
        self.assertEqual(character_casting[0]["nb_occurences"], 2)

    def test_update_entities_casting_rejects_non_object_body(self):
        self.put(
            f"/data/projects/{self.project_id}/entities/casting",
            [{"asset_id": self.asset_id, "nb_occurences": 1}],
            400,
        )

    def test_update_entities_casting_as_artist_is_forbidden(self):
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.put(
            f"/data/projects/{self.project_id}/entities/casting",
            {self.shot_id: [{"asset_id": self.asset_id, "nb_occurences": 1}]},
            403,
        )

    def test_cast_asset_in_entities(self):
        self._set_shot_casting()
        result = self.put(
            f"/data/projects/{self.project_id}"
            f"/entities/casting/assets/{self.asset_character_id}",
            {
                "entity_ids": [self.shot_id, self.asset_id],
                "nb_occurences": 3,
                "label": "fixed",
            },
        )
        self.assertEqual(set(result.keys()), {self.shot_id, self.asset_id})
        shot_casting = self.get(
            f"/data/projects/{self.project_id}"
            f"/entities/{self.shot_id}/casting"
        )
        self.assertEqual(
            {(c["asset_id"], c["nb_occurences"]) for c in shot_casting},
            {(self.asset_id, 1), (self.asset_character_id, 3)},
        )
        asset_casting = self.get(
            f"/data/projects/{self.project_id}"
            f"/entities/{self.asset_id}/casting"
        )
        self.assertEqual(asset_casting[0]["label"], "fixed")

    def test_cast_asset_in_entities_rejects_an_empty_selection(self):
        self.put(
            f"/data/projects/{self.project_id}"
            f"/entities/casting/assets/{self.asset_id}",
            {"entity_ids": []},
            400,
        )

    def test_cast_asset_in_entities_as_artist_is_forbidden(self):
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.put(
            f"/data/projects/{self.project_id}"
            f"/entities/casting/assets/{self.asset_id}",
            {"entity_ids": [self.shot_id]},
            403,
        )

    def test_get_episodes_casting(self):
        self._set_shot_casting()
        result = self.get(f"/data/projects/{self.project_id}/episodes/casting")
        # The shot casting is mirrored on the episode of the shot.
        self.assertIn(self.episode_id, result)

    def test_get_sequence_casting(self):
        self._set_shot_casting()
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/sequences/{self.sequence_id}/casting"
        )
        self.assertIsInstance(result, dict)
        self.assertIn(self.shot_id, result)

    def test_get_episode_sequences_all_casting(self):
        self._set_shot_casting()
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/episodes/{self.episode_id}/sequences/all/casting"
        )
        self.assertEqual(list(result), [self.shot_id])

    def test_get_sequences_all_casting(self):
        self._set_shot_casting()
        result = self.get(
            f"/data/projects/{self.project_id}/sequences/all/casting"
        )
        self.assertEqual(list(result), [self.shot_id])

    def test_delete_entity_link(self):
        self._set_shot_casting()
        links = self.get(
            f"/data/projects/{self.project_id}/entity-links?limit=100"
        )
        link = next(
            link
            for link in links
            if link["entity_in_id"] == self.shot_id
            and link["entity_out_id"] == self.asset_id
        )
        self.delete(
            f"/data/projects/{self.project_id}/entity-links/{link['id']}",
            200,
        )
        links_after = self.get(
            f"/data/projects/{self.project_id}/entity-links?limit=100"
        )
        # The asset left the only shot casting it, so the episode link
        # mirrored from that shot goes with it.
        self.assertNotIn(
            self.asset_id,
            [link["entity_out_id"] for link in links_after],
        )
        self.assertIn(
            self.asset_character_id,
            [link["entity_out_id"] for link in links_after],
        )

    def test_get_scene_asset_instances(self):
        """
        The instances of a scene, grouped by the asset they instantiate.
        Cameras are assets too, and they come back here as well: the camera
        listing is the narrowed one, not this.
        """
        self.generate_fixture_asset_camera()
        for asset in [self.asset, self.asset_camera]:
            self.post(
                f"/data/scenes/{self.scene_id}/asset-instances",
                {"asset_id": str(asset.id)},
            )

        result = self.get(f"/data/scenes/{self.scene_id}/asset-instances")

        self.assertEqual(
            sorted(result.keys()),
            sorted([self.asset_id, str(self.asset_camera.id)]),
        )
        self.assertEqual(len(result[self.asset_id]), 1)

    def test_an_instance_of_another_project_is_not_added_to_a_shot(self):
        other_project = self.generate_fixture_project_standard()
        scene = self.generate_fixture_scene(
            "SC02", project_id=other_project.id
        )
        instance = self.generate_fixture_scene_asset_instance(scene=scene)

        self.post(
            f"/data/shots/{self.shot_id}/asset-instances",
            {"asset_instance_id": str(instance.id)},
            400,
        )
        self.assertEqual(
            self.get(f"/data/shots/{self.shot_id}/asset-instances"), {}
        )

    def test_remove_an_instance_not_cast_in_the_shot(self):
        self.generate_fixture_scene_asset_instance()
        self.delete(
            f"/data/shots/{self.shot_id}/asset-instances"
            f"/{self.asset_instance.id}",
            400,
        )

    def test_a_client_edits_no_asset_instance(self):
        self.generate_fixture_scene_asset_instance()
        self.generate_fixture_user_client()
        projects_service.add_team_member(
            self.project_id, self.user_client["id"]
        )
        self.log_in_client()
        shot_instances = f"/data/shots/{self.shot_id}/asset-instances"
        self.post(
            shot_instances,
            {"asset_instance_id": str(self.asset_instance.id)},
            403,
        )
        self.delete(f"{shot_instances}/{self.asset_instance.id}", 403)
        self.post(
            f"/data/scenes/{self.scene_id}/asset-instances",
            {"asset_id": self.asset_id},
            403,
        )
        self.post(
            f"/data/assets/{self.asset_id}/asset-asset-instances",
            {"asset_to_instantiate_id": self.asset_character_id},
            403,
        )
