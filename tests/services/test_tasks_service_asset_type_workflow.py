from tests.base import ApiDBTestCase
from zou.app.exceptions import WrongParameterException
from zou.app.services import projects_service, tasks_service


class AssetTypeWorkflowTaskCreationTestCase(ApiDBTestCase):
    """
    The task types tasks_service.create_tasks_for_entity creates for an
    asset, with and without a project workflow for its asset type.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.project_id = str(self.project.id)
        self.asset_type_id = str(self.asset_type.id)
        self.shaders_id = str(self.task_type.id)
        self.concept_id = str(self.task_type_concept.id)
        for task_type_id in [self.shaders_id, self.concept_id]:
            projects_service.add_task_type_setting(
                self.project_id, task_type_id
            )
        projects_service.add_asset_type_setting(
            self.project_id, self.asset_type_id
        )

    def set_workflow(self, task_type_ids):
        projects_service.set_asset_type_workflow(
            self.project_id, self.asset_type_id, task_type_ids
        )

    def created_task_type_ids(self):
        asset = self.asset.serialize(obj_type="Asset")
        return {
            task["task_type_id"]
            for task in tasks_service.create_tasks_for_entity(asset)
        }

    def test_project_workflow_replaces_studio_workflow(self):
        self.asset_type.update({"task_types": [self.concept_id]})
        self.set_workflow([self.shaders_id])
        self.assertEqual(self.created_task_type_ids(), {self.shaders_id})

    def test_studio_workflow_applies_without_project_workflow(self):
        self.asset_type.update({"task_types": [self.concept_id]})
        self.assertEqual(self.created_task_type_ids(), {self.concept_id})

    def test_explicit_task_type_outside_project_workflow_is_refused(self):
        self.set_workflow([self.shaders_id])
        asset = self.asset.serialize(obj_type="Asset")
        with self.assertRaises(WrongParameterException):
            tasks_service.create_tasks_for_entity(
                asset, [self.task_type_concept.serialize()]
            )
