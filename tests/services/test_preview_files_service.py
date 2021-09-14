from tests.base import ApiDBTestCase

from zou.app.services import files_service, preview_files_service


class PlaylistTestCase(ApiDBTestCase):
    def setUp(self):
        super(PlaylistTestCase, self).setUp()
        self.generate_base_context()
        self.project_id = str(self.project.id)
        self.user_id = self.user["id"]
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.annotations_1 = [
            {
                "time": "0",
                "drawing": {
                    "objects": [
                        {"id": "obj1", "type": "path", "path": ["Q", 0, 10]}
                    ]
                },
            }
        ]
        self.annotations_2 = [
            {
                "time": "2",
                "drawing": {
                    "objects": [
                        {"id": "obj2", "type": "path", "path": ["Q", 1, 11]}
                    ]
                },
            }
        ]
        self.annotations_3 = [
            {
                "time": "0",
                "drawing": {
                    "objects": [
                        {"id": "obj3", "type": "path", "path": ["Q", 1, 11]}
                    ]
                },
            }
        ]

    def tearDown(self):
        super(PlaylistTestCase, self).tearDown()
        self.delete_test_folder()

    def test_add_annotations(self):
        preview_file = self.generate_fixture_preview_file().serialize()
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_1,
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            self.annotations_1,
            persisted_preview_file["annotations"],
        )

    def test_add_annotations_different_time(self):
        preview_file = self.generate_fixture_preview_file().serialize()
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_1,
        )
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_2,
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            self.annotations_1 + self.annotations_2,
            persisted_preview_file["annotations"],
        )

    def test_add_annotations_different_objects(self):
        expected_result = [
            {
                "time": "0",
                "drawing": {
                    "objects": [
                        self.annotations_1[0]["drawing"]["objects"][0],
                        self.annotations_3[0]["drawing"]["objects"][0],
                    ]
                },
            }
        ]
        preview_file = self.generate_fixture_preview_file().serialize()
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_1,
        )
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_3,
        )
        annotations = files_service.get_preview_file(preview_file["id"])[
            "annotations"
        ]
        self.assertEqual(expected_result, annotations)
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_3,
        )
        annotations = files_service.get_preview_file(preview_file["id"])[
            "annotations"
        ]
        self.assertEqual(expected_result, annotations)

    def test_delete_annotations(self):
        preview_file = self.generate_fixture_preview_file().serialize()
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_1,
        )
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=[],
            deletions=[{"time": "2", "objects": ["obj1"]}],
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            self.annotations_1,
            persisted_preview_file["annotations"],
        )
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=[],
            deletions=[{"time": "0", "objects": ["obj4"]}],
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            self.annotations_1,
            persisted_preview_file["annotations"],
        )
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=[],
            deletions=[{"time": "0", "objects": ["obj1"]}],
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            [],
            persisted_preview_file["annotations"],
        )

    def test_update_annotations(self):
        self.modifications = [
            {
                "time": "0",
                "drawing": {
                    "objects": [
                        {"id": "obj1", "type": "path", "path": ["Q", 2, 14]}
                    ]
                },
            }
        ]
        preview_file = self.generate_fixture_preview_file().serialize()
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            additions=self.annotations_1 + self.annotations_2,
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        preview_files_service.update_preview_file_annotations(
            self.user_id,
            self.project_id,
            preview_file["id"],
            updates=self.modifications,
        )
        persisted_preview_file = files_service.get_preview_file(
            preview_file["id"]
        )
        self.assertEqual(
            self.modifications + self.annotations_2,
            persisted_preview_file["annotations"],
        )
