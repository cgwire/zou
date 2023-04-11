from tests.base import ApiDBTestCase

from zou.app.utils import fields
from zou.app.models.task import Task
from zou.app.services import (
    tasks_service,
    projects_service,
)


class PreviewFileTestCase(ApiDBTestCase):
    def setUp(self):
        super(PreviewFileTestCase, self).setUp()

        self.generate_fixture_user_cg_artist()
        self.user_cg_artist_id = self.user_cg_artist["id"]
        self.generate_fixture_user_vendor()
        self.user_vendor_id = self.user_vendor["id"]

        self.generate_fixture_person()
        self.generate_fixture_assigner()

        # Create first project
        self.generate_fixture_project_status()
        self.project1 = self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

        # Create a task with one preview file
        self.task1_1 = self.generate_fixture_task(name="PROJ1_TASK1")
        self.generate_fixture_file_status()
        self.generate_fixture_output_type()
        self.generate_fixture_output_file()
        self.preview_file1_1 = self.generate_fixture_preview_file(
            name="PROJ1_TASK1_PF1"
        )

        # Create a task with one preview file
        self.task1_2 = self.generate_fixture_task(name="PROJ1_TASK2")
        self.generate_fixture_preview_file(name="PROJ1_TASK2_PF1")

        # Create second project
        self.generate_fixture_project_closed_status()
        self.project2 = self.generate_fixture_project("test")
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()

        # Create a task with one preview file
        self.task2_1 = self.generate_fixture_task(name="PROJ2_TASK1")
        self.preview_file2_1 = self.generate_fixture_preview_file(
            name="PROJ2_TASK1_PF1"
        )

        # Create a task with three preview files
        self.task2_2 = self.generate_fixture_task(name="PROJ2_TASK2")
        self.preview_file2_2 = self.generate_fixture_preview_file(
            name="PROJ2_TASK2_PF1"
        )
        self.generate_fixture_preview_file(name="PROJ2_TASK2_PF2")
        self.generate_fixture_preview_file(name="PROJ2_TASK2_PF3")

        # Assign task 1 from project 1 to artist
        projects_service.add_team_member(
            self.project1.id, self.user_cg_artist_id
        )
        tasks_service.assign_task(self.task1_1.id, self.user_cg_artist_id)

        # Assign task 2 from project 2 to vendor
        projects_service.add_team_member(self.project2.id, self.user_vendor_id)
        tasks_service.assign_task(self.task2_2.id, self.user_vendor_id)

    def test_get_preview_files(self):
        preview_files = self.get("data/preview-files")
        self.assertEqual(len(preview_files), 6)

    def test_get_preview_files_for_artist(self):
        """
        Test route data/preview-files for artist.
        Artists can only access previews linked to projects he works on.
        """
        route = "data/preview-files"
        project1_id = str(self.project1.id)

        self.log_in_cg_artist()
        preview_files_artist = self.get(route)
        for preview_file in preview_files_artist:
            task = tasks_service.get_task(preview_file["task_id"])
            self.assertEqual(task["project_id"], project1_id)
        self.assertEqual(len(preview_files_artist), 2)

    def test_get_preview_files_for_vendor(self):
        """
        Test route data/preview-files for vendor.
        The vendor can only access the tasks he's working on.
        """
        route = "data/preview-files"

        self.log_in_vendor()
        preview_files_vendor = self.get(route)
        for preview_file in preview_files_vendor:
            # tasks_service.get_task doesn't contain assignees, thus we use
            # Task class
            task = Task.get(preview_file["task_id"])
            assignees_ids = [str(assignee.id) for assignee in task.assignees]
            self.assertIn(self.user_vendor_id, assignees_ids)
        self.assertEqual(len(preview_files_vendor), 3)

    def test_get_preview_file(self):
        preview_file = self.get_first("data/preview-files?relations=true")
        preview_file_again = self.get(
            "data/preview-files/%s" % preview_file["id"]
        )
        self.assertEqual(preview_file, preview_file_again)
        self.get_404("data/preview-files/%s" % fields.gen_uuid())

    def test_get_preview_file_for_artist(self):
        """
        Test route data/preview-files/<preview_file_id> for artist.
        Artists can only access previews linked to projects he works on.
        """
        route1_1 = "data/preview-files/%s" % str(self.preview_file1_1.id)
        route2_1 = "data/preview-files/%s" % str(self.preview_file2_1.id)
        project1_id = str(self.project1.id)

        self.log_in_cg_artist()
        preview_file_artist1_1 = self.get(route1_1)
        task_related = tasks_service.get_task(
            preview_file_artist1_1["task_id"]
        )
        self.assertEqual(task_related["project_id"], project1_id)
        self.get(route2_1, code=403)

    def test_get_preview_file_for_vendor(self):
        """
        Test route data/preview-files/<preview_file_id> for vendor.
        The vendor can only access the tasks he's working on.
        """
        route2_1 = "data/preview-files/%s" % str(self.preview_file2_1.id)
        route2_2 = "data/preview-files/%s" % str(self.preview_file2_2.id)

        self.log_in_vendor()
        preview_file_vendor = self.get(route2_2)
        # tasks_service.get_task doesn't contain assignees, thus we use Task
        # class
        task = Task.get(preview_file_vendor["task_id"])
        assignees_ids = [str(assignee.id) for assignee in task.assignees]
        self.assertIn(self.user_vendor_id, assignees_ids)
        self.get(route2_1, code=403)

    def test_get_preview_file_for_admin(self):
        """
        Test route data/preview-files/<preview_file_id> for admin.
        """
        route1_1 = "data/preview-files/%s" % str(self.preview_file1_1.id)
        route2_1 = "data/preview-files/%s" % str(self.preview_file2_1.id)
        route2_2 = "data/preview-files/%s" % str(self.preview_file2_2.id)

        self.log_in_admin()
        preview_file_admin1_1 = self.get(route1_1)
        preview_file_admin2_1 = self.get(route2_1)
        preview_file_admin2_2 = self.get(route2_2)
        self.assertTrue(preview_file_admin1_1)
        self.assertTrue(preview_file_admin2_1)
        self.assertTrue(preview_file_admin2_2)

    def test_create_preview_file(self):
        data = {
            "name": "Modeling preview_file 1",
            "person_id": self.person.id,
            "task_id": self.task.id,
            "source_file_id": self.output_file.id,
        }
        self.file_status_id = self.file_status.id
        self.preview_file = self.post("data/preview-files", data)
        self.assertIsNotNone(self.preview_file["id"])

        preview_files = self.get("data/preview-files")
        self.assertEqual(len(preview_files), 7)

    def test_update_preview_file(self):
        preview_file = self.get_first("data/preview-files")
        data = {"name": "Super modeling preview_file 2"}
        self.put("data/preview-files/%s" % preview_file["id"], data)
        preview_file_again = self.get(
            "data/preview-files/%s" % preview_file["id"]
        )
        self.assertEqual(data["name"], preview_file_again["name"])
        self.put_404("data/preview-files/%s" % fields.gen_uuid(), data)

    def test_delete_preview_file(self):
        preview_files = self.get("data/preview-files")
        self.assertEqual(len(preview_files), 6)
        preview_file = preview_files[0]
        self.delete("data/preview-files/%s" % preview_file["id"])
        preview_files = self.get("data/preview-files")
        self.assertEqual(len(preview_files), 5)
        self.delete_404("data/preview-files/%s" % fields.gen_uuid())
