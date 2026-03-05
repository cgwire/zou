from tests.base import ApiDBTestCase

from zou.app.services import budget_service, schedule_service


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

    def test_get_project_asset_types(self):
        result = self.get(
            f"/data/projects/{self.project_id}/settings/asset-types"
        )
        self.assertIsInstance(result, list)

    def test_add_project_asset_type(self):
        result = self.post(
            f"/data/projects/{self.project_id}/settings/asset-types",
            {"asset_type_id": str(self.asset_type.id)},
        )
        self.assertIsNotNone(result.get("id"))

    def test_delete_project_asset_type(self):
        self.post(
            f"/data/projects/{self.project_id}/settings/asset-types",
            {"asset_type_id": str(self.asset_type.id)},
        )
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/settings/asset-types/{self.asset_type.id}"
        )

    # --- Task type settings ---

    def test_get_project_task_types(self):
        result = self.get(
            f"/data/projects/{self.project_id}/settings/task-types"
        )
        self.assertIsInstance(result, list)

    def test_add_project_task_type(self):
        result = self.post(
            f"/data/projects/{self.project_id}/settings/task-types",
            {"task_type_id": str(self.task_type.id)},
        )
        self.assertIsNotNone(result.get("id"))

    def test_delete_project_task_type(self):
        self.post(
            f"/data/projects/{self.project_id}/settings/task-types",
            {"task_type_id": str(self.task_type.id)},
        )
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/settings/task-types/{self.task_type.id}"
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

    def test_delete_project_task_status(self):
        self.post(
            f"/data/projects/{self.project_id}/settings/task-status",
            {"task_status_id": str(self.task_status.id)},
        )
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/settings/task-status/{self.task_status.id}"
        )

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
        self.assertIsInstance(result, list)

    def test_get_project_task_type_time_spents(self):
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/task-types/{self.task_type.id}/time-spents"
        )
        self.assertIsInstance(result, list)


class ProjectBudgetRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(ProjectBudgetRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.project_id = str(self.project.id)

    def test_get_project_budgets(self):
        result = self.get(
            f"/data/projects/{self.project_id}/budgets"
        )
        self.assertIsInstance(result, list)

    def test_create_project_budget(self):
        result = self.post(
            f"/data/projects/{self.project_id}/budgets",
            {"name": "Test Budget"},
        )
        self.assertEqual(result["name"], "Test Budget")

    def test_get_project_budget(self):
        budget = self.post(
            f"/data/projects/{self.project_id}/budgets",
            {"name": "Get Budget"},
        )
        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}"
        )
        self.assertEqual(result["name"], "Get Budget")

    def test_update_project_budget(self):
        budget = self.post(
            f"/data/projects/{self.project_id}/budgets",
            {"name": "Old Name"},
        )
        result = self.put(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}",
            {"name": "New Name"},
        )
        self.assertEqual(result["name"], "New Name")

    def test_delete_project_budget(self):
        budget = self.post(
            f"/data/projects/{self.project_id}/budgets",
            {"name": "To Delete"},
        )
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}"
        )
        budgets = self.get(
            f"/data/projects/{self.project_id}/budgets"
        )
        self.assertEqual(len(budgets), 0)

    def test_budget_entries(self):
        budget = self.post(
            f"/data/projects/{self.project_id}/budgets",
            {"name": "Entries Budget"},
        )
        entries = self.get(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries"
        )
        self.assertIsInstance(entries, list)

    def test_create_budget_entry(self):
        budget = self.post(
            f"/data/projects/{self.project_id}/budgets",
            {"name": "Entry Budget"},
        )
        entry = self.post(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries",
            {"name": "VFX", "amount": 1000},
        )
        self.assertEqual(entry["name"], "VFX")

    def test_update_budget_entry(self):
        budget = self.post(
            f"/data/projects/{self.project_id}/budgets",
            {"name": "Update Entry Budget"},
        )
        entry = self.post(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries",
            {"name": "VFX", "amount": 1000},
        )
        result = self.put(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries/{entry['id']}",
            {"name": "SFX"},
        )
        self.assertEqual(result["name"], "SFX")

    def test_delete_budget_entry(self):
        budget = self.post(
            f"/data/projects/{self.project_id}/budgets",
            {"name": "Delete Entry Budget"},
        )
        entry = self.post(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries",
            {"name": "VFX", "amount": 1000},
        )
        self.delete(
            f"/data/projects/{self.project_id}"
            f"/budgets/{budget['id']}/entries/{entry['id']}"
        )

    def test_get_budgets_time_spents(self):
        result = self.get(
            f"/data/projects/{self.project_id}/budgets/time-spents"
        )
        self.assertIsInstance(result, list)


class ProductionScheduleVersionRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(ProductionScheduleVersionRoutesTestCase, self).setUp()
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

    def _create_schedule_version(self):
        from zou.app.models.production_schedule_version import (
            ProductionScheduleVersion,
        )

        self.schedule_version = ProductionScheduleVersion.create(
            name="Version 1",
            project_id=self.project.id,
        )
        return self.schedule_version

    def test_get_schedule_version_task_links(self):
        version = self._create_schedule_version()
        result = self.get(
            f"/data/production-schedule-versions"
            f"/{version.id}/task-links"
        )
        self.assertIsInstance(result, list)

    def test_create_schedule_version_task_links(self):
        version = self._create_schedule_version()
        result = self.post(
            f"/data/production-schedule-versions"
            f"/{version.id}/task-links",
            {},
            200,
        )
        self.assertIsInstance(result, list)
