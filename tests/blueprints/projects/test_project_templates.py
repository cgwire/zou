from tests.base import ApiDBTestCase
from zou.app import db
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.project_template import ProjectTemplateTaskTypeLink
from zou.app.services import projects_service


class ProjectTemplatesRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
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

    def assert_a_link_can_be_added_and_removed(
        self, sub_path, payload, link_id, expected=None
    ):
        """
        Every list a template carries goes the same way: post a link, see it
        in the listing, delete it, see the listing empty again.
        """
        template = self._create_template()
        base = f"/data/project-templates/{template['id']}/{sub_path}"

        created = self.post(base, payload)
        for key, value in (expected or {}).items():
            self.assertEqual(created[key], value)
        self.assertEqual(len(self.get(base)), 1)

        self.delete(f"{base}/{link_id}")
        self.assertEqual(self.get(base), [])

    def test_task_type_link_routes(self):
        self.assert_a_link_can_be_added_and_removed(
            "task-types",
            {
                "task_type_id": str(self.task_type_modeling.id),
                "priority": 3,
            },
            self.task_type_modeling.id,
            expected={"priority": 3},
        )

    def test_task_type_link_bitrates_route(self):
        template = self._create_template()
        base = f"/data/project-templates/{template['id']}/task-types"
        task_type_id = str(self.task_type_modeling.id)
        self.post(
            base,
            {
                "task_type_id": task_type_id,
                "priority": 1,
                "hd_bitrate_compression": 20,
                "ld_bitrate_compression": 4,
            },
        )
        # A priority-only call, as the reorder does, keeps the bitrates.
        link = self.post(base, {"task_type_id": task_type_id, "priority": 2})
        self.assertEqual(
            (
                link["priority"],
                link["hd_bitrate_compression"],
                link["ld_bitrate_compression"],
            ),
            (2, 20, 4),
        )
        listed = self.get(base)[0]
        self.assertEqual(listed["hd_bitrate_compression"], 20)
        self.post(
            base,
            {"task_type_id": task_type_id, "hd_bitrate_compression": 0},
            400,
        )
        self.post(
            base,
            {
                "task_type_id": task_type_id,
                "hd_bitrate_compression": 10,
                "ld_bitrate_compression": 12,
            },
            400,
        )

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

    def test_reorder_routes_refuse_a_body_without_the_id_list(self):
        template = self.post("/data/project-templates", {"name": "Empty"})
        self.post(
            f"/actions/project-templates/{template['id']}/task-types/reorder",
            {"task_type_ids": "not-a-list"},
            400,
        )
        self.post(
            f"/actions/project-templates/{template['id']}/task-statuses/reorder",
            [],
            400,
        )

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
        self.assert_a_link_can_be_added_and_removed(
            "task-statuses",
            {
                "task_status_id": str(self.task_status.id),
                "priority": 1,
                "roles_for_board": ["admin", "manager"],
            },
            self.task_status.id,
            expected={"priority": 1},
        )

    def test_task_type_link_is_client_visible(self):
        template = self._create_template()
        url = f"/data/project-templates/{template['id']}/task-types"
        task_type_id = str(self.task_type.id)
        link = self.post(
            url, {"task_type_id": task_type_id, "is_client_visible": True}
        )
        self.assertTrue(link["is_client_visible"])
        link = self.post(url, {"task_type_id": task_type_id, "priority": 2})
        self.assertTrue(link["is_client_visible"])
        link = self.post(
            url, {"task_type_id": task_type_id, "is_client_visible": False}
        )
        self.assertFalse(link["is_client_visible"])

    def test_task_status_link_is_client_allowed(self):
        template = self._create_template()
        url = f"/data/project-templates/{template['id']}/task-statuses"
        status_id = str(self.task_status.id)

        def link_value():
            statuses = self.get(url)
            return {s["id"]: s for s in statuses}[status_id][
                "link_is_client_allowed"
            ]

        self.post(url, {"task_status_id": status_id})
        self.assertIsNone(link_value())
        self.post(
            url, {"task_status_id": status_id, "is_client_allowed": True}
        )
        self.assertIs(link_value(), True)
        self.post(url, {"task_status_id": status_id, "priority": 3})
        self.assertIs(link_value(), True)
        self.post(
            url, {"task_status_id": status_id, "is_client_allowed": False}
        )
        self.assertIs(link_value(), False)
        self.post(
            url, {"task_status_id": status_id, "is_client_allowed": None}
        )
        self.assertIsNone(link_value())
        studio = {s["id"]: s for s in self.get(url)}[status_id]
        self.assertIn("is_client_allowed", studio)

    def test_asset_type_link_routes(self):
        self.assert_a_link_can_be_added_and_removed(
            "asset-types",
            {"asset_type_id": str(self.asset_type.id)},
            self.asset_type.id,
        )

    def test_status_automation_link_routes(self):
        self.assert_a_link_can_be_added_and_removed(
            "status-automations",
            {"status_automation_id": str(self.status_automation_to_status.id)},
            self.status_automation_to_status.id,
        )

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


class ProjectTemplateWorkflowsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_asset_type()
        self.project_id = str(self.project.id)
        self.asset_type_id = str(self.asset_type.id)
        self.shaders_id = str(self.task_type.id)
        self.modeling_id = str(self.task_type_modeling.id)

    def create_template(self, name="Workflow setup"):
        template = self.post("/data/project-templates", {"name": name})
        path = f"/data/project-templates/{template['id']}"
        self.post(
            f"{path}/asset-types",
            {"asset_type_id": self.asset_type_id},
        )
        for task_type_id in [self.shaders_id, self.modeling_id]:
            self.post(f"{path}/task-types", {"task_type_id": task_type_id})
        return template, f"{path}/asset-types/{self.asset_type_id}/task-types"

    def template_workflow(self, template):
        asset_types = self.get(
            f"/data/project-templates/{template['id']}/asset-types"
        )
        return asset_types[0]["workflow"]

    def project_workflows(self, project_id):
        return self.get(f"/data/projects/{project_id}")["asset_type_workflows"]

    def test_set_and_reset_workflow(self):
        template, route = self.create_template()
        self.assertEqual(self.template_workflow(template), [])
        self.put(route, {"task_type_ids": [self.shaders_id]})
        self.assertEqual(self.template_workflow(template), [self.shaders_id])
        self.put(route, {"task_type_ids": []})
        self.assertEqual(self.template_workflow(template), [])

    def test_set_workflow_refuses_invalid_ids(self):
        _, route = self.create_template()
        self.put(route, {"task_type_ids": [self.project_id]}, 400)
        self.put(route, {}, 400)
        unknown = route.replace(self.asset_type_id, self.project_id)
        self.put(unknown, {"task_type_ids": [self.shaders_id]}, 400)

    def test_set_workflow_requires_admin(self):
        _, route = self.create_template()
        self.generate_fixture_user_manager()
        self.log_in_manager()
        self.put(route, {"task_type_ids": [self.shaders_id]}, 403)

    def test_removing_a_task_type_removes_it_from_the_workflows(self):
        template, route = self.create_template()
        self.put(route, {"task_type_ids": [self.shaders_id, self.modeling_id]})
        self.delete(
            f"/data/project-templates/{template['id']}/task-types"
            f"/{self.shaders_id}"
        )
        self.assertEqual(self.template_workflow(template), [self.modeling_id])

    def test_removing_an_asset_type_removes_its_workflow(self):
        template, route = self.create_template()
        self.put(route, {"task_type_ids": [self.shaders_id]})
        path = f"/data/project-templates/{template['id']}/asset-types"
        self.delete(f"{path}/{self.asset_type_id}")
        self.post(path, {"asset_type_id": self.asset_type_id})
        self.assertEqual(self.template_workflow(template), [])

    def test_stale_workflow_links_are_not_copied(self):
        template, route = self.create_template()
        self.put(route, {"task_type_ids": [self.shaders_id]})
        ProjectTemplateTaskTypeLink.query.filter_by(
            project_template_id=template["id"], task_type_id=self.shaders_id
        ).delete()
        db.session.commit()
        self.post(
            f"/data/projects/{self.project_id}"
            f"/apply-template/{template['id']}",
            {},
            200,
        )
        self.assertEqual(self.project_workflows(self.project_id), {})

    def test_stale_project_workflow_links_are_not_copied(self):
        projects_service.add_asset_type_setting(
            self.project_id, self.asset_type_id
        )
        projects_service.add_task_type_setting(
            self.project_id, self.shaders_id
        )
        projects_service.set_asset_type_workflow(
            self.project_id, self.asset_type_id, [self.shaders_id]
        )
        ProjectTaskTypeLink.query.filter_by(
            project_id=self.project_id, task_type_id=self.shaders_id
        ).delete()
        db.session.commit()
        template = self.post(
            f"/data/project-templates/from-project/{self.project_id}",
            {"name": "From stale project"},
        )
        self.assertEqual(self.template_workflow(template), [])

    def test_template_from_project_copies_the_workflows(self):
        projects_service.add_asset_type_setting(
            self.project_id, self.asset_type_id
        )
        projects_service.add_task_type_setting(
            self.project_id, self.shaders_id
        )
        projects_service.set_asset_type_workflow(
            self.project_id, self.asset_type_id, [self.shaders_id]
        )
        template = self.post(
            f"/data/project-templates/from-project/{self.project_id}",
            {"name": "From project"},
        )
        self.assertEqual(self.template_workflow(template), [self.shaders_id])

    def test_apply_template_copies_the_workflows(self):
        template, route = self.create_template()
        self.put(route, {"task_type_ids": [self.shaders_id]})
        self.post(
            f"/data/projects/{self.project_id}"
            f"/apply-template/{template['id']}",
            {},
            200,
        )
        self.assertEqual(
            self.project_workflows(self.project_id),
            {self.asset_type_id: [self.shaders_id]},
        )

    def test_apply_template_keeps_a_workflow_the_project_sets(self):
        template, route = self.create_template()
        self.put(route, {"task_type_ids": [self.shaders_id]})
        projects_service.add_asset_type_setting(
            self.project_id, self.asset_type_id
        )
        projects_service.add_task_type_setting(
            self.project_id, self.modeling_id
        )
        projects_service.set_asset_type_workflow(
            self.project_id, self.asset_type_id, [self.modeling_id]
        )
        self.post(
            f"/data/projects/{self.project_id}"
            f"/apply-template/{template['id']}",
            {},
            200,
        )
        self.assertEqual(
            self.project_workflows(self.project_id),
            {self.asset_type_id: [self.modeling_id]},
        )
