from tests.base import ApiDBTestCase

from zou.app.models.project import ProjectTaskTypeLink
from zou.app.services import budget_service
from zou.app.utils import fields


class ProjectSettingsRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(ProjectSettingsRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.project_id = str(self.project.id)

    # --- Asset type settings ---

    def test_add_project_asset_type(self):
        result = self.post(
            f"/data/projects/{self.project_id}/settings/asset-types",
            {"asset_type_id": str(self.asset_type.id)},
        )
        self.assertIsNotNone(result.get("id"))
        project = self.get(f"/data/projects/{self.project_id}")
        self.assertIn(str(self.asset_type.id), project.get("asset_types", []))

    def test_delete_project_asset_type(self):
        self.post(
            f"/data/projects/{self.project_id}/settings/asset-types",
            {"asset_type_id": str(self.asset_type.id)},
        )
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/settings/asset-types/{self.asset_type.id}"
        )
        project = self.get(f"/data/projects/{self.project_id}")
        self.assertNotIn(
            str(self.asset_type.id), project.get("asset_types", [])
        )

    # --- Task type settings ---

    def test_add_project_task_type(self):
        result = self.post(
            f"/data/projects/{self.project_id}/settings/task-types",
            {"task_type_id": str(self.task_type.id)},
        )
        self.assertIsNotNone(result.get("id"))
        project = self.get(f"/data/projects/{self.project_id}")
        self.assertIn(str(self.task_type.id), project.get("task_types", []))

    def test_delete_project_task_type(self):
        self.post(
            f"/data/projects/{self.project_id}/settings/task-types",
            {"task_type_id": str(self.task_type.id)},
        )
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/settings/task-types/{self.task_type.id}"
        )
        project = self.get(f"/data/projects/{self.project_id}")
        self.assertNotIn(str(self.task_type.id), project.get("task_types", []))

    # --- Task status settings ---

    def test_get_project_task_statuses(self):
        result = self.get(
            f"/data/projects/{self.project_id}/settings/task-status"
        )
        self.assertIsInstance(result, list)

    def test_add_project_task_status(self):
        result = self.post(
            f"/data/projects/{self.project_id}/settings/task-status",
            {"task_status_id": str(self.task_status.id)},
        )
        self.assertIsNotNone(result.get("id"))
        statuses = self.get(
            f"/data/projects/{self.project_id}/settings/task-status"
        )
        status_ids = [s["id"] for s in statuses]
        self.assertIn(str(self.task_status.id), status_ids)

    def test_delete_project_task_status(self):
        self.post(
            f"/data/projects/{self.project_id}/settings/task-status",
            {"task_status_id": str(self.task_status.id)},
        )
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/settings/task-status/{self.task_status.id}"
        )
        statuses = self.get(
            f"/data/projects/{self.project_id}/settings/task-status"
        )
        status_ids = [s["id"] for s in statuses]
        self.assertNotIn(str(self.task_status.id), status_ids)

    # --- Batch settings ---

    def test_add_project_settings_batch(self):
        result = self.post(
            f"/data/projects/{self.project_id}/settings/batch",
            {
                "task_types": [
                    {"task_type_id": str(self.task_type.id), "priority": 1},
                    {
                        "task_type_id": str(self.task_type_modeling.id),
                        "priority": 2,
                    },
                ],
                "task_status_ids": [str(self.task_status.id)],
                "asset_type_ids": [str(self.asset_type.id)],
            },
            200,
        )
        self.assertIsNotNone(result.get("id"))
        project = self.get(f"/data/projects/{self.project_id}")
        self.assertIn(str(self.task_type.id), project["task_types"])
        self.assertIn(str(self.task_type_modeling.id), project["task_types"])
        self.assertIn(str(self.asset_type.id), project["asset_types"])
        statuses = self.get(
            f"/data/projects/{self.project_id}/settings/task-status"
        )
        self.assertIn(str(self.task_status.id), [s["id"] for s in statuses])
        link = ProjectTaskTypeLink.get_by(
            project_id=self.project_id, task_type_id=str(self.task_type.id)
        )
        self.assertEqual(link.priority, 1)

    def test_project_settings_batch_is_idempotent(self):
        data = {
            "task_types": [{"task_type_id": str(self.task_type.id)}],
            "task_status_ids": [
                str(self.task_status.id),
                str(self.task_status.id),
            ],
            "asset_type_ids": [str(self.asset_type.id)],
        }
        self.post(
            f"/data/projects/{self.project_id}/settings/batch", data, 200
        )
        self.post(
            f"/data/projects/{self.project_id}/settings/batch", data, 200
        )
        project = self.get(f"/data/projects/{self.project_id}")
        self.assertEqual(
            project["task_types"].count(str(self.task_type.id)), 1
        )
        self.assertEqual(
            project["asset_types"].count(str(self.asset_type.id)), 1
        )
        statuses = self.get(
            f"/data/projects/{self.project_id}/settings/task-status"
        )
        status_ids = [s["id"] for s in statuses]
        self.assertEqual(status_ids.count(str(self.task_status.id)), 1)

    def test_project_settings_batch_replace_task_types(self):
        self.post(
            f"/data/projects/{self.project_id}/settings/batch",
            {
                "task_types": [
                    {"task_type_id": str(self.task_type.id), "priority": 1},
                    {
                        "task_type_id": str(self.task_type_concept.id),
                        "priority": 2,
                    },
                ]
            },
            200,
        )
        self.post(
            f"/data/projects/{self.project_id}/settings/batch",
            {
                "task_types": [
                    {"task_type_id": str(self.task_type.id), "priority": 2},
                    {
                        "task_type_id": str(self.task_type_modeling.id),
                        "priority": 1,
                    },
                ],
                "replace_task_types": True,
            },
            200,
        )
        project = self.get(f"/data/projects/{self.project_id}")
        self.assertIn(str(self.task_type.id), project["task_types"])
        self.assertIn(str(self.task_type_modeling.id), project["task_types"])
        self.assertNotIn(str(self.task_type_concept.id), project["task_types"])
        link = ProjectTaskTypeLink.get_by(
            project_id=self.project_id, task_type_id=str(self.task_type.id)
        )
        self.assertEqual(link.priority, 2)

    def test_project_settings_batch_skips_unknown_ids(self):
        self.post(
            f"/data/projects/{self.project_id}/settings/batch",
            {
                "task_types": [{"task_type_id": fields.gen_uuid()}],
                "task_status_ids": [fields.gen_uuid()],
                "asset_type_ids": [fields.gen_uuid()],
            },
            200,
        )
        project = self.get(f"/data/projects/{self.project_id}")
        self.assertEqual(project["task_types"], [])
        self.assertEqual(project["asset_types"], [])

    def test_project_settings_batch_as_artist_is_forbidden(self):
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.post(
            f"/data/projects/{self.project_id}/settings/batch",
            {"task_types": [{"task_type_id": str(self.task_type.id)}]},
            403,
        )

    # --- Status automations settings ---

    def test_get_project_status_automations(self):
        result = self.get(
            f"/data/projects/{self.project_id}" f"/settings/status-automations"
        )
        self.assertIsInstance(result, list)

    def test_add_project_status_automation(self):
        self.generate_fixture_status_automation_to_status()
        result = self.post(
            f"/data/projects/{self.project_id}"
            f"/settings/status-automations",
            {"status_automation_id": str(self.status_automation_to_status.id)},
        )
        self.assertIsNotNone(result.get("id"))
        automations = self.get(
            f"/data/projects/{self.project_id}" f"/settings/status-automations"
        )
        automation_ids = [a["id"] for a in automations]
        self.assertIn(str(self.status_automation_to_status.id), automation_ids)

    def test_delete_project_status_automation(self):
        self.generate_fixture_status_automation_to_status()
        self.post(
            f"/data/projects/{self.project_id}"
            f"/settings/status-automations",
            {"status_automation_id": str(self.status_automation_to_status.id)},
        )
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/settings/status-automations"
            f"/{self.status_automation_to_status.id}"
        )
        automations = self.get(
            f"/data/projects/{self.project_id}" f"/settings/status-automations"
        )
        automation_ids = [a["id"] for a in automations]
        self.assertNotIn(
            str(self.status_automation_to_status.id), automation_ids
        )

    # --- Preview background file settings ---

    def test_get_project_preview_background_files(self):
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/settings/preview-background-files"
        )
        self.assertIsInstance(result, list)

    def test_add_project_preview_background_file(self):
        self.generate_fixture_preview_background_file()
        result = self.post(
            f"/data/projects/{self.project_id}"
            f"/settings/preview-background-files",
            {
                "preview_background_file_id": str(
                    self.preview_background_file.id
                )
            },
        )
        self.assertIsNotNone(result.get("id"))
        files = self.get(
            f"/data/projects/{self.project_id}"
            f"/settings/preview-background-files"
        )
        file_ids = [f["id"] for f in files]
        self.assertIn(str(self.preview_background_file.id), file_ids)

    def test_delete_project_preview_background_file(self):
        self.generate_fixture_preview_background_file()
        self.post(
            f"/data/projects/{self.project_id}"
            f"/settings/preview-background-files",
            {
                "preview_background_file_id": str(
                    self.preview_background_file.id
                )
            },
        )
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/settings/preview-background-files"
            f"/{self.preview_background_file.id}"
        )
        files = self.get(
            f"/data/projects/{self.project_id}"
            f"/settings/preview-background-files"
        )
        file_ids = [f["id"] for f in files]
        self.assertNotIn(str(self.preview_background_file.id), file_ids)


class ProjectDataRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(ProjectDataRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task()
        self.project_id = str(self.project.id)

    def test_get_project_time_spents(self):
        result = self.get(f"/data/projects/{self.project_id}/time-spents")
        self.assertIsInstance(result, list)

    def test_get_project_milestones(self):
        result = self.get(f"/data/projects/{self.project_id}/milestones")
        self.assertIsInstance(result, list)

    def test_get_project_day_offs(self):
        result = self.get(f"/data/projects/{self.project_id}/day-offs")
        self.assertIsInstance(result, dict)

    def test_get_project_task_type_time_spents(self):
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/task-types/{self.task_type.id}/time-spents"
        )
        self.assertIsInstance(result, dict)


class ProjectBudgetRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(ProjectBudgetRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.project_id = str(self.project.id)

    def _create_budget(self, name="Test Budget"):
        return self.post(
            f"/data/projects/{self.project_id}/budgets",
            {"name": name},
            200,
        )

    def test_get_project_budgets(self):
        result = self.get(f"/data/projects/{self.project_id}/budgets")
        self.assertIsInstance(result, list)

    def test_create_project_budget(self):
        result = self._create_budget("Test Budget")
        self.assertEqual(result["name"], "Test Budget")
        fetched = self.get(
            f"/data/projects/{self.project_id}" f"/budgets/{result['id']}"
        )
        self.assertEqual(fetched["name"], "Test Budget")

    def test_get_project_budget(self):
        budget = self._create_budget("Get Budget")
        result = self.get(
            f"/data/projects/{self.project_id}" f"/budgets/{budget['id']}"
        )
        self.assertEqual(result["name"], "Get Budget")

    def test_update_project_budget(self):
        budget = self._create_budget("Old Name")
        result = self.put(
            f"/data/projects/{self.project_id}" f"/budgets/{budget['id']}",
            {"name": "New Name"},
        )
        self.assertEqual(result["name"], "New Name")
        fetched = self.get(
            f"/data/projects/{self.project_id}" f"/budgets/{budget['id']}"
        )
        self.assertEqual(fetched["name"], "New Name")

    def test_delete_project_budget(self):
        budget = self._create_budget("To Delete")
        self.delete(
            f"/data/projects/{self.project_id}" f"/budgets/{budget['id']}"
        )
        budgets = self.get(f"/data/projects/{self.project_id}/budgets")
        self.assertEqual(len(budgets), 0)

    def test_budget_entries(self):
        budget = self._create_budget("Entries Budget")
        entries = self.get(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries"
        )
        self.assertIsInstance(entries, list)

    def test_create_budget_entry(self):
        self.generate_fixture_department()
        budget = self._create_budget("Entry Budget")
        entry = self.post(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries",
            {
                "department_id": str(self.department.id),
                "start_date": "2024-01-01",
                "months_duration": 6,
                "daily_salary": 500,
            },
            200,
        )
        self.assertIsNotNone(entry.get("id"))
        entries = self.get(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries"
        )
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["department_id"], str(self.department.id))

    def test_update_budget_entry(self):
        self.generate_fixture_department()
        self.generate_fixture_person()
        budget = self._create_budget("Update Entry Budget")
        entry = self.post(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries",
            {
                "department_id": str(self.department.id),
                "start_date": "2024-01-01",
                "months_duration": 6,
                "daily_salary": 500,
            },
            200,
        )
        result = self.put(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries/{entry['id']}",
            {
                "department_id": str(self.department.id),
                "start_date": "2024-01-01",
                "months_duration": 6,
                "daily_salary": 700,
            },
        )
        self.assertEqual(result["daily_salary"], 700)
        fetched = self.get(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries"
        )
        self.assertEqual(fetched[0]["daily_salary"], 700)

    def test_delete_budget_entry(self):
        self.generate_fixture_department()
        budget = self._create_budget("Delete Entry Budget")
        entry = self.post(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries",
            {
                "department_id": str(self.department.id),
                "start_date": "2024-01-01",
                "months_duration": 6,
                "daily_salary": 500,
            },
            200,
        )
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries/{entry['id']}"
        )
        entries = self.get(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries"
        )
        self.assertEqual(len(entries), 0)

    def test_get_budgets_time_spents(self):
        result = self.get(
            f"/data/projects/{self.project_id}/budgets/time-spents"
        )
        self.assertIsInstance(result, dict)
