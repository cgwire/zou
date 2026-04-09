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
        again = self.get("/data/project-templates/%s" % template["id"])
        self.assertEqual(again["id"], template["id"])

        # Update
        updated = self.put(
            "/data/project-templates/%s" % template["id"],
            {"description": "updated"},
        )
        self.assertEqual(updated["description"], "updated")

        # Delete
        self.delete("/data/project-templates/%s" % template["id"])
        self.assertEqual(self.get("/data/project-templates"), [])

    def test_create_template_duplicate_name_returns_400(self):
        self.post(
            "/data/project-templates", {"name": "Series Setup"}
        )
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
            "/data/project-templates/%s/task-types" % template["id"],
            {
                "task_type_id": str(self.task_type_modeling.id),
                "priority": 3,
            },
        )
        self.assertEqual(link["priority"], 3)

        types = self.get(
            "/data/project-templates/%s/task-types" % template["id"]
        )
        self.assertEqual(len(types), 1)

        self.delete(
            "/data/project-templates/%s/task-types/%s"
            % (template["id"], self.task_type_modeling.id)
        )
        types = self.get(
            "/data/project-templates/%s/task-types" % template["id"]
        )
        self.assertEqual(len(types), 0)

    def test_task_status_link_routes(self):
        template = self._create_template()
        link = self.post(
            "/data/project-templates/%s/task-statuses" % template["id"],
            {
                "task_status_id": str(self.task_status.id),
                "priority": 1,
                "roles_for_board": ["admin", "manager"],
            },
        )
        self.assertEqual(link["priority"], 1)

        statuses = self.get(
            "/data/project-templates/%s/task-statuses" % template["id"]
        )
        self.assertEqual(len(statuses), 1)

        self.delete(
            "/data/project-templates/%s/task-statuses/%s"
            % (template["id"], self.task_status.id)
        )
        statuses = self.get(
            "/data/project-templates/%s/task-statuses" % template["id"]
        )
        self.assertEqual(len(statuses), 0)

    def test_asset_type_link_routes(self):
        template = self._create_template()
        self.post(
            "/data/project-templates/%s/asset-types" % template["id"],
            {"asset_type_id": str(self.asset_type.id)},
        )
        items = self.get(
            "/data/project-templates/%s/asset-types" % template["id"]
        )
        self.assertEqual(len(items), 1)

        self.delete(
            "/data/project-templates/%s/asset-types/%s"
            % (template["id"], self.asset_type.id)
        )
        items = self.get(
            "/data/project-templates/%s/asset-types" % template["id"]
        )
        self.assertEqual(len(items), 0)

    def test_status_automation_link_routes(self):
        template = self._create_template()
        self.post(
            "/data/project-templates/%s/status-automations" % template["id"],
            {
                "status_automation_id": str(
                    self.status_automation_to_status.id
                )
            },
        )
        items = self.get(
            "/data/project-templates/%s/status-automations" % template["id"]
        )
        self.assertEqual(len(items), 1)

        self.delete(
            "/data/project-templates/%s/status-automations/%s"
            % (template["id"], self.status_automation_to_status.id)
        )
        items = self.get(
            "/data/project-templates/%s/status-automations" % template["id"]
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
            "/data/project-templates/%s/metadata-descriptors"
            % template["id"],
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
            "/data/projects/%s/settings/task-types" % self.project_id,
            {"task_type_id": str(self.task_type_modeling.id)},
        )
        template = self.post(
            "/data/project-templates/from-project/%s" % self.project_id,
            {"name": "Snapshot of Cosmos", "description": "snapshot"},
        )
        self.assertEqual(template["name"], "Snapshot of Cosmos")
        types = self.get(
            "/data/project-templates/%s/task-types" % template["id"]
        )
        self.assertEqual(len(types), 1)

    # --- Apply template to existing project ------------------------------

    def test_apply_template_to_project_route(self):
        template = self._create_template()
        self.post(
            "/data/project-templates/%s/task-types" % template["id"],
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
            "/data/projects/%s/apply-template/%s"
            % (target["id"], template["id"]),
            {},
            code=200,
        )
        self.assertEqual(result["id"], target["id"])
        # Verify task type link materialized on the project
        links = self.get(
            "/data/projects/%s" % target["id"]
        )
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
            "/data/project-templates/%s/task-types" % template["id"],
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
        full = self.get("/data/projects/%s" % project["id"])
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
            "/data/project-templates/%s/metadata-descriptors"
            % template["id"],
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
