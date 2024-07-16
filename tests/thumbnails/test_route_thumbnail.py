import os
import hashlib

from tests.base import ApiDBTestCase

from zou.app.utils import fs, thumbnail
from zou.app.services import assets_service

from PIL import Image

TEST_FOLDER = os.path.join("tests", "tmp")


def get_file_md5hash(file_path):
    with open(file_path, "rb") as f:
        file_hash = hashlib.md5()
        while chunk := f.read(8192):
            file_hash.update(chunk)


class RouteThumbnailTestCase(ApiDBTestCase):
    def setUp(self):
        super(RouteThumbnailTestCase, self).setUp()

        self.delete_thumbnail_folders()
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
        super(RouteThumbnailTestCase, self).tearDown()

        self.delete_thumbnail_folders()

    def delete_thumbnail_folders(self):
        fs.rm_rf(TEST_FOLDER)

    def test_add_thumbnail(self):
        path = "/pictures/thumbnails/persons/%s" % self.person_id

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        self.upload_file(path, file_path_fixture)

        path = "/pictures/thumbnails/persons/%s.png" % self.person_id
        result_file_path = self.get_file_path("th01.png")

        self.create_test_folder()
        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)

        self.assertEqual(result_image.size, thumbnail.BIG_SQUARE_SIZE)

    def test_add_preview(self):
        path = "/pictures/preview-files/%s" % self.preview_file_id

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        self.upload_file(path, file_path_fixture)

        current_path = os.path.dirname(__file__)
        result_file_path = os.path.join(TEST_FOLDER, "th01.png")
        result_file_path = os.path.join(
            current_path, "..", "..", result_file_path
        )
        os.mkdir(TEST_FOLDER)

        path = "/pictures/previews/preview-files/%s.png" % self.preview_file_id
        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)
        self.assertEqual(result_image.size, (1200, 674))

        path = (
            "/pictures/thumbnails/preview-files/%s.png" % self.preview_file_id
        )
        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)
        self.assertEqual(result_image.size, (150, 100))

        path = (
            "/pictures/thumbnails-square/preview-files/%s.png"
            % self.preview_file_id
        )
        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)
        self.assertEqual(result_image.size, (100, 100))

    def test_set_main_preview(self):
        path = "/pictures/preview-files/%s" % self.preview_file_id

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        self.upload_file(path, file_path_fixture)

        path = (
            "/actions/preview-files/%s/set-main-preview" % self.preview_file_id
        )
        self.put(path, {})

        asset = assets_service.get_asset(self.asset_id)
        self.assertEqual(asset["preview_file_id"], str(self.preview_file_id))

    def test_add_preview_background(self):
        self.generate_fixture_preview_background_file()
        path = f"/pictures/preview-background-files/{self.preview_background_file.id}"

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "sample.hdr")
        )
        self.upload_file(path, file_path_fixture)
        original_md5hash = get_file_md5hash(file_path_fixture)

        current_path = os.path.dirname(__file__)
        result_file_path = os.path.join(TEST_FOLDER, "sample.hdr")
        result_file_path = os.path.join(
            current_path, "..", "..", result_file_path
        )
        os.mkdir(TEST_FOLDER)

        path = f"/pictures/preview-background-files/{self.preview_background_file.id}.hdr"
        self.download_file(path, result_file_path)
        result_md5hash = get_file_md5hash(result_file_path)
        self.assertEqual(result_md5hash, original_md5hash)

        path = f"/pictures/thumbnails/preview-background-files/{self.preview_background_file.id}.png"
        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)
        self.assertEqual(result_image.size, (300, 200))
