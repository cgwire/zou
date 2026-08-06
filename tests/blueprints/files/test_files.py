from tests.base import ApiDBTestCase

from zou.app.models.output_type import OutputType
from zou.app.services import files_service


class FileRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_task()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_scene()

    def test_get_working_file(self):
        self.generate_fixture_working_file()
        result = self.get(f"/data/files/{self.working_file.id}")
        self.assertEqual(result["id"], str(self.working_file.id))

    def test_get_task_working_files(self):
        self.generate_fixture_working_file()
        result = self.get(f"/data/tasks/{self.task.id}/working-files")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_get_output_file(self):
        self.generate_fixture_file_status()
        self.generate_fixture_output_type()
        self.generate_fixture_output_file()
        result = self.get(f"/data/files/{self.output_file.id}")
        self.assertEqual(result["id"], str(self.output_file.id))

    def test_get_instance_output_types(self):
        """
        The output types an instance has published under, which is empty
        until it publishes something.
        """
        self.generate_fixture_scene_asset_instance()
        path = (
            f"/data/asset-instances/{self.asset_instance.id}"
            f"/entities/{self.scene.id}/output-types"
        )
        self.assertEqual(self.get(path), [])

        cache = files_service.get_or_create_output_type("Cache", "cch")
        geometry = files_service.get_or_create_output_type("Geometry", "geo")
        for output_type in [cache, geometry]:
            self.generate_fixture_output_file(
                OutputType.get(output_type["id"]),
                asset_instance=self.asset_instance,
                temporal_entity_id=self.scene.id,
            )

        result = self.get(path)

        # Ordered by name, the reverse of the order they were made in.
        self.assertEqual(
            [output_type["name"] for output_type in result],
            ["Cache", "Geometry"],
        )

    def test_guess_from_path(self):
        result = self.post(
            "/data/entities/guess-from-path",
            {
                "project_id": str(self.project.id),
                "file_path": "/some/test/path",
            },
            200,
        )
        # Nothing in that path names anything of this production.
        self.assertEqual(result, [])

    def test_guess_from_path_reads_a_real_path(self):
        """
        A path built from the production's own file tree resolves to the
        entities it names. Every token is looked up with an ilike, which has
        to reach filter rather than filter_by.
        """
        self.generate_fixture_task()

        result = self.post(
            "/data/entities/guess-from-path",
            {
                "project_id": str(self.project.id),
                "file_path": (
                    "/simple/productions/cosmos_landromat/assets/Props/Tree/"
                    "Shaders/blender"
                ),
            },
            200,
        )

        self.assertEqual(
            result,
            [
                {
                    "Template": "asset",
                    "Project": str(self.project.id),
                    "AssetType": str(self.asset_type.id),
                    "Asset": str(self.asset.id),
                    "TaskType": str(self.task_type.id),
                }
            ],
        )

    def test_guess_from_path_deprecated_alias(self):
        """
        The underscore spelling is kept for older clients and has to answer
        exactly what the canonical route answers.
        """
        body = {
            "project_id": str(self.project.id),
            "file_path": (
                "/simple/productions/cosmos_landromat/assets/Props/Tree/"
                "Shaders/blender"
            ),
        }

        alias = self.post("/data/entities/guess_from_path", body, 200)

        self.assertEqual(
            alias, self.post("/data/entities/guess-from-path", body, 200)
        )

    def test_set_file_tree(self):
        result = self.post(
            f"/actions/projects/{self.project.id}/set-file-tree",
            {"tree_name": "default"},
            200,
        )
        self.assertIsNotNone(result)
        project = self.get(f"/data/projects/{self.project.id}")
        self.assertIsNotNone(project.get("file_tree"))
