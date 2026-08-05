from tests.base import ApiDBTestCase

from zou.app.models.preview_file import PreviewFile


class PreviewActionsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()

        self.first = self.generate_fixture_preview_file(
            name="first", position=1
        ).serialize()
        self.second = self.generate_fixture_preview_file(
            name="second", position=2
        ).serialize()
        self.third = self.generate_fixture_preview_file(
            name="third", position=3
        ).serialize()

    def positions(self):
        """
        Read the stored positions keyed by name. The route answers with the
        previews in their former order and only the position field carries
        the new one, so ordering the response would prove nothing.
        """
        previews = PreviewFile.query.filter_by(task_id=self.task.id).all()
        return {preview.name: preview.position for preview in previews}

    def test_update_preview_position(self):
        self.assertEqual(
            self.positions(), {"first": 1, "second": 2, "third": 3}
        )

        self.put(
            f"/actions/preview-files/{self.third['id']}/update-position",
            {"position": 1},
        )

        self.assertEqual(
            self.positions(), {"third": 1, "first": 2, "second": 3}
        )

    def test_update_preview_position_out_of_range(self):
        """
        A position outside 1..len is ignored rather than raising, so a client
        racing against a deletion cannot 500 the route.
        """
        self.put(
            f"/actions/preview-files/{self.first['id']}/update-position",
            {"position": 99},
        )
        self.assertEqual(
            self.positions(), {"first": 1, "second": 2, "third": 3}
        )

    def test_extract_frame_from_a_picture(self):
        """
        Only a movie has frames to extract. A preview of any other extension
        is a 404, not a crash inside ffmpeg.
        """
        picture = self.generate_fixture_preview_file(name="picture")
        picture.update({"extension": "png"})
        self.get(f"/actions/preview-files/{picture.id}/extract-frame", 404)
