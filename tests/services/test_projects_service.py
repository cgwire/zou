from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.project_status import ProjectStatus
from zou.app.services import (
    breakdown_service,
    deletion_service,
    projects_service,
)
from zou.app.services.exception import (
    MetadataDescriptorNotFoundException,
    ProjectNotFoundException,
    WrongParameterException,
)


class ProjectServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(ProjectServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project_closed_status()
        self.generate_fixture_project()
        self.generate_fixture_project_closed()

    def test_get_open_projects(self):
        projects = projects_service.open_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual("Cosmos Landromat", projects[0]["name"])

    def test_get_projects(self):
        projects = projects_service.get_projects()
        self.assertEqual(len(projects), 2)
        self.assertEqual(projects[0]["project_status_name"], "Open")

    def test_get_or_create_status(self):
        project_status = projects_service.get_or_create_status("Frozen")
        statuses = ProjectStatus.query.all()
        self.assertEqual(project_status["name"], "Frozen")
        self.assertEqual(len(statuses), 3)

        project_status = projects_service.get_or_create_status("Frozen")
        self.assertEqual(project_status["name"], "Frozen")
        self.assertEqual(len(statuses), 3)

    def test_get_or_create_open_status(self):
        project_status = projects_service.get_or_create_open_status()
        self.assertEqual(project_status["name"], "Open")

    def test_save_project_status(self):
        statuses = projects_service.save_project_status(
            ["Frozen", "Postponed"]
        )
        self.assertEqual(len(statuses), 2)
        statuses = ProjectStatus.query.all()
        self.assertEqual(len(statuses), 4)

        statuses = projects_service.save_project_status(
            ["Frozen", "Postponed"]
        )
        self.assertEqual(len(statuses), 2)
        statuses = ProjectStatus.query.all()
        self.assertEqual(len(statuses), 4)

    def test_get_or_create_project(self):
        project = projects_service.get_or_create_project("Agent 327")
        projects = projects_service.get_projects()
        self.assertIsNotNone(project["id"])
        self.assertEqual(project["name"], "Agent 327")
        self.assertEqual(len(projects), 3)

    def test_get_project_by_name(self):
        project = projects_service.get_project_by_name(self.project.name)
        self.assertEqual(project["name"], self.project.name)
        self.assertRaises(
            ProjectNotFoundException,
            projects_service.get_project_by_name,
            "missing",
        )

    def test_get_project(self):
        project = projects_service.get_project(self.project.id)
        self.assertEqual(project["name"], self.project.name)
        self.assertRaises(
            ProjectNotFoundException, projects_service.get_project, "wrongid"
        )

    def test_update_project(self):
        new_name = "New name"
        projects_service.update_project(self.project.id, {"name": new_name})
        project = projects_service.get_project(self.project.id)
        self.assertEqual(project["name"], new_name)

    def test_add_team_member(self):
        self.generate_fixture_person()
        projects_service.add_team_member(self.project.id, self.person.id)
        project = projects_service.get_project(self.project.id, relations=True)
        self.assertEqual(project["team"], [str(self.person.id)])

    def test_remove_team_member(self):
        self.generate_fixture_person()
        projects_service.add_team_member(self.project.id, self.person.id)
        projects_service.remove_team_member(self.project.id, self.person.id)
        project = projects_service.get_project(self.project.id, relations=True)
        self.assertEqual(project["team"], [])

    def test_add_asset_type_setting(self):
        self.generate_fixture_asset_type()
        projects_service.add_asset_type_setting(
            self.project.id, self.asset_type.id
        )
        project = projects_service.get_project(self.project.id, relations=True)
        self.assertEqual(project["asset_types"], [str(self.asset_type.id)])

    def test_remove_asset_type(self):
        self.generate_fixture_asset_type()
        projects_service.add_asset_type_setting(
            self.project.id, self.asset_type.id
        )
        projects_service.remove_asset_type_setting(
            self.project.id, self.asset_type.id
        )
        project = projects_service.get_project(self.project.id, relations=True)
        self.assertEqual(project["asset_types"], [])

    def test_add_task_type_setting(self):
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        projects_service.add_task_type_setting(
            self.project.id, self.task_type.id
        )
        project = projects_service.get_project(self.project.id, relations=True)
        self.assertEqual(project["task_types"], [str(self.task_type.id)])

    def test_remove_task_type(self):
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        projects_service.add_task_type_setting(
            self.project.id, self.task_type.id
        )
        projects_service.remove_task_type_setting(
            self.project.id, self.task_type.id
        )
        project = projects_service.get_project(self.project.id, relations=True)
        self.assertEqual(project["task_types"], [])

    def test_add_task_status_setting(self):
        self.generate_fixture_task_status()
        projects_service.add_task_status_setting(
            self.project.id, self.task_status.id
        )
        project = projects_service.get_project(self.project.id, relations=True)
        self.assertEqual(project["task_statuses"], [str(self.task_status.id)])

    def test_remove_task_status(self):
        self.generate_fixture_task_status()
        projects_service.add_task_status_setting(
            self.project.id, self.task_status.id
        )
        projects_service.remove_task_status_setting(
            self.project.id, self.task_status.id
        )
        project = projects_service.get_project(self.project.id, relations=True)
        self.assertEqual(project["task_statuses"], [])

    def test_add_asset_metadata_descriptor(self):
        descriptor = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Is Outdoor", "string", [], False
        )
        self.assertIsNotNone(MetadataDescriptor.get(descriptor["id"]))
        descriptor = projects_service.add_metadata_descriptor(
            self.project.id,
            "Asset",
            "Contractor",
            "list",
            ["contractor 1", "contractor 2"],
            False,
        )
        descriptors = projects_service.get_metadata_descriptors(
            self.project.id
        )
        self.assertEqual(len(descriptors), 2)
        self.assertEqual(descriptors[0]["id"], descriptor["id"])
        self.assertEqual(descriptors[0]["field_name"], "contractor")
        self.assertEqual(descriptors[1]["field_name"], "is_outdoor")

        descriptors = projects_service.get_metadata_descriptors(
            self.project.id, for_client=True
        )
        self.assertEqual(len(descriptors), 0)

    def test_update_metadata_descriptor(self):
        asset = self.generate_fixture_asset_type()
        asset = self.generate_fixture_asset()
        descriptor = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Contractor", "string", [], False
        )
        asset.update({"data": {"contractor": "contractor 1"}})
        self.assertTrue("contractor" in asset.data)
        projects_service.update_metadata_descriptor(
            descriptor["id"], {"name": "Team", "for_client": True}
        )
        descriptors = projects_service.get_metadata_descriptors(
            self.project.id
        )
        self.assertEqual(len(descriptors), 1)
        self.assertTrue(descriptors[0]["for_client"])
        asset = Entity.get(asset.id)
        self.assertEqual(asset.data.get("team"), "contractor 1")

    def test_add_delete_metadata_descriptor(self):
        asset = self.generate_fixture_asset_type()
        asset = self.generate_fixture_asset()
        descriptor = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Contractor", "string", [], False
        )
        asset.update({"data": {"contractor": "contractor 1"}})
        self.assertTrue("contractor" in asset.data)

        projects_service.remove_metadata_descriptor(descriptor["id"])
        descriptors = projects_service.get_metadata_descriptors(
            self.project.id
        )
        self.assertEqual(len(descriptors), 0)
        asset = Entity.get(asset.id)
        self.assertFalse("contractor" in asset.data)

    def test_delete_project(self):
        self.generate_fixture_asset_type()
        self.generate_fixture_asset_types()
        self.generate_assigned_task()
        self.generate_fixture_episode()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        breakdown_service.create_casting_link(self.shot.id, self.asset.id)

        project_id = str(self.project.id)
        deletion_service.remove_project(project_id)
        self.assertIsNone(Project.get(project_id))

    def test_is_tv_show(self):
        self.assertFalse(projects_service.is_tv_show(self.project.serialize()))
        self.project.update({"production_type": "tvshow"})
        self.assertTrue(projects_service.is_tv_show(self.project.serialize()))

    def test_is_open(self):
        self.assertTrue(projects_service.is_open(self.project.serialize()))
        self.assertFalse(
            projects_service.is_open(self.project_closed.serialize())
        )

    def test_reorder_metadata_descriptors(self):
        descriptor1 = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Contractor", "string", [], False
        )
        descriptor2 = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Environment", "string", [], False
        )
        descriptor3 = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Location", "string", [], False
        )
        descriptor4 = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Type", "string", [], False
        )
        descriptor5 = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Status", "string", [], False
        )

        descriptors = projects_service.get_metadata_descriptors(
            self.project.id
        )
        self.assertEqual(len(descriptors), 5)

        descriptor_ids = [
            str(descriptor3["id"]),
            str(descriptor1["id"]),
            str(descriptor5["id"]),
        ]
        reordered = projects_service.reorder_metadata_descriptors(
            self.project.id, "Asset", descriptor_ids
        )

        self.assertEqual(len(reordered), 5)
        self.assertEqual(reordered[0]["id"], descriptor3["id"])
        self.assertEqual(reordered[0]["position"], 1)
        self.assertEqual(reordered[1]["id"], descriptor1["id"])
        self.assertEqual(reordered[1]["position"], 2)
        self.assertEqual(reordered[2]["id"], descriptor5["id"])
        self.assertEqual(reordered[2]["position"], 3)
        self.assertEqual(reordered[3]["id"], descriptor2["id"])
        self.assertEqual(reordered[3]["position"], 4)
        self.assertEqual(reordered[4]["id"], descriptor4["id"])
        self.assertEqual(reordered[4]["position"], 5)

        self.assertIn(reordered[3]["name"], ["Environment"])
        self.assertIn(reordered[4]["name"], ["Type"])

    def test_reorder_metadata_descriptors_all_included(self):
        descriptor1 = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Contractor", "string", [], False
        )
        descriptor2 = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Environment", "string", [], False
        )

        descriptor_ids = [
            str(descriptor2["id"]),
            str(descriptor1["id"]),
        ]
        reordered = projects_service.reorder_metadata_descriptors(
            self.project.id, "Asset", descriptor_ids
        )

        self.assertEqual(len(reordered), 2)
        self.assertEqual(reordered[0]["id"], descriptor2["id"])
        self.assertEqual(reordered[0]["position"], 1)
        self.assertEqual(reordered[1]["id"], descriptor1["id"])
        self.assertEqual(reordered[1]["position"], 2)

    def test_reorder_metadata_descriptors_empty_list(self):
        descriptor1 = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Contractor", "string", [], False
        )
        descriptor2 = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Environment", "string", [], False
        )
        descriptor3 = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Location", "string", [], False
        )

        descriptor_ids = []
        reordered = projects_service.reorder_metadata_descriptors(
            self.project.id, "Asset", descriptor_ids
        )

        self.assertEqual(len(reordered), 3)
        self.assertEqual(reordered[0]["name"], "Contractor")
        self.assertEqual(reordered[0]["position"], 1)
        self.assertEqual(reordered[1]["name"], "Environment")
        self.assertEqual(reordered[1]["position"], 2)
        self.assertEqual(reordered[2]["name"], "Location")
        self.assertEqual(reordered[2]["position"], 3)

    def test_reorder_metadata_descriptors_descriptor_not_found(self):
        descriptor1 = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Contractor", "string", [], False
        )

        fake_id = "00000000-0000-0000-0000-000000000000"
        descriptor_ids = [fake_id]

        with self.assertRaises(WrongParameterException):
            projects_service.reorder_metadata_descriptors(
                self.project.id, "Asset", descriptor_ids
            )

    def test_reorder_metadata_descriptors_different_entity_type(self):
        asset_descriptor = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Contractor", "string", [], False
        )
        shot_descriptor = projects_service.add_metadata_descriptor(
            self.project.id, "Shot", "Location", "string", [], False
        )
        descriptor_ids = [str(shot_descriptor["id"])]

        with self.assertRaises(WrongParameterException):
            projects_service.reorder_metadata_descriptors(
                self.project.id, "Asset", descriptor_ids
            )

    def test_get_project_raw(self):
        project = projects_service.get_project_raw(self.project.id)
        self.assertEqual(project.name, self.project.name)
        self.assertRaises(
            ProjectNotFoundException,
            projects_service.get_project_raw,
            "wrong-id",
        )

    def test_get_project_statuses(self):
        statuses = projects_service.get_project_statuses()
        self.assertGreater(len(statuses), 0)
        names = [s["name"] for s in statuses]
        self.assertIn("Open", names)

    def test_get_closed_status(self):
        status = projects_service.get_closed_status()
        self.assertEqual(status["name"], "Closed")

    def test_open_project_ids(self):
        ids = projects_service.open_project_ids()
        self.assertIn(str(self.project.id), ids)
        self.assertNotIn(str(self.project_closed.id), ids)

    def test_get_metadata_descriptor_raw(self):
        descriptor = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Weight", "string", [], False
        )
        raw = projects_service.get_metadata_descriptor_raw(descriptor["id"])
        self.assertEqual(str(raw.id), descriptor["id"])
        self.assertRaises(
            MetadataDescriptorNotFoundException,
            projects_service.get_metadata_descriptor_raw,
            "wrong-id",
        )

    def test_get_metadata_descriptor(self):
        descriptor = projects_service.add_metadata_descriptor(
            self.project.id, "Asset", "Weight", "string", [], False
        )
        result = projects_service.get_metadata_descriptor(descriptor["id"])
        self.assertEqual(result["id"], descriptor["id"])
        self.assertEqual(result["name"], "Weight")

    def test_create_project_task_type_link(self):
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        link = projects_service.create_project_task_type_link(
            str(self.project.id), str(self.task_type.id), 1
        )
        self.assertEqual(link["project_id"], str(self.project.id))
        self.assertEqual(link["task_type_id"], str(self.task_type.id))
        self.assertEqual(link["priority"], 1)
        # Update existing link
        link2 = projects_service.create_project_task_type_link(
            str(self.project.id), str(self.task_type.id), 5
        )
        self.assertEqual(link2["priority"], 5)

    def test_create_project_task_type_link_invalid(self):
        self.assertRaises(
            WrongParameterException,
            projects_service.create_project_task_type_link,
            str(self.project.id),
            "not-a-uuid",
            1,
        )

    def test_create_project_task_status_link(self):
        self.generate_fixture_task_status()
        link = projects_service.create_project_task_status_link(
            str(self.project.id), str(self.task_status.id), 1
        )
        self.assertEqual(link["project_id"], str(self.project.id))
        self.assertEqual(link["task_status_id"], str(self.task_status.id))
        # Update existing link
        link2 = projects_service.create_project_task_status_link(
            str(self.project.id), str(self.task_status.id), 3,
            roles_for_board=["admin"],
        )
        self.assertEqual(link2["priority"], 3)

    def test_create_project_task_status_link_invalid(self):
        self.assertRaises(
            WrongParameterException,
            projects_service.create_project_task_status_link,
            str(self.project.id),
            "not-a-uuid",
            1,
        )

    def test_get_project_task_types(self):
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        projects_service.add_task_type_setting(
            self.project.id, self.task_type.id
        )
        task_types = projects_service.get_project_task_types(self.project.id)
        self.assertEqual(len(task_types), 1)

    def test_get_project_task_statuses(self):
        self.generate_fixture_task_status()
        projects_service.add_task_status_setting(
            self.project.id, self.task_status.id
        )
        statuses = projects_service.get_project_task_statuses(self.project.id)
        self.assertEqual(len(statuses), 1)

    def test_add_status_automation_setting(self):
        self.generate_fixture_status_automation_to_status()
        automations = projects_service.get_project_status_automations(
            self.project.id
        )
        self.assertEqual(len(automations), 1)

    def test_remove_status_automation_setting(self):
        self.generate_fixture_status_automation_to_status()
        projects_service.remove_status_automation_setting(
            self.project.id, self.status_automation_to_status.id
        )
        automations = projects_service.get_project_status_automations(
            self.project.id
        )
        self.assertEqual(len(automations), 0)

    def test_add_preview_background_file_setting(self):
        self.generate_fixture_preview_background_file()
        projects_service.add_preview_background_file_setting(
            self.project.id, self.preview_background_file.id
        )
        files = projects_service.get_project_preview_background_files(
            self.project.id
        )
        self.assertEqual(len(files), 1)

    def test_remove_preview_background_file_setting(self):
        self.generate_fixture_preview_background_file()
        projects_service.add_preview_background_file_setting(
            self.project.id, self.preview_background_file.id
        )
        projects_service.remove_preview_background_file_setting(
            self.project.id, self.preview_background_file.id
        )
        files = projects_service.get_project_preview_background_files(
            self.project.id
        )
        self.assertEqual(len(files), 0)

    def test_get_project_fps(self):
        fps = projects_service.get_project_fps(self.project.id)
        self.assertEqual(fps, 25.00)
        projects_service.update_project(self.project.id, {"fps": "30"})
        fps = projects_service.get_project_fps(self.project.id)
        self.assertEqual(fps, 30.00)

    def test_get_task_type_priority_map(self):
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        projects_service.create_project_task_type_link(
            str(self.project.id), str(self.task_type.id), 3
        )
        priority_map = projects_service.get_task_type_priority_map(
            self.project.id
        )
        self.assertIn(str(self.task_type.id), priority_map)
        self.assertEqual(priority_map[str(self.task_type.id)], 3)

    def test_get_task_type_links(self):
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        projects_service.create_project_task_type_link(
            str(self.project.id), str(self.task_type.id), 2
        )
        links = projects_service.get_task_type_links(self.project.id)
        self.assertEqual(len(links), 1)

    def test_get_department_team(self):
        self.generate_fixture_department()
        self.generate_fixture_person()
        projects_service.add_team_member(self.project.id, self.person.id)
        from zou.app.services import persons_service

        persons_service.add_to_department(
            str(self.department.id), str(self.person.id)
        )
        team = projects_service.get_department_team(
            self.project.id, self.department.id
        )
        self.assertEqual(len(team), 1)
