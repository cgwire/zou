from tests.base import ApiDBTestCase


class FileRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(FileRoutesTestCase, self).setUp()
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
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()

    def test_get_working_file(self):
        self.generate_fixture_working_file()
        result = self.get(
            f"/data/files/{self.working_file.id}"
        )
        self.assertEqual(result["id"], str(self.working_file.id))

    def test_get_task_working_files(self):
        self.generate_fixture_working_file()
        result = self.get(
            f"/data/tasks/{self.task.id}/working-files"
        )
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_get_output_file(self):
        self.generate_fixture_file_status()
        self.generate_fixture_output_type()
        self.generate_fixture_output_file()
        result = self.get(
            f"/data/files/{self.output_file.id}"
        )
        self.assertEqual(result["id"], str(self.output_file.id))

    def test_get_instance_output_types(self):
        self.generate_fixture_scene_asset_instance()
        result = self.get(
            f"/data/asset-instances/{self.asset_instance.id}"
            f"/entities/{self.scene.id}/output-types"
        )
        self.assertIsInstance(result, list)

    def test_guess_from_path(self):
        result = self.post(
            "/data/entities/guess_from_path",
            {
                "project_id": str(self.project.id),
                "file_path": "/some/test/path",
            },
            200,
        )
        self.assertIsInstance(result, list)

    def test_set_file_tree(self):
        result = self.post(
            f"/actions/projects/{self.project.id}/set-file-tree",
            {"tree_name": "default"},
            200,
        )
        self.assertIsNotNone(result)
        project = self.get(f"/data/projects/{self.project.id}")
        self.assertIsNotNone(project.get("file_tree"))
