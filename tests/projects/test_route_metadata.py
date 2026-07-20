from tests.base import ApiDBTestCase

from zou.app.services import projects_service
from zou.app.utils import fields


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

    def test_add_project_metadata_descriptor(self):
        descriptor = self.post(
            f"data/projects/{self.project_id}/metadata-descriptors",
            {
                "entity_type": "Project",
                "name": "Delivery code",
                "data_type": "string",
            },
        )
        self.assertEqual(descriptor["entity_type"], "Project")
        self.assertEqual(descriptor["field_name"], "delivery_code")
        self.put(
            f"data/projects/{self.project_id}",
            {"data": {"delivery_code": "X-12"}},
        )
        self.put(
            f"data/projects/{self.project_id}/metadata-descriptors/{descriptor['id']}",
            {"name": "Ship code", "data_type": "string"},
        )
        project = self.get(f"data/projects/{self.project_id}")
        self.assertEqual(project["data"].get("ship_code"), "X-12")
        self.assertIsNone((project.get("data") or {}).get("delivery_code"))
        self.delete(
            f"data/projects/{self.project_id}/metadata-descriptors/{descriptor['id']}"
        )
        project = self.get(f"data/projects/{self.project_id}")
        self.assertIsNone((project.get("data") or {}).get("ship_code"))

    def test_all_projects_metadata_descriptor(self):
        first_project_id = str(self.project_id)
        second_project = self.generate_fixture_project(name="Second Project")
        second_project_id = str(second_project.id)
        closed_project_id = str(self.project_closed.id)

        created = self.post(
            "data/metadata-descriptors/all-projects",
            {
                "entity_type": "Project",
                "name": "Delivery code",
                "data_type": "string",
            },
            201,
        )
        # Both open projects, the closed one is left out.
        self.assertEqual(len(created), 2)
        for project_id in (first_project_id, second_project_id):
            descriptors = self.get(
                f"data/projects/{project_id}/metadata-descriptors"
            )
            self.assertTrue(
                any(d["field_name"] == "delivery_code" for d in descriptors)
            )
        closed = self.get(
            f"data/projects/{closed_project_id}/metadata-descriptors"
        )
        self.assertFalse(
            any(d["field_name"] == "delivery_code" for d in closed)
        )

        updated = self.put(
            "data/metadata-descriptors/all-projects/delivery_code",
            {
                "entity_type": "Project",
                "name": "Ship code",
                "data_type": "string",
            },
        )
        self.assertEqual(len(updated), 2)

        self.post(
            "actions/metadata-descriptors/all-projects/reorder",
            {"entity_type": "Project", "field_order": ["ship_code"]},
            200,
        )

        self.delete(
            "data/metadata-descriptors/all-projects/ship_code"
            "?entity_type=Project",
            200,
        )
        for project_id in (first_project_id, second_project_id):
            descriptors = self.get(
                f"data/projects/{project_id}/metadata-descriptors"
            )
            self.assertFalse(
                any(d["field_name"] == "ship_code" for d in descriptors)
            )

    def test_new_project_copies_project_descriptors(self):
        # A Project descriptor on an open project and one on a closed
        # project: only the open one is copied onto a new project.
        self.post(
            f"data/projects/{self.project_id}/metadata-descriptors",
            {
                "entity_type": "Project",
                "name": "Delivery code",
                "data_type": "string",
            },
        )
        projects_service.add_metadata_descriptor(
            str(self.project_closed.id),
            "Project",
            "Closed only",
            "string",
            [],
            False,
        )
        project = self.post("data/projects", {"name": "Fresh Project"}, 201)
        descriptors = self.get(
            f"data/projects/{project['id']}/metadata-descriptors"
        )
        field_names = [d["field_name"] for d in descriptors]
        self.assertIn("delivery_code", field_names)
        self.assertNotIn("closed_only", field_names)

    def test_add_asset_metadata_descriptor(self):
        descriptor = self.post(
            f"data/projects/{self.project_id}/metadata-descriptors",
            {
                "entity_type": "Asset",
                "name": "environment type",
                "data_type": "list",
                "choices": ["indoor", "outdoor"],
            },
        )
        descriptor = self.get(
            f"data/projects/{self.project_id}/metadata-descriptors/{descriptor['id']}"
        )
        descriptor = self.post(
            f"data/projects/{self.project_id}/metadata-descriptors",
            {
                "entity_type": "Shot",
                "name": "Contractor",
                "data_type": "list",
                "choices": ["studio1", "studio2"],
            },
        )
        descriptors = self.get(
            f"data/projects/{self.project_id}/metadata-descriptors",
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
            f"data/projects/{self.project_id}/metadata-descriptors",
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
            f"data/projects/{self.project_id}/metadata-descriptors",
            {
                "entity_type": "Asset",
                "name": "Contractor",
                "data_type": "list",
                "choices": ["contractor 1", "contractor 2"],
            },
        )
        self.asset.update({"data": {"contractor": "contractor 1"}})
        asset = self.get(f"data/assets/{self.asset_id}")
        self.put(
            f"data/projects/{self.project_id}/metadata-descriptors/{descriptor['id']}",
            {"name": "Team", "data_type": "list"},
        )
        descriptors = self.get(
            f"data/projects/{self.project_id}/metadata-descriptors"
        )
        self.assertEqual(len(descriptors), 1)
        asset = self.get(f"data/entities/{self.asset_id}")
        self.assertEqual(asset["data"].get("team"), "contractor 1")

    def test_unallowed_update_metadata_descriptor(self):
        descriptor = projects_service.add_metadata_descriptor(
            self.project_id, "Asset", "Contractor", "string", [], False
        )
        self.generate_fixture_user_manager()
        self.log_in_manager()
        self.put(
            f"data/projects/{self.project_id}/metadata-descriptors/{descriptor['id']}",
            {"name": "Team", "data_type": "list"},
            403,
        )

    def test_delete_metadata_descriptor(self):
        descriptor = projects_service.add_metadata_descriptor(
            self.project_id, "Asset", "Contractor", "string", [], False
        )
        self.asset.update({"data": {"contractor": "contractor 1"}})
        self.delete(
            f"data/projects/{self.project_id}/metadata-descriptors/{descriptor['id']}"
        )
        descriptors = self.get(
            f"data/projects/{self.project_id}/metadata-descriptors"
        )
        self.assertEqual(len(descriptors), 0)
        asset = self.get(f"data/assets/{self.asset_id}")
        self.assertFalse("contractor" in asset["data"])

    def test_unallowed_delete_metadata_descriptor(self):
        descriptor = projects_service.add_metadata_descriptor(
            self.project_id, "Asset", "Contractor", "string", [], False
        )
        self.generate_fixture_user_manager()
        self.log_in_manager()
        self.delete(
            f"data/projects/{self.project_id}/metadata-descriptors/{descriptor['id']}",
            403,
        )

    def post_task_descriptor(self, task_type_id, name="Render layer"):
        return self.post(
            f"data/projects/{self.project_id}/metadata-descriptors",
            {
                "entity_type": "Task",
                "task_type_id": task_type_id,
                "name": name,
                "data_type": "string",
            },
        )

    def test_add_task_metadata_descriptor(self):
        self.generate_fixture_task()
        task_type_id = str(self.task_type.id)
        descriptor = self.post_task_descriptor(task_type_id)
        self.assertEqual(descriptor["entity_type"], "Task")
        self.assertEqual(descriptor["task_type_id"], task_type_id)
        self.assertEqual(descriptor["field_name"], "render_layer")
        # The same field name is allowed on another task type but not
        # twice on the same one.
        other = self.post_task_descriptor(str(self.task_type_modeling.id))
        self.assertEqual(other["field_name"], "render_layer")
        self.post(
            f"data/projects/{self.project_id}/metadata-descriptors",
            {
                "entity_type": "Task",
                "task_type_id": task_type_id,
                "name": "Render layer",
                "data_type": "string",
            },
            400,
        )

    def test_task_metadata_descriptor_in_open_projects_payload(self):
        self.generate_fixture_task()
        task_type_id = str(self.task_type.id)
        self.post_task_descriptor(task_type_id)
        projects = self.get("data/projects/open")
        descriptor = projects[0]["descriptors"][0]
        self.assertEqual(descriptor["task_type_id"], task_type_id)

    def test_task_metadata_descriptor_requires_valid_task_type(self):
        self.generate_fixture_task()
        self.post(
            f"data/projects/{self.project_id}/metadata-descriptors",
            {
                "entity_type": "Task",
                "name": "Render layer",
                "data_type": "string",
            },
            400,
        )
        self.post(
            f"data/projects/{self.project_id}/metadata-descriptors",
            {
                "entity_type": "Task",
                "task_type_id": str(fields.gen_uuid()),
                "name": "Render layer",
                "data_type": "string",
            },
            400,
        )
        self.post(
            f"data/projects/{self.project_id}/metadata-descriptors",
            {
                "entity_type": "Asset",
                "task_type_id": str(self.task_type.id),
                "name": "Render layer",
                "data_type": "string",
            },
            400,
        )

    def test_update_task_data_merges_metadata(self):
        self.generate_fixture_task()
        task_id = str(self.task.id)
        self.put(f"data/tasks/{task_id}", {"data": {"render_layer": "bg"}})
        self.put(f"data/tasks/{task_id}", {"data": {"note": "wip"}})
        task = self.get(f"data/tasks/{task_id}")
        self.assertEqual(task["data"].get("render_layer"), "bg")
        self.assertEqual(task["data"].get("note"), "wip")

    def test_rename_and_delete_task_metadata_descriptor(self):
        self.generate_fixture_task()
        task_id = str(self.task.id)
        descriptor = self.post_task_descriptor(str(self.task_type.id))
        self.post_task_descriptor(str(self.task_type_modeling.id))
        other_task = self.generate_fixture_task(
            name="Second", task_type_id=self.task_type_modeling.id
        )
        other_task_id = str(other_task.id)
        self.put(f"data/tasks/{task_id}", {"data": {"render_layer": "bg"}})
        self.put(
            f"data/tasks/{other_task_id}", {"data": {"render_layer": "fg"}}
        )
        self.put(
            f"data/projects/{self.project_id}/metadata-descriptors/{descriptor['id']}",
            {"name": "Layer", "data_type": "string"},
        )
        task = self.get(f"data/tasks/{task_id}")
        self.assertEqual(task["data"].get("layer"), "bg")
        self.assertNotIn("render_layer", task["data"])
        # The same field on another task type is left untouched.
        other_task_data = self.get(f"data/tasks/{other_task_id}")["data"]
        self.assertEqual(other_task_data.get("render_layer"), "fg")
        self.delete(
            f"data/projects/{self.project_id}/metadata-descriptors/{descriptor['id']}"
        )
        task = self.get(f"data/tasks/{task_id}")
        self.assertNotIn("layer", task["data"] or {})
        other_task_data = self.get(f"data/tasks/{other_task_id}")["data"]
        self.assertEqual(other_task_data.get("render_layer"), "fg")
