from tests.base import ApiDBTestCase

from zou.app.models.metadata_descriptor import MetadataDescriptor


class ProjectTemplatesRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(ProjectTemplatesRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_done()
        self.generate_fixture_asset_type()
        self.generate_fixture_status_automation_to_status()
        self.project_id = str(self.project.id)

    # --- CRUD via routes -----------------------------------------------

    def test_crud_project_template(self):
        # Create
        template = self.post(
            "/data/project-templates",
            {
                "name": "Series Setup",
                "description": "Animated series setup",
                "fps": "24",
                "production_type": "tvshow",
                "production_style": "3d",
            },
        )
        self.assertIsNotNone(template["id"])
        self.assertEqual(template["fps"], "24")

        # List
        templates = self.get("/data/project-templates")
        self.assertEqual(len(templates), 1)

        # Get
        again = self.get(f"/data/project-templates/{template['id']}")
        self.assertEqual(again["id"], template["id"])

        # Update
        updated = self.put(
            f"/data/project-templates/{template['id']}",
            {"description": "updated"},
        )
        self.assertEqual(updated["description"], "updated")

        # Delete
        self.delete(f"/data/project-templates/{template['id']}")
        self.assertEqual(self.get("/data/project-templates"), [])

    def test_create_template_duplicate_name_returns_400(self):
        self.post("/data/project-templates", {"name": "Series Setup"})
        self.post(
            "/data/project-templates",
            {"name": "Series Setup"},
            code=400,
        )

    # --- Link management -------------------------------------------------

    def _create_template(self, name="Setup"):
        return self.post("/data/project-templates", {"name": name})

    def test_task_type_link_routes(self):
        template = self._create_template()
        link = self.post(
            f"/data/project-templates/{template['id']}/task-types",
            {
                "task_type_id": str(self.task_type_modeling.id),
                "priority": 3,
            },
        )
        self.assertEqual(link["priority"], 3)

        types = self.get(
            f"/data/project-templates/{template['id']}/task-types"
        )
        self.assertEqual(len(types), 1)

        self.delete(
            f'/data/project-templates/{template["id"]}/task-types/{self.task_type_modeling.id}'
        )
        types = self.get(
            f"/data/project-templates/{template['id']}/task-types"
        )
        self.assertEqual(len(types), 0)

    def test_task_type_reorder_route(self):
        template = self._create_template()
        tt1 = str(self.task_type_modeling.id)
        tt2 = str(self.task_type_concept.id)
        self.post(
            f"/data/project-templates/{template['id']}/task-types",
            {"task_type_id": tt1, "priority": 1},
        )
        self.post(
            f"/data/project-templates/{template['id']}/task-types",
            {"task_type_id": tt2, "priority": 2},
        )
        result = self.post(
            f"/actions/project-templates/{template['id']}/task-types/reorder",
            {"task_type_ids": [tt2, tt1]},
            200,
        )
        by_type = {link["task_type_id"]: link["priority"] for link in result}
        self.assertEqual(by_type[tt2], 1)
        self.assertEqual(by_type[tt1], 2)

    def test_task_status_reorder_route_preserves_roles(self):
        template = self._create_template()
        ts1 = str(self.task_status.id)
        ts2 = str(self.task_status_done.id)
        self.post(
            f"/data/project-templates/{template['id']}/task-statuses",
            {
                "task_status_id": ts1,
                "priority": 1,
                "roles_for_board": ["manager"],
            },
        )
        self.post(
            f"/data/project-templates/{template['id']}/task-statuses",
            {"task_status_id": ts2, "priority": 2},
        )
        result = self.post(
            f"/actions/project-templates/{template['id']}/task-statuses/reorder",
            {"task_status_ids": [ts2, ts1]},
            200,
        )
        by_status = {link["task_status_id"]: link for link in result}
        self.assertEqual(by_status[ts2]["priority"], 1)
        self.assertEqual(by_status[ts1]["priority"], 2)
        # Board roles survive the reorder (only priority is updated).
        statuses = self.get(
            f"/data/project-templates/{template['id']}/task-statuses"
        )
        by_id = {status["id"]: status for status in statuses}
        self.assertIn("manager", by_id[ts1]["roles_for_board"])

    def test_task_status_link_routes(self):
        template = self._create_template()
        link = self.post(
            f"/data/project-templates/{template['id']}/task-statuses",
            {
                "task_status_id": str(self.task_status.id),
                "priority": 1,
                "roles_for_board": ["admin", "manager"],
            },
        )
        self.assertEqual(link["priority"], 1)

        statuses = self.get(
            f"/data/project-templates/{template['id']}/task-statuses"
        )
        self.assertEqual(len(statuses), 1)

        self.delete(
            f'/data/project-templates/{template["id"]}/task-statuses/{self.task_status.id}'
        )
        statuses = self.get(
            f"/data/project-templates/{template['id']}/task-statuses"
        )
        self.assertEqual(len(statuses), 0)

    def test_asset_type_link_routes(self):
        template = self._create_template()
        self.post(
            f"/data/project-templates/{template['id']}/asset-types",
            {"asset_type_id": str(self.asset_type.id)},
        )
        items = self.get(
            f"/data/project-templates/{template['id']}/asset-types"
        )
        self.assertEqual(len(items), 1)

        self.delete(
            f"/data/project-templates/{template['id']}/asset-types/{self.asset_type.id}"
        )
        items = self.get(
            f"/data/project-templates/{template['id']}/asset-types"
        )
        self.assertEqual(len(items), 0)

    def test_status_automation_link_routes(self):
        template = self._create_template()
        self.post(
            f"/data/project-templates/{template['id']}/status-automations",
            {"status_automation_id": str(self.status_automation_to_status.id)},
        )
        items = self.get(
            f"/data/project-templates/{template['id']}/status-automations"
        )
        self.assertEqual(len(items), 1)

        self.delete(
            f'/data/project-templates/{template["id"]}/status-automations/{self.status_automation_to_status.id}'
        )
        items = self.get(
            f"/data/project-templates/{template['id']}/status-automations"
        )
        self.assertEqual(len(items), 0)

    def test_set_metadata_descriptors_route(self):
        template = self._create_template()
        descriptors = [
            {
                "name": "Difficulty",
                "entity_type": "Asset",
                "data_type": "list",
                "choices": ["easy", "medium"],
                "for_client": False,
                "departments": [str(self.department.id)],
            }
        ]
        result = self.put(
            f"/data/project-templates/{template['id']}/metadata-descriptors",
            {"metadata_descriptors": descriptors},
        )
        self.assertEqual(len(result["metadata_descriptors"]), 1)
        self.assertEqual(
            result["metadata_descriptors"][0]["field_name"], "difficulty"
        )

    # --- Snapshot from project ------------------------------------------

    def test_create_template_from_project_route(self):
        # Configure the source project a bit
        self.post(
            f"/data/projects/{self.project_id}/settings/task-types",
            {"task_type_id": str(self.task_type_modeling.id)},
        )
        template = self.post(
            f"/data/project-templates/from-project/{self.project_id}",
            {"name": "Snapshot of Cosmos", "description": "snapshot"},
        )
        self.assertEqual(template["name"], "Snapshot of Cosmos")
        types = self.get(
            f"/data/project-templates/{template['id']}/task-types"
        )
        self.assertEqual(len(types), 1)

    # --- Apply template to existing project ------------------------------

    def test_apply_template_to_project_route(self):
        template = self._create_template()
        self.post(
            f"/data/project-templates/{template['id']}/task-types",
            {
                "task_type_id": str(self.task_type_modeling.id),
                "priority": 5,
            },
        )

        target = self.post(
            "/data/projects",
            {"name": "Target Project"},
        )
        result = self.post(
            f"/data/projects/{target['id']}/apply-template/{template['id']}",
            {},
            code=200,
        )
        self.assertEqual(result["id"], target["id"])
        # Verify task type link materialized on the project
        links = self.get(f"/data/projects/{target['id']}")
        self.assertIn(
            str(self.task_type_modeling.id), links.get("task_types", [])
        )

    # --- Project creation with template ---------------------------------

    def test_create_project_with_template_id(self):
        template = self.post(
            "/data/project-templates",
            {
                "name": "Template",
                "fps": "30",
                "ratio": "2.39:1",
                "max_retakes": 5,
            },
        )
        self.post(
            f"/data/project-templates/{template['id']}/task-types",
            {"task_type_id": str(self.task_type_modeling.id)},
        )

        project = self.post(
            "/data/projects",
            {
                "name": "From Template",
                "project_template_id": template["id"],
            },
        )
        self.assertEqual(project["fps"], "30")
        self.assertEqual(project["ratio"], "2.39:1")
        self.assertEqual(project["max_retakes"], 5)
        # Task type link materialized
        full = self.get(f"/data/projects/{project['id']}")
        self.assertIn(
            str(self.task_type_modeling.id), full.get("task_types", [])
        )

    def test_create_project_explicit_field_overrides_template(self):
        template = self.post(
            "/data/project-templates",
            {"name": "Template", "fps": "30", "max_retakes": 5},
        )
        project = self.post(
            "/data/projects",
            {
                "name": "From Template With Override",
                "project_template_id": template["id"],
                "fps": "60",
            },
        )
        self.assertEqual(project["fps"], "60")  # explicit wins
        self.assertEqual(project["max_retakes"], 5)  # template wins

    def test_create_project_with_template_metadata_descriptors(self):
        template = self.post(
            "/data/project-templates",
            {"name": "Template With Metadata"},
        )
        self.put(
            f"/data/project-templates/{template['id']}/metadata-descriptors",
            {
                "metadata_descriptors": [
                    {
                        "name": "Difficulty",
                        "entity_type": "Asset",
                        "data_type": "list",
                        "choices": ["easy", "medium"],
                        "for_client": False,
                    }
                ]
            },
        )
        project = self.post(
            "/data/projects",
            {
                "name": "From Template Metadata",
                "project_template_id": template["id"],
            },
        )
        descriptors = MetadataDescriptor.query.filter_by(
            project_id=project["id"]
        ).all()
        self.assertEqual(len(descriptors), 1)
        self.assertEqual(descriptors[0].name, "Difficulty")

    # --- Default preview background file --------------------------------

    def _new_template(self, name="Series Setup"):
        return self.post("/data/project-templates", {"name": name})

    def test_set_template_default_background(self):
        template = self._new_template()
        background = self.generate_fixture_preview_background_file()
        self.post(
            f"/data/project-templates/{template['id']}"
            f"/preview-background-files",
            {"preview_background_file_id": str(background.id)},
        )

        path = (
            f"/data/project-templates/{template['id']}"
            f"/default-preview-background-file"
        )
        result = self.put(
            path, {"default_preview_background_file_id": str(background.id)}
        )
        self.assertEqual(
            result["default_preview_background_file_id"], str(background.id)
        )

        # Passing null clears it, which is how a studio drops the default.
        result = self.put(path, {"default_preview_background_file_id": None})
        self.assertIsNone(result["default_preview_background_file_id"])

    def test_removing_the_default_background_clears_it(self):
        """
        Unlinking a background that was the template default has to clear the
        default too, otherwise the template keeps pointing at a file it no
        longer carries.
        """
        template = self._new_template()
        background = self.generate_fixture_preview_background_file()
        self.post(
            f"/data/project-templates/{template['id']}"
            f"/preview-background-files",
            {"preview_background_file_id": str(background.id)},
        )
        self.put(
            f"/data/project-templates/{template['id']}"
            f"/default-preview-background-file",
            {"default_preview_background_file_id": str(background.id)},
        )

        self.delete(
            f"/data/project-templates/{template['id']}"
            f"/preview-background-files/{background.id}"
        )

        template_again = self.get(f"/data/project-templates/{template['id']}")
        self.assertIsNone(template_again["default_preview_background_file_id"])
        self.assertEqual(
            self.get(
                f"/data/project-templates/{template['id']}"
                f"/preview-background-files"
            ),
            [],
        )

    def test_set_template_default_background_not_linked(self):
        """
        The default has to be one of the template's own backgrounds, so a
        file that was never linked to it is refused.
        """
        template = self._new_template()
        background = self.generate_fixture_preview_background_file()

        self.put(
            f"/data/project-templates/{template['id']}"
            f"/default-preview-background-file",
            {"default_preview_background_file_id": str(background.id)},
            400,
        )
