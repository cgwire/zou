import os

from tests.base import ApiDBTestCase

from zou.app.services import shots_service


class ImportOTIOEdlTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project(name="TestProject")
        self.project.update({"fps": "25"})

    def import_edl(self, edl_filename):
        path = "/import/otio/projects/%s" % self.project.id
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

        shots_by_name = {s["name"]: s for s in shots}

        shot1 = shots_by_name["sc010"]
        self.assertEqual(shot1["nb_frames"], 130)
        self.assertEqual(shot1["data"]["frame_in"], 0)
        self.assertEqual(shot1["data"]["frame_out"], 129)

        shot2 = shots_by_name["sc020"]
        self.assertEqual(shot2["nb_frames"], 73)
        self.assertEqual(shot2["data"]["frame_in"], 130)
        self.assertEqual(shot2["data"]["frame_out"], 202)

    def test_import_edl_with_tc_offset(self):
        self.import_edl("tc_offset.edl")

        sequences = shots_service.get_sequences()
        self.assertEqual(len(sequences), 2)

        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 3)

        shots_by_name = {s["name"]: s for s in shots}

        shot1 = shots_by_name["sc010"]
        self.assertEqual(shot1["nb_frames"], 130)
        self.assertEqual(shot1["data"]["frame_in"], 0)
        self.assertEqual(shot1["data"]["frame_out"], 129)

        shot2 = shots_by_name["sc020"]
        self.assertEqual(shot2["nb_frames"], 73)
        self.assertEqual(shot2["data"]["frame_in"], 130)
        self.assertEqual(shot2["data"]["frame_out"], 202)

    def test_import_edl_creates_sequences(self):
        self.import_edl("tc_offset.edl")

        sequences = shots_service.get_sequences()
        sequence_names = {s["name"] for s in sequences}
        self.assertEqual(sequence_names, {"SQ010", "SQ020"})

    def test_import_edl_updates_existing_shots(self):
        self.import_edl("no_offset.edl")
        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 3)

        self.import_edl("no_offset.edl")
        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 3)
