import os
import hashlib

from tests.base import ApiDBTestCase

from zou.app.utils import fs, thumbnail
from zou.app.services import assets_service, persons_service, projects_service

from PIL import Image

# Absolute, so that the folder created and the folder written to are the
# same one wherever pytest is launched from and however deep this file sits.
TEST_FOLDER = os.path.join(
    os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ),
    "tmp",
)


def get_file_md5hash(file_path):
    with open(file_path, "rb") as f:
        file_hash = hashlib.md5()
        while chunk := f.read(8192):
            file_hash.update(chunk)


class RouteThumbnailTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.delete_thumbnail_folders()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.generate_fixture_working_file()
        self.generate_fixture_preview_file()
        self.asset_id = self.asset.id
        self.preview_file_id = self.preview_file.id
        self.person_id = self.person.id

    def tearDown(self):
        super().tearDown()

        self.delete_thumbnail_folders()

    def delete_thumbnail_folders(self):
        fs.rm_rf(TEST_FOLDER)

    def test_add_thumbnail(self):
        path = f"/pictures/thumbnails/persons/{self.person_id}"

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        self.upload_file(path, file_path_fixture)

        path = f"/pictures/thumbnails/persons/{self.person_id}.png"
        result_file_path = self.get_file_path("th01.png")

        self.create_test_folder()
        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)

        self.assertEqual(result_image.size, thumbnail.BIG_SQUARE_SIZE)

    def test_add_thumbnail_without_file_keeps_has_avatar_false(self):
        path = f"/pictures/thumbnails/persons/{self.person_id}"
        response = self.app.post(path, headers=self.base_headers)
        self.assertEqual(response.status_code, 400)
        person = self.get(f"data/persons/{self.person_id}")
        self.assertFalse(person["has_avatar"])

    def test_add_preview(self):
        path = f"/pictures/preview-files/{self.preview_file_id}"

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        self.upload_file(path, file_path_fixture)

        result_file_path = os.path.join(TEST_FOLDER, "th01.png")
        os.makedirs(TEST_FOLDER, exist_ok=True)

        path = f"/pictures/previews/preview-files/{self.preview_file_id}.png"
        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)
        self.assertEqual(result_image.size, (1200, 674))

        path = f"/pictures/thumbnails/preview-files/{self.preview_file_id}.png"
        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)
        self.assertEqual(result_image.size, (150, 100))

        path = f"/pictures/thumbnails-square/preview-files/{self.preview_file_id}.png"
        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)
        self.assertEqual(result_image.size, (100, 100))

    def test_set_main_preview(self):
        path = f"/pictures/preview-files/{self.preview_file_id}"

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png")
        )
        self.upload_file(path, file_path_fixture)

        path = (
            f"/actions/preview-files/{self.preview_file_id}/set-main-preview"
        )
        self.put(path, {})

        asset = assets_service.get_asset(self.asset_id)
        self.assertEqual(asset["preview_file_id"], str(self.preview_file_id))

    def test_set_main_preview_as_client(self):
        # A client can review but must not redefine the entity thumbnail.
        self.generate_fixture_user_client()
        projects_service.add_team_member(
            str(self.project.id), self.user_client["id"]
        )
        self.log_in_client()
        path = (
            f"/actions/preview-files/{self.preview_file_id}/set-main-preview"
        )
        self.put(path, {}, 403)

    def test_add_preview_background(self):
        self.generate_fixture_preview_background_file()
        path = f"/pictures/preview-background-files/{self.preview_background_file.id}"

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "sample.hdr")
        )
        self.upload_file(path, file_path_fixture)
        original_md5hash = get_file_md5hash(file_path_fixture)

        result_file_path = os.path.join(TEST_FOLDER, "sample.hdr")
        os.makedirs(TEST_FOLDER, exist_ok=True)

        path = f"/pictures/preview-background-files/{self.preview_background_file.id}.hdr"
        self.download_file(path, result_file_path)
        result_md5hash = get_file_md5hash(result_file_path)
        self.assertEqual(result_md5hash, original_md5hash)

        path = f"/pictures/thumbnails/preview-background-files/{self.preview_background_file.id}.png"
        self.download_file(path, result_file_path)
        result_image = Image.open(result_file_path)
        self.assertEqual(result_image.size, (300, 200))

    def _upload_thumbnail(self, path):
        self.upload_file(
            path,
            self.get_fixture_file_path(os.path.join("thumbnails", "th01.png")),
        )

    def test_add_project_thumbnail(self):
        path = f"/pictures/thumbnails/projects/{self.project.id}"
        self._upload_thumbnail(path)

        self.create_test_folder()
        result_file_path = self.get_file_path("project-th.png")
        self.download_file(f"{path}.png", result_file_path)

        self.assertEqual(
            Image.open(result_file_path).size, thumbnail.BIG_SQUARE_SIZE
        )
        self.assertTrue(
            projects_service.get_project(str(self.project.id))["has_avatar"]
        )

    def test_project_thumbnail_needs_project_access(self):
        """
        A project avatar is only readable by a manager or by someone on the
        production. Uploading one is stricter still, it takes a manager of
        that production.
        """
        path = f"/pictures/thumbnails/projects/{self.project.id}"
        self._upload_thumbnail(path)

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.get(f"{path}.png", 403)
        self.upload_file(
            path,
            self.get_fixture_file_path(os.path.join("thumbnails", "th01.png")),
            code=403,
        )

    def test_add_organisation_thumbnail(self):
        """
        The organisation is a singleton: the resource resolves it with
        get_organisation() and ignores the id in the url when reading, so the
        round trip only holds for the one row the instance actually has.
        """
        organisation_id = persons_service.get_organisation()["id"]
        path = f"/pictures/thumbnails/organisations/{organisation_id}"
        self._upload_thumbnail(path)

        self.create_test_folder()
        result_file_path = self.get_file_path("organisation-th.png")
        self.download_file(f"{path}.png", result_file_path)

        self.assertEqual(
            Image.open(result_file_path).size, thumbnail.BIG_SQUARE_SIZE
        )
