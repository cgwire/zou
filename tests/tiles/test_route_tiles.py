import os

from tests.base import ApiDBTestCase

from zou.app.utils import fs
from zou.app.services import assets_service
from zou.app.models.entity import Entity

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

    def tearDown(self):
        super(RouteTileTestCase, self).tearDown()

        self.delete_tile_folders()

    def delete_tile_folders(self):
        fs.rm_rf(TEST_FOLDER)

    def test_extract_tile(self):
 
        path = "/actions/preview-files/%s/extract-tile" % self.preview_file_id

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("tiles", "preview01.mp4")
        )

        self.upload_file(path, file_path_fixture)

        current_path = os.path.dirname(__file__)
        result_file_path = os.path.join(TEST_FOLDER, "tile01.png")
        result_file_path = os.path.join(
            current_path, "..", "..", result_file_path
        )
        os.mkdir(TEST_FOLDER)

        path = "/movies/tiles/preview-files/%s.png" % self.preview_file_id
        result_file_path = self.get_file_path("tile01.png")

        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)        

        self.assertEqual(result_image.size, (1704, 3840))