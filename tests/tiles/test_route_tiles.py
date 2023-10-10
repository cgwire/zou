import os

from tests.base import ApiDBTestCase

from zou.app.utils import fs

from PIL import Image

TEST_FOLDER = os.path.join("tests", "tmp")


class RouteTileTestCase(ApiDBTestCase):
    def setUp(self):
        super(RouteTileTestCase, self).setUp()

        self.delete_tile_folders()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.generate_fixture_software()
        self.generate_fixture_working_file()
        self.generate_fixture_preview_file()
        self.asset_id = self.asset.id
        self.preview_file_id = self.preview_file.id
        self.person_id = self.person.id
        os.makedirs(TEST_FOLDER)

    def tearDown(self):
        super(RouteTileTestCase, self).tearDown()

        self.delete_tile_folders()

    def delete_tile_folders(self):
        fs.rm_rf(TEST_FOLDER)

    def test_extract_tile(self):
        path = "/pictures/preview-files/%s" % self.preview_file_id
        file_path_fixture = self.get_fixture_file_path(
            "videos/test_preview_tiles.mp4"
        )
        self.upload_file(path, file_path_fixture)

        path = "/actions/preview-files/%s/extract-tile" % self.preview_file_id
        try:
            self.get(path)
        except Exception:
            pass
        path = "/movies/tiles/preview-files/%s.png" % self.preview_file_id
        result_file_path = self.get_file_path("tile01.png")
        self.download_file(path, result_file_path)

        result_image = Image.open(result_file_path)
        self.assertEqual(result_image.size, (1912, 600))
