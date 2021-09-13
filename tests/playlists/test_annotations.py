from tests.base import ApiDBTestCase

from zou.app.services import projects_service


class PlaylistTestCase(ApiDBTestCase):
    def setUp(self):
        super(PlaylistTestCase, self).setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_assigner()
        self.generate_fixture_person()
        self.generate_fixture_task()

        self.annotations = [
            {
                "drawing": {
                    "objects": [
                        {
                            "id": "obj-1",
                            "type": "Path",
                            "path": ["0 0", "0 10"],
                        }
                    ]
                },
                "time": 0,
            }
        ]

    def tearDown(self):
        super(PlaylistTestCase, self).tearDown()
        self.delete_test_folder()

    def test_update_annotations(self):
        preview_file = self.generate_fixture_preview_file().serialize()
        self.put(
            "actions/preview-files/%s/update-annotations" % preview_file["id"],
            {"additions": self.annotations, "deletions": [], "updates": []},
        )
        preview_file = self.get("data/preview-files/%s" % preview_file["id"])
        self.assertEqual(preview_file["annotations"], self.annotations)

    def test_update_annotations_rights(self):
        self.generate_fixture_user_client()
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project.id, self.user_client["id"]
        )
        projects_service.add_team_member(
            self.project.id, self.user_cg_artist["id"]
        )
        preview_file = self.generate_fixture_preview_file().serialize()
        self.log_in_client()
        self.put(
            "actions/preview-files/%s/update-annotations" % preview_file["id"],
            {"additions": self.annotations},
        )

        self.log_in_cg_artist()
        self.put(
            "actions/preview-files/%s/update-annotations" % preview_file["id"],
            {"additions": self.annotations},
            403,
        )
