from tests.base import ApiDBTestCase

from zou.app.utils import fields


class PreviewBackgroundFileTestCase(ApiDBTestCase):
    def setUp(self):
        super(PreviewBackgroundFileTestCase, self).setUp()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status_done()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_preview_background_file("test")
        self.generate_fixture_preview_background_file("test1")
        self.generate_fixture_project_status()
        self.project = self.generate_fixture_project()

    def test_get_preview_background_files(self):
        preview_background_files = self.get("data/preview-background-files")
        self.assertEqual(len(preview_background_files), 2)

    def test_get_preview_background_file(self):
        preview_background_file = self.get_first(
            "data/preview-background-files"
        )
        preview_background_file_again = self.get(
            f"data/preview-background-files/{preview_background_file['id']}"
        )
        self.assertEqual(
            preview_background_file, preview_background_file_again
        )
        self.get_404(f"data/preview-background-files/{fields.gen_uuid()}")

    def test_create_preview_background_file(self):
        data = {
            "name": "test4",
        }
        self.preview_background_file = self.post(
            "data/preview-background-files", data
        )
        self.assertIsNotNone(self.preview_background_file["id"])

        preview_background_files = self.get("data/preview-background-files")
        self.assertEqual(len(preview_background_files), 3)

    def test_update_preview_background_file(self):
        preview_background_file = self.get_first(
            "data/preview-background-files"
        )
        data = {"name": "test4"}
        self.put(
            "data/preview-background-files/%s" % preview_background_file["id"],
            data,
        )
        preview_background_file_again = self.get(
            "data/preview-background-files/%s" % preview_background_file["id"]
        )
        self.assertEqual(
            data["name"],
            preview_background_file_again["name"],
        )
        self.put_404(
            "data/preview-background-files/%s" % fields.gen_uuid(), data
        )

    def test_delete_preview_background_file(self):
        preview_background_files = self.get("data/preview-background-files")
        self.assertEqual(len(preview_background_files), 2)
        preview_background_file = preview_background_files[0]
        self.delete(
            "data/preview-background-files/%s" % preview_background_file["id"]
        )
        preview_background_files = self.get("data/preview-background-files")
        self.assertEqual(len(preview_background_files), 1)
        self.delete_404("data/preview-background-files/%s" % fields.gen_uuid())

    def test_add_preview_background_to_project(self):
        data = {
            "preview_background_file_id": self.preview_background_file.id,
        }
        self.post(
            f"data/projects/{self.project.id}/settings/preview-background-files",
            data,
        )
        project = self.get(f"data/projects/{self.project.id}")
        self.assertIn(
            str(self.preview_background_file.id),
            project["preview_background_files"],
        )
        self.assertEqual(len(project["preview_background_files"]), 1)
        preview_background_file_ids = [
            p["id"]
            for p in self.get(
                f"data/projects/{self.project.id}/settings/preview-background-files"
            )
        ]
        self.assertIn(
            str(self.preview_background_file.id), preview_background_file_ids
        )
        self.assertEqual(len(preview_background_file_ids), 1)

    def test_remove_preview_background_to_project(self):
        data = {
            "preview_background_file_id": self.preview_background_file.id,
        }
        self.post(
            f"data/projects/{self.project.id}/settings/preview-background-files",
            data,
        )
        project = self.get(f"data/projects/{self.project.id}")
        self.assertIn(
            str(self.preview_background_file.id),
            project["preview_background_files"],
        )
        self.assertEqual(len(project["preview_background_files"]), 1)
        self.delete(
            f"data/projects/{self.project.id}/settings/preview-background-files/{self.preview_background_file.id}"
        )
        project = self.get(f"data/projects/{self.project.id}")
        self.assertNotIn(
            str(self.preview_background_file.id),
            project["preview_background_files"],
        )
        self.assertEqual(len(project["preview_background_files"]), 0)
        preview_background_file_ids = [
            p["id"]
            for p in self.get(
                f"data/projects/{self.project.id}/settings/preview-background-files"
            )
        ]
        self.assertNotIn(
            str(self.preview_background_file.id), preview_background_file_ids
        )
        self.assertEqual(len(preview_background_file_ids), 0)
