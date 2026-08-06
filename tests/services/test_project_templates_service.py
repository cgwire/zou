from tests.base import ApiDBTestCase

from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.project import (
    Project,
    ProjectAssetTypeLink,
    ProjectTaskStatusLink,
    ProjectTaskTypeLink,
)
from zou.app.models.project_template import (
    ProjectTemplate,
    ProjectTemplateAssetTypeLink,
    ProjectTemplateTaskStatusLink,
    ProjectTemplateTaskTypeLink,
)
from zou.app.services import (
    project_templates_service,
    projects_service,
)
from zou.app.services.exception import (
    ProjectNotFoundException,
    ProjectTemplateNotFoundException,
    WrongParameterException,
)


class ProjectTemplateServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_asset_type()
        self.generate_fixture_status_automation_to_status()

    # ----- CRUD -----------------------------------------------------------

    def test_create_project_template(self):
        template = project_templates_service.create_project_template(
            name="Series Setup",
            description="Animated series defaults",
            fps="24",
            production_type="tvshow",
            production_style="3d",
        )
        self.assertIsNotNone(template["id"])
        self.assertEqual(template["fps"], "24")
        self.assertEqual(template["production_type"], "tvshow")

    def test_create_template_duplicate_name_raises(self):
        project_templates_service.create_project_template(name="Setup")
        self.assertRaises(
            WrongParameterException,
            project_templates_service.create_project_template,
            name="Setup",
        )

    def test_get_project_templates(self):
        project_templates_service.create_project_template(name="A")
        project_templates_service.create_project_template(name="B")
        templates = project_templates_service.get_project_templates()
        self.assertEqual(len(templates), 2)
        self.assertEqual([t["name"] for t in templates], ["A", "B"])

    def test_get_project_template_by_name(self):
        project_templates_service.create_project_template(name="Series Setup")
        template = project_templates_service.get_project_template_by_name(
            "series setup"
        )
        self.assertEqual(template["name"], "Series Setup")
        self.assertRaises(
            ProjectTemplateNotFoundException,
            project_templates_service.get_project_template_by_name,
            "Series",
        )

    def test_get_project_template_not_found(self):
        self.assertRaises(
            ProjectTemplateNotFoundException,
            project_templates_service.get_project_template,
            "00000000-0000-0000-0000-000000000000",
        )

    def test_update_project_template(self):
        template = project_templates_service.create_project_template(
            name="Setup"
        )
        updated = project_templates_service.update_project_template(
            template["id"], {"description": "new desc", "fps": "30"}
        )
        self.assertEqual(updated["description"], "new desc")
        self.assertEqual(updated["fps"], "30")

    def test_delete_project_template(self):
        template = project_templates_service.create_project_template(
            name="Setup"
        )
        project_templates_service.delete_project_template(template["id"])
        self.assertIsNone(ProjectTemplate.get(template["id"]))

    # ----- Link management ------------------------------------------------

    def test_add_and_remove_task_type(self):
        template = project_templates_service.create_project_template(
            name="Setup"
        )
        link = project_templates_service.add_task_type_to_template(
            template["id"], str(self.task_type_modeling.id), priority=2
        )
        self.assertEqual(link["priority"], 2)

        task_types = project_templates_service.get_template_task_types(
            template["id"]
        )
        self.assertEqual(len(task_types), 1)

        # Idempotent — re-adding updates priority instead of duplicating
        project_templates_service.add_task_type_to_template(
            template["id"], str(self.task_type_modeling.id), priority=5
        )
        task_types = project_templates_service.get_template_task_types(
            template["id"]
        )
        self.assertEqual(len(task_types), 1)

        project_templates_service.remove_task_type_from_template(
            template["id"], str(self.task_type_modeling.id)
        )
        task_types = project_templates_service.get_template_task_types(
            template["id"]
        )
        self.assertEqual(task_types, [])

    def test_add_and_remove_task_status(self):
        template = project_templates_service.create_project_template(
            name="Setup"
        )
        link = project_templates_service.add_task_status_to_template(
            template["id"],
            str(self.task_status.id),
            priority=1,
            roles_for_board=["admin", "manager"],
        )
        self.assertEqual(link["priority"], 1)

        statuses = project_templates_service.get_template_task_statuses(
            template["id"]
        )
        self.assertEqual(len(statuses), 1)

        project_templates_service.remove_task_status_from_template(
            template["id"], str(self.task_status.id)
        )
        statuses = project_templates_service.get_template_task_statuses(
            template["id"]
        )
        self.assertEqual(statuses, [])

    def test_add_and_remove_asset_type(self):
        template = project_templates_service.create_project_template(
            name="Setup"
        )
        project_templates_service.add_asset_type_to_template(
            template["id"], str(self.asset_type.id)
        )
        asset_types = project_templates_service.get_template_asset_types(
            template["id"]
        )
        self.assertEqual(len(asset_types), 1)

        project_templates_service.remove_asset_type_from_template(
            template["id"], str(self.asset_type.id)
        )
        asset_types = project_templates_service.get_template_asset_types(
            template["id"]
        )
        self.assertEqual(asset_types, [])

    def test_add_and_remove_status_automation(self):
        template = project_templates_service.create_project_template(
            name="Setup"
        )
        project_templates_service.add_status_automation_to_template(
            template["id"], str(self.status_automation_to_status.id)
        )
        items = project_templates_service.get_template_status_automations(
            template["id"]
        )
        self.assertEqual(len(items), 1)

        project_templates_service.remove_status_automation_from_template(
            template["id"], str(self.status_automation_to_status.id)
        )
        items = project_templates_service.get_template_status_automations(
            template["id"]
        )
        self.assertEqual(items, [])

    def test_set_metadata_descriptors(self):
        template = project_templates_service.create_project_template(
            name="Setup"
        )
        descriptors = [
            {
                "name": "Difficulty",
                "entity_type": "Asset",
                "data_type": "list",
                "choices": ["easy", "medium", "hard"],
                "for_client": False,
            },
            {
                "name": "Approval status",
                "entity_type": "Shot",
                "data_type": "string",
                "choices": [],
                "for_client": True,
                "departments": [str(self.department.id)],
            },
        ]
        updated = project_templates_service.set_template_metadata_descriptors(
            template["id"], descriptors
        )
        snapshot = updated["metadata_descriptors"]
        self.assertEqual(len(snapshot), 2)
        self.assertEqual(snapshot[0]["field_name"], "difficulty")
        self.assertEqual(snapshot[1]["field_name"], "approval_status")
        self.assertEqual(snapshot[1]["departments"], [str(self.department.id)])

    # ----- Snapshot from project ------------------------------------------

    # ----- Priorities and background files ---------------------------------

    def test_set_template_task_type_priorities(self):
        """
        The ordered id list becomes the priorities, one based, in one pass.
        A task type not yet linked is linked on the way.
        """
        template = project_templates_service.create_project_template(
            name="Priorities"
        )
        project_templates_service.add_task_type_to_template(
            template["id"], str(self.task_type.id), priority=9
        )

        project_templates_service.set_template_task_type_priorities(
            template["id"],
            [str(self.task_type_animation.id), str(self.task_type.id)],
        )

        task_types = project_templates_service.get_template_task_types(
            template["id"]
        )
        # Sorted by priority, so the list order carries the answer too.
        self.assertEqual(
            [(held["id"], held["priority"]) for held in task_types],
            [
                (str(self.task_type_animation.id), 1),
                (str(self.task_type.id), 2),
            ],
        )

    def test_set_template_task_status_priorities_keeps_the_board_roles(self):
        template = project_templates_service.create_project_template(
            name="Status Priorities"
        )
        project_templates_service.add_task_status_to_template(
            template["id"],
            str(self.task_status.id),
            priority=9,
            roles_for_board=["admin"],
        )

        project_templates_service.set_template_task_status_priorities(
            template["id"], [str(self.task_status.id)]
        )

        link = project_templates_service.get_template_task_statuses(
            template["id"]
        )[0]
        self.assertEqual(link["priority"], 1)
        self.assertEqual(link["roles_for_board"], ["admin"])

    def test_add_and_remove_preview_background_file(self):
        template = project_templates_service.create_project_template(
            name="Backgrounds"
        )
        self.generate_fixture_preview_background_file()
        background_id = str(self.preview_background_file.id)

        added = (
            project_templates_service.add_preview_background_file_to_template(
                template["id"], background_id
            )
        )

        self.assertEqual(added["id"], background_id)
        self.assertEqual(
            [
                held["id"]
                for held in project_templates_service.get_template_preview_background_files(
                    template["id"]
                )
            ],
            [background_id],
        )

        project_templates_service.remove_preview_background_file_from_template(
            template["id"], background_id
        )

        self.assertEqual(
            project_templates_service.get_template_preview_background_files(
                template["id"]
            ),
            [],
        )

    def test_set_template_default_preview_background_file(self):
        template = project_templates_service.create_project_template(
            name="Default Background"
        )
        self.generate_fixture_preview_background_file()
        background_id = str(self.preview_background_file.id)
        project_templates_service.add_preview_background_file_to_template(
            template["id"], background_id
        )

        result = project_templates_service.set_template_default_preview_background_file(
            template["id"], background_id
        )

        self.assertEqual(
            result["default_preview_background_file_id"], background_id
        )

    def test_the_default_background_has_to_be_linked_first(self):
        template = project_templates_service.create_project_template(
            name="Unlinked Background"
        )
        self.generate_fixture_preview_background_file()

        self.assertRaises(
            WrongParameterException,
            project_templates_service.set_template_default_preview_background_file,
            template["id"],
            str(self.preview_background_file.id),
        )

    def test_removing_the_default_background_clears_it(self):
        template = project_templates_service.create_project_template(
            name="Cleared Background"
        )
        self.generate_fixture_preview_background_file()
        background_id = str(self.preview_background_file.id)
        project_templates_service.add_preview_background_file_to_template(
            template["id"], background_id
        )
        project_templates_service.set_template_default_preview_background_file(
            template["id"], background_id
        )

        project_templates_service.remove_preview_background_file_from_template(
            template["id"], background_id
        )

        self.assertIsNone(
            project_templates_service.get_project_template(template["id"])[
                "default_preview_background_file_id"
            ]
        )

    def _seed_project_with_full_config(self):
        projects_service.add_task_type_setting(
            self.project_id, str(self.task_type_modeling.id), priority=3
        )
        projects_service.add_task_type_setting(
            self.project_id, str(self.task_type_animation.id), priority=4
        )
        projects_service.create_project_task_status_link(
            str(self.project_id),
            str(self.task_status.id),
            priority=1,
            roles_for_board=["admin", "manager"],
        )
        projects_service.add_asset_type_setting(
            self.project_id, str(self.asset_type.id)
        )
        projects_service.add_metadata_descriptor(
            project_id=str(self.project_id),
            entity_type="Asset",
            name="Difficulty",
            data_type="list",
            choices=["easy", "medium"],
            for_client=False,
            departments=[str(self.department.id)],
        )
        projects_service.update_project(
            str(self.project_id),
            {
                "fps": "30",
                "ratio": "2.39:1",
                "resolution": "2048x858",
                "max_retakes": 5,
                "data": {"foo": "bar"},
            },
        )

    def test_create_template_from_project(self):
        self._seed_project_with_full_config()
        template = project_templates_service.create_template_from_project(
            str(self.project_id),
            name="From project",
        )
        self.assertEqual(template["fps"], "30")
        self.assertEqual(template["ratio"], "2.39:1")
        self.assertEqual(template["max_retakes"], 5)
        self.assertEqual(template["data"], {"foo": "bar"})

        # Link tables snapshot
        task_type_links = ProjectTemplateTaskTypeLink.get_all_by(
            project_template_id=template["id"]
        )
        self.assertEqual(len(task_type_links), 2)
        priorities = {
            link.task_type_id: link.priority for link in task_type_links
        }
        self.assertEqual(priorities[self.task_type_modeling.id], 3)

        task_status_links = ProjectTemplateTaskStatusLink.get_all_by(
            project_template_id=template["id"]
        )
        self.assertEqual(len(task_status_links), 1)
        self.assertEqual(task_status_links[0].priority, 1)

        asset_type_links = ProjectTemplateAssetTypeLink.query.filter_by(
            project_template_id=template["id"]
        ).all()
        self.assertEqual(len(asset_type_links), 1)

        # Metadata descriptor snapshot
        descriptors = template["metadata_descriptors"]
        self.assertEqual(len(descriptors), 1)
        self.assertEqual(descriptors[0]["name"], "Difficulty")
        self.assertEqual(descriptors[0]["data_type"], "list")
        self.assertEqual(
            descriptors[0]["departments"], [str(self.department.id)]
        )

    def test_task_metadata_descriptor_round_trip(self):
        projects_service.add_metadata_descriptor(
            project_id=str(self.project.id),
            entity_type="Task",
            name="Render layer",
            data_type="string",
            choices=[],
            for_client=False,
            task_type_id=str(self.task_type.id),
        )
        template = project_templates_service.create_template_from_project(
            str(self.project.id), name="From production"
        )
        snapshot = template["metadata_descriptors"]
        self.assertEqual(len(snapshot), 1)
        self.assertEqual(snapshot[0]["task_type_id"], str(self.task_type.id))

        project = self.generate_fixture_project(name="Fresh Project")
        project_templates_service.apply_template_to_project(
            str(project.id), template["id"]
        )
        descriptors = MetadataDescriptor.query.filter_by(
            project_id=project.id, entity_type="Task"
        ).all()
        self.assertEqual(len(descriptors), 1)
        self.assertEqual(
            str(descriptors[0].task_type_id), str(self.task_type.id)
        )

    def test_create_template_from_project_does_not_copy_team(self):
        self.generate_fixture_person()
        projects_service.add_team_member(self.project_id, self.person.id)
        template = project_templates_service.create_template_from_project(
            str(self.project_id), name="From project"
        )
        # Templates have no team relationship at all — just confirm no team
        # info leaks via the serialized payload.
        self.assertNotIn("team", template)

    def test_create_template_from_missing_project_raises(self):
        self.assertRaises(
            ProjectNotFoundException,
            project_templates_service.create_template_from_project,
            "00000000-0000-0000-0000-000000000000",
            "From missing",
        )

    # ----- Apply template to project --------------------------------------

    def _build_full_template(self):
        template = project_templates_service.create_project_template(
            name="Full",
            fps="30",
            ratio="2.39:1",
            resolution="2048x858",
            max_retakes=4,
        )
        project_templates_service.add_task_type_to_template(
            template["id"], str(self.task_type_modeling.id), priority=7
        )
        project_templates_service.add_task_status_to_template(
            template["id"],
            str(self.task_status.id),
            priority=1,
            roles_for_board=["admin"],
        )
        project_templates_service.add_asset_type_to_template(
            template["id"], str(self.asset_type.id)
        )
        project_templates_service.set_template_metadata_descriptors(
            template["id"],
            [
                {
                    "name": "Difficulty",
                    "entity_type": "Asset",
                    "data_type": "list",
                    "choices": ["easy"],
                    "for_client": False,
                }
            ],
        )
        return template

    def test_apply_template_to_project(self):
        template = self._build_full_template()
        # Empty target project — no overrides
        target = Project.create(
            name="Target",
            project_status_id=self.open_status.id,
        )
        project_templates_service.apply_template_to_project(
            str(target.id), template["id"]
        )
        # Settings copied
        target_dict = projects_service.get_project(str(target.id))
        self.assertEqual(target_dict["fps"], "30")
        self.assertEqual(target_dict["max_retakes"], 4)

        # Links created
        task_types = ProjectTaskTypeLink.get_all_by(project_id=target.id)
        self.assertEqual(len(task_types), 1)
        self.assertEqual(task_types[0].priority, 7)

        statuses = ProjectTaskStatusLink.get_all_by(project_id=target.id)
        self.assertEqual(len(statuses), 1)

        asset_types = ProjectAssetTypeLink.query.filter_by(
            project_id=target.id
        ).all()
        self.assertEqual(len(asset_types), 1)

        # Metadata descriptors materialized on the project
        descriptors = MetadataDescriptor.query.filter_by(
            project_id=target.id
        ).all()
        self.assertEqual(len(descriptors), 1)
        self.assertEqual(descriptors[0].name, "Difficulty")

    def test_apply_template_is_additive(self):
        template = self._build_full_template()
        target = Project.create(
            name="Target", project_status_id=self.open_status.id
        )
        # Pre-seed an existing link with a different priority — apply must
        # not overwrite it.
        ProjectTaskTypeLink.create(
            project_id=target.id,
            task_type_id=self.task_type_modeling.id,
            priority=99,
        )
        project_templates_service.apply_template_to_project(
            str(target.id), template["id"]
        )
        links = ProjectTaskTypeLink.get_all_by(project_id=target.id)
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].priority, 99)  # untouched

    def test_apply_template_with_explicit_overrides(self):
        template = self._build_full_template()
        target = Project.create(
            name="Target", project_status_id=self.open_status.id
        )
        project_templates_service.apply_template_to_project(
            str(target.id),
            template["id"],
            override_settings={"fps": "60"},
        )
        target_dict = projects_service.get_project(str(target.id))
        self.assertEqual(target_dict["fps"], "60")  # explicit wins
        self.assertEqual(target_dict["max_retakes"], 4)  # template wins

    def test_apply_missing_template_raises(self):
        self.assertRaises(
            ProjectTemplateNotFoundException,
            project_templates_service.apply_template_to_project,
            str(self.project_id),
            "00000000-0000-0000-0000-000000000000",
        )
