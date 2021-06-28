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

    def tearDown(self):
        super(PlaylistTestCase, self).tearDown()
        self.delete_test_folder()

    def test_update_annotations(self):
        preview_file = self.generate_fixture_preview_file().serialize()
        annotations = [{
            "0": [
                "Path", "0 0", "0 10"
            ]
        }]
        self.put(
            "actions/preview-files/%s/update-annotations" % preview_file["id"],
            {"annotations": annotations}
        )
        preview_file = self.get("data/preview-files/%s" % preview_file["id"])
        self.assertEqual(preview_file["annotations"], annotations)

    def test_update_annotations_rights(self):
        self.generate_fixture_user_client()
        self.generate_fixture_user_cg_artist()
        projects_service.add_team_member(
            self.project.id,
            self.user_client["id"]
        )
        projects_service.add_team_member(
            self.project.id,
            self.user_cg_artist["id"]
        )
        preview_file = self.generate_fixture_preview_file().serialize()
        annotations = [{
            "0": [
                "Path", "0 0", "0 10"
            ]
        }]

        self.log_in_client()
        self.put(
            "actions/preview-files/%s/update-annotations" % preview_file["id"],
            {"annotations": annotations}
        )

        self.log_in_cg_artist()
        self.put(
            "actions/preview-files/%s/update-annotations" % preview_file["id"],
            {"annotations": annotations},
            403
        )
