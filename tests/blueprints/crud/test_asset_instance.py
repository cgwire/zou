from tests.base import ApiDBTestCase

from zou.app.services import projects_service


class AssetInstanceTestCase(ApiDBTestCase):
    """
    The generic crud routes over asset instances. Unlike most of the crud
    resources they do not settle for the admin only default: an instance is
    readable by whoever may reach the asset it stands for.
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
        self.generate_fixture_scene()
        self.asset_instance = (
            self.generate_fixture_scene_asset_instance().serialize()
        )

    def test_get_asset_instances(self):
        instances = self.get("data/asset-instances")
        self.assertEqual(len(instances), 1)
        self.assertEqual(instances[0]["id"], self.asset_instance["id"])

    def test_get_asset_instance(self):
        instance = self.get(
            f"data/asset-instances/{self.asset_instance['id']}"
        )
        self.assertEqual(instance["asset_id"], str(self.asset.id))

    def test_number_is_protected(self):
        """
        The number is what the instance name is built from, so a put must
        not move it out from under the name.
        """
        self.put(
            f"data/asset-instances/{self.asset_instance['id']}",
            {"number": 42, "description": "Second thought"},
        )
        instance = self.get(
            f"data/asset-instances/{self.asset_instance['id']}"
        )
        self.assertEqual(instance["number"], self.asset_instance["number"])
        self.assertEqual(instance["description"], "Second thought")

    def test_reading_one_needs_access_to_its_asset(self):
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        path = f"data/asset-instances/{self.asset_instance['id']}"

        self.get(path, 403)

        # Through the service, so the caches the guard reads are dropped.
        projects_service.add_team_member(
            str(self.project.id), self.user_cg_artist["id"]
        )

        self.assertEqual(self.get(path)["id"], str(self.asset_instance["id"]))
