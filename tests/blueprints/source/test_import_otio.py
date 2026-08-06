import os
import tempfile

from io import BytesIO

from tests.base import ApiDBTestCase

from zou.app.services import shots_service


class ImportOTIOEdlTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project(name="TestProject")
        self.project.update({"fps": "25"})

    def import_edl(self, edl_filename):
        path = f"/import/otio/projects/{self.project.id}"
        file_path = self.get_fixture_file_path(
            os.path.join("edl", edl_filename)
        )
        self.upload_file(path, file_path)

    def test_import_edl_no_offset(self):
        self.import_edl("no_offset.edl")

        sequences = shots_service.get_sequences()
        self.assertEqual(len(sequences), 2)

        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 3)

        shots = sorted(shots, key=lambda s: s["data"]["frame_in"])

        self.assertEqual(shots[0]["name"], "sc010")
        self.assertEqual(shots[0]["nb_frames"], 130)
        self.assertEqual(shots[0]["data"]["frame_in"], 0)
        self.assertEqual(shots[0]["data"]["frame_out"], 129)

        self.assertEqual(shots[1]["name"], "sc020")
        self.assertEqual(shots[1]["nb_frames"], 73)
        self.assertEqual(shots[1]["data"]["frame_in"], 130)
        self.assertEqual(shots[1]["data"]["frame_out"], 202)

    def test_import_edl_with_tc_offset(self):
        self.import_edl("tc_offset.edl")

        sequences = shots_service.get_sequences()
        self.assertEqual(len(sequences), 2)

        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 3)

        shots = sorted(shots, key=lambda s: s["data"]["frame_in"])

        self.assertEqual(shots[0]["name"], "sc010")
        self.assertEqual(shots[0]["nb_frames"], 130)
        self.assertEqual(shots[0]["data"]["frame_in"], 0)
        self.assertEqual(shots[0]["data"]["frame_out"], 129)

        self.assertEqual(shots[1]["name"], "sc020")
        self.assertEqual(shots[1]["nb_frames"], 73)
        self.assertEqual(shots[1]["data"]["frame_in"], 130)
        self.assertEqual(shots[1]["data"]["frame_out"], 202)

    def test_import_edl_creates_sequences(self):
        self.import_edl("tc_offset.edl")

        sequences = shots_service.get_sequences()
        sequence_names = {s["name"] for s in sequences}
        self.assertEqual(sequence_names, {"SQ010", "SQ020"})

    def _upload_bad_file(self, suffix, content):
        path = f"/import/otio/projects/{self.project.id}"
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False
        ) as bad_file:
            bad_file.write(content)
        try:
            return self.upload_file(path, bad_file.name, code=400)
        finally:
            os.remove(bad_file.name)

    def test_import_unsupported_file_type(self):
        # A file OTIO has no adapter for (e.g. a csv) is a user error: clean
        # 400 with an explicit message, not a logged server error.
        result = self._upload_bad_file(".csv", "shot;frame_in;frame_out\n")
        self.assertIn("Unsupported file type '.csv'", result["message"])
        self.assertIn("edl", result["message"])

    def test_import_unparseable_file(self):
        result = self._upload_bad_file(".edl", "this is not an edl\n")
        self.assertIn("Failed to parse OTIO file", result["message"])

    def test_import_ignores_uploaded_file_name(self):
        # The temporary file is named from a uuid, so an uploaded name
        # holding an absolute path (or a "../" prefix) leaves the file it
        # points at alone.
        path = f"/import/otio/projects/{self.project.id}"
        with tempfile.TemporaryDirectory() as target_dir:
            canary_path = os.path.join(target_dir, "canary.edl")
            with open(canary_path, "w") as canary:
                canary.write("keep me")

            response = self.app.post(
                path,
                data={"file": (BytesIO(b"not an edl\n"), canary_path)},
                headers=self.base_headers,
            )
            self.assertEqual(response.status_code, 400)

            self.assertTrue(os.path.exists(canary_path))
            with open(canary_path) as canary:
                self.assertEqual(canary.read(), "keep me")

    def test_import_edl_updates_existing_shots(self):
        self.import_edl("no_offset.edl")
        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 3)

        self.import_edl("no_offset.edl")
        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 3)

    def test_import_edl_into_an_episode(self):
        """
        The episode variant of the route. A series cuts one edl per episode,
        and the sequences it creates have to hang from that episode instead
        of from the production root.
        """
        self.project.update({"production_type": "tvshow"})
        episode = self.generate_fixture_episode("E01", self.project.id)
        path = (
            f"/import/otio/projects/{self.project.id}"
            f"/episodes/{episode.id}"
        )
        # The episode route defaults to a four part convention that carries
        # the episode name. The fixture edl names clips with three, so the
        # convention travels with the upload.
        self.upload_file(
            path,
            self.get_fixture_file_path(os.path.join("edl", "no_offset.edl")),
            extra_fields={
                "naming_convention": (
                    "${project_name}_${sequence_name}-${shot_name}"
                )
            },
        )

        sequences = shots_service.get_sequences()
        self.assertEqual(len(sequences), 2)
        self.assertEqual(
            {sequence["parent_id"] for sequence in sequences},
            {str(episode.id)},
        )
