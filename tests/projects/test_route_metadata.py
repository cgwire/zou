from tests.base import ApiDBTestCase

from zou.app.services import projects_service


class ProjectMetadataRouteTestCase(ApiDBTestCase):
    def setUp(self):
        super(ProjectMetadataRouteTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project_closed_status()
        self.generate_fixture_project()
        self.generate_fixture_project_closed()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.project_id = self.project.id
        self.asset_id = self.asset.id

    def test_add_asset_metadata_descriptor(self):
        descriptor = self.post(
            "data/projects/%s/metadata-descriptors" % self.project_id,
            {
                "entity_type": "Asset",
                "name": "environment type",
                "data_type": "list",
                "choices": ["indoor", "outdoor"],
            },
        )
        descriptor = self.get(
            "data/projects/%s/metadata-descriptors/%s"
            % (self.project_id, descriptor["id"])
        )
        descriptor = self.post(
            "data/projects/%s/metadata-descriptors" % self.project_id,
            {
                "entity_type": "Shot",
                "name": "Contractor",
                "data_type": "list",
                "choices": ["studio1", "studio2"],
            },
        )
        descriptors = self.get(
            "data/projects/%s/metadata-descriptors" % self.project_id,
        )
        self.assertEqual(len(descriptors), 2)
        self.assertEqual(descriptors[0]["id"], descriptor["id"])
        self.assertEqual(descriptors[0]["data_type"], "list")
        self.assertEqual(descriptors[0]["field_name"], "contractor")
        self.assertEqual(descriptors[1]["field_name"], "environment_type")
        self.assertEqual(descriptors[1]["choices"], ["indoor", "outdoor"])
        self.assertEqual(descriptors[1]["data_type"], "list")

        projects = self.get("data/projects/open/")
        self.assertEqual(len(projects), 1)
        self.assertEqual(len(projects[0]["descriptors"]), 2)

    def test_unallowed_add_asset_metadata_descriptor(self):
        self.generate_fixture_user_manager()
        self.log_in_manager()
        self.post(
            "data/projects/%s/metadata-descriptors" % self.project_id,
            {
                "entity_type": "Asset",
                "name": "environment type",
                "data_type": "list",
                "choices": ["indoor", "outdoor"],
            },
            403,
        )

    def test_update_metadata_descriptor(self):
        descriptor = self.post(
            "data/projects/%s/metadata-descriptors" % self.project_id,
            {
                "entity_type": "Asset",
                "name": "Contractor",
                "data_type": "list",
                "choices": ["contractor 1", "contractor 2"],
            },
        )
        self.asset.update({"data": {"contractor": "contractor 1"}})
        asset = self.get("data/assets/%s" % self.asset_id)
        self.put(
            "data/projects/%s/metadata-descriptors/%s"
            % (self.project_id, descriptor["id"]),
            {"name": "Team", "data_type": "list"},
        )
        descriptors = self.get(
            "data/projects/%s/metadata-descriptors" % self.project_id
        )
        self.assertEqual(len(descriptors), 1)
        asset = self.get("data/entities/%s" % self.asset_id)
        self.assertEqual(asset["data"].get("team"), "contractor 1")

    def test_unallowed_update_metadata_descriptor(self):
        descriptor = projects_service.add_metadata_descriptor(
            self.project_id, "Asset", "Contractor", "string", [], False
        )
        self.generate_fixture_user_manager()
        self.log_in_manager()
        self.put(
            "data/projects/%s/metadata-descriptors/%s"
            % (self.project_id, descriptor["id"]),
            {"name": "Team", "data_type": "list"},
            403,
        )

    def test_delete_metadata_descriptor(self):
        descriptor = projects_service.add_metadata_descriptor(
            self.project_id, "Asset", "Contractor", "string", [], False
        )
        self.asset.update({"data": {"contractor": "contractor 1"}})
        self.delete(
            "data/projects/%s/metadata-descriptors/%s"
            % (self.project_id, descriptor["id"])
        )
        descriptors = self.get(
            "data/projects/%s/metadata-descriptors" % self.project_id
        )
        self.assertEqual(len(descriptors), 0)
        asset = self.get("data/assets/%s" % self.asset_id)
        self.assertFalse("contractor" in asset["data"])

    def test_unallowed_delete_metadata_descriptor(self):
        descriptor = projects_service.add_metadata_descriptor(
            self.project_id, "Asset", "Contractor", "string", [], False
        )
        self.generate_fixture_user_manager()
        self.log_in_manager()
        self.delete(
            "data/projects/%s/metadata-descriptors/%s"
            % (self.project_id, descriptor["id"]),
            403,
        )
