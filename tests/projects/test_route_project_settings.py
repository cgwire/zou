from tests.base import ApiDBTestCase

from zou.app.services import budget_service


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
        self.assertIn(
            str(self.asset_type.id), project.get("asset_types", [])
        )

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
        self.assertIn(
            str(self.task_type.id), project.get("task_types", [])
        )

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
        self.assertNotIn(
            str(self.task_type.id), project.get("task_types", [])
        )

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

    # --- Status automations settings ---

    def test_get_project_status_automations(self):
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/settings/status-automations"
        )
        self.assertIsInstance(result, list)

    def test_add_project_status_automation(self):
        self.generate_fixture_status_automation_to_status()
        result = self.post(
            f"/data/projects/{self.project_id}"
            f"/settings/status-automations",
            {
                "status_automation_id": str(
                    self.status_automation_to_status.id
                )
            },
        )
        self.assertIsNotNone(result.get("id"))
        automations = self.get(
            f"/data/projects/{self.project_id}"
            f"/settings/status-automations"
        )
        automation_ids = [a["id"] for a in automations]
        self.assertIn(
            str(self.status_automation_to_status.id), automation_ids
        )

    def test_delete_project_status_automation(self):
        self.generate_fixture_status_automation_to_status()
        self.post(
            f"/data/projects/{self.project_id}"
            f"/settings/status-automations",
            {
                "status_automation_id": str(
                    self.status_automation_to_status.id
                )
            },
        )
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/settings/status-automations"
            f"/{self.status_automation_to_status.id}"
        )
        automations = self.get(
            f"/data/projects/{self.project_id}"
            f"/settings/status-automations"
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
        self.assertIn(
            str(self.preview_background_file.id), file_ids
        )

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
        self.assertNotIn(
            str(self.preview_background_file.id), file_ids
        )


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
        result = self.get(
            f"/data/projects/{self.project_id}/time-spents"
        )
        self.assertIsInstance(result, list)

    def test_get_project_milestones(self):
        result = self.get(
            f"/data/projects/{self.project_id}/milestones"
        )
        self.assertIsInstance(result, list)

    def test_get_project_day_offs(self):
        result = self.get(
            f"/data/projects/{self.project_id}/day-offs"
        )
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
        result = self.get(
            f"/data/projects/{self.project_id}/budgets"
        )
        self.assertIsInstance(result, list)

    def test_create_project_budget(self):
        result = self._create_budget("Test Budget")
        self.assertEqual(result["name"], "Test Budget")
        fetched = self.get(
            f"/data/projects/{self.project_id}"
            f"/budgets/{result['id']}"
        )
        self.assertEqual(fetched["name"], "Test Budget")

    def test_get_project_budget(self):
        budget = self._create_budget("Get Budget")
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}"
        )
        self.assertEqual(result["name"], "Get Budget")

    def test_update_project_budget(self):
        budget = self._create_budget("Old Name")
        result = self.put(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}",
            {"name": "New Name"},
        )
        self.assertEqual(result["name"], "New Name")
        fetched = self.get(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}"
        )
        self.assertEqual(fetched["name"], "New Name")

    def test_delete_project_budget(self):
        budget = self._create_budget("To Delete")
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}"
        )
        budgets = self.get(
            f"/data/projects/{self.project_id}/budgets"
        )
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
        self.assertEqual(
            entries[0]["department_id"], str(self.department.id)
        )

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
