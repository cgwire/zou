from tests.base import ApiDBTestCase
from zou.app.models.day_off import DayOff
from zou.app.models.milestone import Milestone
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.services import (
    projects_service,
    time_spents_service,
)
from zou.app.utils import events, fields


class ProjectSettingsRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
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

    def test_task_type_link_bitrates(self):
        path = f"/data/projects/{self.project_id}/settings/task-types"
        task_type_id = str(self.task_type.id)
        self.post(path, {"task_type_id": task_type_id, "priority": 3})
        # A second call keeps the priority and sets the bitrates.
        self.post(
            path,
            {
                "task_type_id": task_type_id,
                "hd_bitrate_compression": 20,
                "ld_bitrate_compression": 4,
            },
        )
        # The link maps ride along the project lists, not the single GET.
        project = next(
            project
            for project in self.get("/data/projects/open")
            if project["id"] == self.project_id
        )
        self.assertEqual(
            project["task_type_links"][task_type_id],
            {
                "priority": 3,
                "hd_bitrate_compression": 20,
                "ld_bitrate_compression": 4,
                "is_client_visible": True,
            },
        )
        self.assertEqual(project["task_types_priority"][task_type_id], 3)
        # A call without bitrates leaves them alone.
        self.post(path, {"task_type_id": task_type_id, "priority": 4})
        link = ProjectTaskTypeLink.get_by(
            project_id=self.project_id, task_type_id=task_type_id
        )
        self.assertEqual(link.hd_bitrate_compression, 20)
        self.post(
            path,
            {"task_type_id": task_type_id, "ld_bitrate_compression": 0},
            400,
        )
        # A link low def above the project high def is refused.
        self.put(
            f"/data/projects/{self.project_id}", {"hd_bitrate_compression": 10}
        )
        self.post(
            path,
            {"task_type_id": task_type_id, "ld_bitrate_compression": 12},
            400,
        )
        self.post(
            path,
            {
                "task_type_id": task_type_id,
                "hd_bitrate_compression": 14,
                "ld_bitrate_compression": 12,
            },
        )
        # A link high def below the low def it inherits is fine: the
        # encoder caps that low def.
        self.put(
            f"/data/projects/{self.project_id}", {"ld_bitrate_compression": 6}
        )
        self.post(
            path,
            {
                "task_type_id": task_type_id,
                "hd_bitrate_compression": 4,
                "ld_bitrate_compression": None,
            },
        )
        link = ProjectTaskTypeLink.get_by(
            project_id=self.project_id, task_type_id=task_type_id
        )
        self.assertEqual(
            (link.hd_bitrate_compression, link.ld_bitrate_compression),
            (4, None),
        )

    def _open_project_link(self, task_type_id):
        project = next(
            project
            for project in self.get("/data/projects/open")
            if project["id"] == self.project_id
        )
        return project["task_type_links"][task_type_id]

    def test_set_task_type_client_visibility(self):
        path = f"/data/projects/{self.project_id}/settings/task-types"
        task_type_id = str(self.task_type.id)
        self.post(
            path,
            {
                "task_type_id": task_type_id,
                "priority": 3,
                "hd_bitrate_compression": 20,
            },
        )
        self.post(
            path, {"task_type_id": task_type_id, "is_client_visible": False}
        )
        link = self._open_project_link(task_type_id)
        self.assertIs(link["is_client_visible"], False)
        self.assertEqual(link["priority"], 3)
        self.assertEqual(link["hd_bitrate_compression"], 20)

    def test_task_type_setting_without_visibility_keeps_it(self):
        path = f"/data/projects/{self.project_id}/settings/task-types"
        task_type_id = str(self.task_type.id)
        self.post(path, {"task_type_id": task_type_id, "priority": 3})
        self.assertIs(
            self._open_project_link(task_type_id)["is_client_visible"], True
        )
        self.post(
            path, {"task_type_id": task_type_id, "is_client_visible": False}
        )
        self.post(
            path, {"task_type_id": task_type_id, "hd_bitrate_compression": 20}
        )
        self.assertIs(
            self._open_project_link(task_type_id)["is_client_visible"], False
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
        self.assertNotIn(str(self.task_type.id), project.get("task_types", []))

    # --- Task status settings ---

    def test_get_project_task_statuses(self):
        # Nothing linked yet: the add tests below cover the rest.
        self.assertEqual(
            self.get(f"/data/projects/{self.project_id}/settings/task-status"),
            [],
        )

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

    def _task_status_path(self):
        return (
            f"/data/projects/{self.project_id}"
            f"/settings/task-status/{self.task_status.id}"
        )

    def _open_project_status_link(self):
        project = next(
            project
            for project in self.get("/data/projects/open")
            if project["id"] == self.project_id
        )
        return project["task_statuses_link"][str(self.task_status.id)]

    def test_set_task_status_client_allowed(self):
        self.post(
            f"/data/projects/{self.project_id}/settings/task-status",
            {"task_status_id": str(self.task_status.id)},
        )
        self.assertIsNone(
            self._open_project_status_link()["is_client_allowed"]
        )
        for value in (False, True, None):
            link = self.put(
                self._task_status_path(), {"is_client_allowed": value}
            )
            self.assertIs(link["is_client_allowed"], value)
            self.assertIs(
                self._open_project_status_link()["is_client_allowed"], value
            )

    def test_set_task_status_client_allowed_requires_the_field(self):
        self.post(
            f"/data/projects/{self.project_id}/settings/task-status",
            {"task_status_id": str(self.task_status.id)},
        )
        self.put(self._task_status_path(), {}, 400)

    def test_set_client_allowed_of_an_unlinked_task_status(self):
        self.put(self._task_status_path(), {"is_client_allowed": False}, 404)

    def test_set_task_status_client_allowed_as_artist_is_forbidden(self):
        self.post(
            f"/data/projects/{self.project_id}/settings/task-status",
            {"task_status_id": str(self.task_status.id)},
        )
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        self.log_in_cg_artist()
        self.put(self._task_status_path(), {"is_client_allowed": False}, 403)

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

    def test_project_settings_batch_applies_client_visibility(self):
        path = f"/data/projects/{self.project_id}/settings/batch"
        type_id = str(self.task_type.id)

        def visible():
            return ProjectTaskTypeLink.get_by(
                project_id=self.project_id, task_type_id=type_id
            ).is_client_visible

        self.post(
            path,
            {
                "task_types": [
                    {"task_type_id": type_id, "is_client_visible": False}
                ]
            },
            200,
        )
        self.assertFalse(visible())
        self.post(path, {"task_types": [{"task_type_id": type_id}]}, 200)
        self.assertFalse(visible())
        self.post(
            path,
            {
                "task_types": [
                    {"task_type_id": type_id, "is_client_visible": True}
                ]
            },
            200,
        )
        self.assertTrue(visible())

    def test_set_client_allowed_with_malformed_status_id(self):
        self.put(
            f"/data/projects/{self.project_id}/settings/task-status/nope",
            {"is_client_allowed": False},
            404,
        )

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
        # Nothing linked yet: the add tests below cover the rest.
        self.assertEqual(
            self.get(
                f"/data/projects/{self.project_id}"
                f"/settings/status-automations"
            ),
            [],
        )

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
        # Nothing linked yet: the add tests below cover the rest.
        self.assertEqual(
            self.get(
                f"/data/projects/{self.project_id}"
                f"/settings/preview-background-files"
            ),
            [],
        )

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
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task()
        self.project_id = str(self.project.id)

    def test_get_project_time_spents(self):
        """
        Every time spent logged on the production, whoever logged it.
        """
        self.assertEqual(
            self.get(f"/data/projects/{self.project_id}/time-spents"), []
        )
        time_spents_service.create_or_update_time_spent(
            str(self.task.id), str(self.person.id), "2024-06-12", 120
        )

        result = self.get(f"/data/projects/{self.project_id}/time-spents")

        self.assertEqual(
            [(spent["duration"], spent["date"]) for spent in result],
            [(120, "2024-06-12")],
        )

    def test_get_project_milestones(self):
        self.assertEqual(
            self.get(f"/data/projects/{self.project_id}/milestones"), []
        )
        milestone = Milestone.create(
            date=fields.get_date_object("2024-06-12"),
            name="Delivery",
            project_id=self.project.id,
            task_type_id=self.task_type.id,
        )

        result = self.get(f"/data/projects/{self.project_id}/milestones")

        self.assertEqual(
            [entry["id"] for entry in result], [str(milestone.id)]
        )

    def test_get_project_day_offs(self):
        """
        The leave of the production's team, keyed by person. Someone off the
        team is not the production's business.
        """
        projects_service.add_team_member(self.project_id, str(self.person.id))
        DayOff.create(
            date="2024-06-12",
            end_date="2024-06-12",
            person_id=self.person.id,
        )
        outsider = self.generate_fixture_user_cg_artist()
        DayOff.create(
            date="2024-06-12",
            end_date="2024-06-12",
            person_id=outsider["id"],
        )

        result = self.get(f"/data/projects/{self.project_id}/day-offs")

        self.assertEqual(list(result.keys()), [str(self.person.id)])
        self.assertEqual(len(result[str(self.person.id)]), 1)

    def test_get_project_task_type_time_spents(self):
        """
        The same time spents narrowed to one task type and grouped per
        person.
        """
        here = self.task
        for date, duration in [("2024-06-12", 120), ("2024-06-13", 300)]:
            time_spents_service.create_or_update_time_spent(
                str(here.id), str(self.person.id), date, duration
            )

        # The same person on the same asset, under another task type: the
        # narrowing is what has to keep this out.
        elsewhere = self.generate_fixture_task(
            name="Animation", task_type_id=self.task_type_animation.id
        )
        time_spents_service.create_or_update_time_spent(
            str(elsewhere.id), str(self.person.id), "2024-06-12", 999
        )
        self.task = here

        result = self.get(
            f"/data/projects/{self.project_id}"
            f"/task-types/{self.task_type.id}/time-spents"
        )

        self.assertEqual(list(result.keys()), [str(self.person.id)])
        self.assertEqual(
            sorted(
                (spent["date"], spent["duration"])
                for spent in result[str(self.person.id)]
            ),
            [("2024-06-12", 120), ("2024-06-13", 300)],
        )


class ProjectBudgetRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.project_id = str(self.project.id)

    def _create_budget(self, name="Test Budget"):
        return self.post(
            f"/data/projects/{self.project_id}/budgets",
            {"name": name},
            200,
        )

    def test_get_project_budgets(self):
        self.assertEqual(
            self.get(f"/data/projects/{self.project_id}/budgets"), []
        )
        budget = self._create_budget("Test Budget")

        result = self.get(f"/data/projects/{self.project_id}/budgets")

        self.assertEqual([entry["id"] for entry in result], [budget["id"]])

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
        self.assertEqual(budgets, [])

    def test_budget_entries(self):
        # A fresh budget has no lines yet: creating and removing them is the
        # business of the tests below.
        budget = self._create_budget("Entries Budget")
        self.assertEqual(
            self.get(
                f"/data/projects/{self.project_id}"
                f"/budgets/{budget['id']}/entries"
            ),
            [],
        )

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

    def test_a_budget_answers_only_under_its_project_and_budget(self):
        self.generate_fixture_department()
        budget = self._create_budget()
        entry_data = {
            "department_id": str(self.department.id),
            "start_date": "2024-01-01",
            "months_duration": 6,
            "daily_salary": 500,
        }
        path = f"/data/projects/{self.project_id}/budgets/{budget['id']}"
        entry = self.post(f"{path}/entries", entry_data, 200)

        other_budget = self._create_budget("Other")
        wrong_budget = (
            f"/data/projects/{self.project_id}/budgets/{other_budget['id']}"
        )
        self.get(f"{wrong_budget}/entries/{entry['id']}", 404)
        self.put(f"{wrong_budget}/entries/{entry['id']}", entry_data, 404)
        self.delete(f"{wrong_budget}/entries/{entry['id']}", 404)

        other_project_id = self.generate_fixture_project("Other").id
        wrong_project = (
            f"/data/projects/{other_project_id}/budgets/{budget['id']}"
        )
        self.get(wrong_project, 404)
        self.put(wrong_project, {"name": "Taken"}, 404)
        self.delete(wrong_project, 404)
        self.get(f"{wrong_project}/entries", 404)
        self.post(f"{wrong_project}/entries", entry_data, 404)

        self.assertEqual(self.get(path)["name"], "Test Budget")
        self.assertEqual(len(self.get(f"{path}/entries")), 1)

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
        self.assertEqual(entries, [])

    def test_get_budgets_time_spents(self):
        result = self.get(
            f"/data/projects/{self.project_id}/budgets/time-spents"
        )
        self.assertIsInstance(result, dict)


class ProjectSettingsEventsTestCase(ApiDBTestCase):
    """
    Linking a task type or a task status to a project, and reordering either
    list, change what the clients read through the project. They each emit
    project:update so the clients refetch it.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.project_id = str(self.project.id)
        self.events = []
        events.register("project:update", "handle_event", self)

    def handle_event(self, data={}):
        self.events.append(data)

    def test_task_type_link_notifies(self):
        self.post(
            "/data/task-type-links",
            {
                "project_id": self.project_id,
                "task_type_id": str(self.task_type.id),
                "priority": 1,
            },
        )
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["project_id"], self.project_id)

    def test_task_status_link_notifies(self):
        self.post(
            "/data/task-status-links",
            {
                "project_id": self.project_id,
                "task_status_id": str(self.task_status.id),
                "priority": 1,
            },
        )
        self.assertEqual(len(self.events), 1)
        self.assertEqual(self.events[0]["project_id"], self.project_id)

    def test_reorder_notifies_once(self):
        """
        A reorder touches every link of the list but the clients only need to
        refetch the project once.
        """
        first = str(self.task_type.id)
        second = str(self.task_type_concept.id)
        projects_service.create_project_task_type_link(
            self.project_id, first, 1
        )
        projects_service.create_project_task_type_link(
            self.project_id, second, 2
        )
        self.events.clear()

        self.post(
            f"/actions/projects/{self.project_id}/task-type-links/reorder",
            {"task_type_ids": [second, first]},
            200,
        )
        self.assertEqual(len(self.events), 1)
