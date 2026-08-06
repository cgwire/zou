import os

from tests.base import ApiDBTestCase
from zou.app import db

from zou.app.models.entity_type import EntityType
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task import Task
from zou.app.services import projects_service, shots_service


class ImportCsvShotsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_metadata_descriptor(entity_type="Shot")
        self.generate_fixture_task_type()

    def _tmp_csv_files(self):
        tmp_dir = self.app.application.config["TMP_DIR"]
        return {name for name in os.listdir(tmp_dir) if name.endswith(".csv")}

    def test_import_leaves_no_file_behind(self):
        path = f"/import/csv/projects/{self.project.id}/shots"
        self.project.update({"production_type": "tvshow"})
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "shots.csv")
        )
        before = self._tmp_csv_files()
        self.upload_file(path, file_path_fixture)
        self.assertEqual(self._tmp_csv_files(), before)

    def test_a_refused_import_writes_nothing(self):
        # The upload used to be saved before the permission check ran, and
        # never removed, so a 403 still cost a file in TMP_DIR.
        path = f"/import/csv/projects/{self.project.id}/shots"
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "shots.csv")
        )
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        before = self._tmp_csv_files()
        self.upload_file(path, file_path_fixture, 403)
        self.assertEqual(self._tmp_csv_files(), before)

    def test_import_needs_managing_this_project(self):
        # Holding the manager role somewhere is not enough: the OTIO import
        # and the CSV exports both scope to the production, and
        # check_project_permissions was written for this and never wired.
        path = f"/import/csv/projects/{self.project.id}/shots"
        self.project.update({"production_type": "tvshow"})
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "shots.csv")
        )
        self.generate_fixture_user_manager()
        self.log_in_manager()
        self.upload_file(path, file_path_fixture, 403)

        projects_service.add_team_member(
            self.project.id, self.user_manager["id"]
        )
        self.upload_file(path, file_path_fixture)
        self.assertEqual(len(shots_service.get_shots()), 4)

    def test_import_shots(self):
        self.assertEqual(len(Task.query.all()), 0)
        db.session.add(
            ProjectTaskTypeLink(
                project_id=self.project_id, task_type_id=self.task_type.id
            )
        )
        db.session.add(
            ProjectTaskTypeLink(
                project_id=self.project_id,
                task_type_id=self.task_type_layout.id,
            )
        )
        path = f"/import/csv/projects/{self.project.id}/shots"
        self.project.update({"production_type": "tvshow"})

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "shots.csv")
        )
        self.upload_file(path, file_path_fixture)

        sequences = shots_service.get_sequences()
        self.assertEqual(len(sequences), 3)
        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 4)

        entity_types = EntityType.query.all()
        self.assertEqual(len(entity_types), 4)

        tasks = Task.query.all()
        self.assertEqual(
            len(tasks),
            len(shots),
        )

        shot = shots[0]
        self.assertEqual(shot["data"].get("contractor", None), "contractor 1")

        # nb_frames is derived from the imported frame range (all fixture
        # rows cover 100-frame ranges).
        for shot in shots:
            self.assertEqual(shot["nb_frames"], 101)

        self.assertEqual(
            set(str(task.entity_id) for task in tasks),
            set(shot["id"] for shot in shots),
        )

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "shots_no_metadata.csv")
        )
        self.upload_file(f"{path}?update=true", file_path_fixture)

        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 4)

        entity_types = EntityType.query.all()
        self.assertEqual(len(entity_types), 4)

        shot = shots[0]
        self.assertEqual(shot["data"].get("contractor", None), "contractor 1")

    def test_import_shots_empty_boolean_descriptor(self):
        MetadataDescriptor.create(
            project_id=self.project.id,
            name="Delivery",
            data_type="boolean",
            field_name="delivery",
            choices=[],
            entity_type="Shot",
        )
        path = f"/import/csv/projects/{self.project.id}/shots"
        self.project.update({"production_type": "tvshow"})

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "shots_boolean_metadata.csv")
        )
        self.upload_file(path, file_path_fixture)

        shots = {s["name"]: s for s in shots_service.get_shots()}
        self.assertEqual(shots["BS01"]["data"]["delivery"], "true")
        # An empty boolean cell must not fail the import.
        self.assertEqual(shots["BS02"]["data"]["delivery"], "")

    def test_import_shots_frame_range_is_normalized(self):
        path = f"/import/csv/projects/{self.project.id}/shots"
        self.project.update({"production_type": "tvshow"})

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "shots_frame_range.csv")
        )
        self.upload_file(path, file_path_fixture)

        shots = {s["name"]: s for s in shots_service.get_shots()}

        # An empty frame value must not be stored as "": the key stays absent
        # so it reads as None, consistently with a shot never given one.
        empty = shots["FS01"]
        self.assertNotIn("frame_in", empty["data"])
        self.assertNotIn("frame_out", empty["data"])

        # A provided frame value is stored as an int, not the raw CSV string.
        filled = shots["FS02"]
        self.assertEqual(filled["data"]["frame_in"], 1001)
        self.assertEqual(filled["data"]["frame_out"], 1100)
        self.assertIsInstance(filled["data"]["frame_in"], int)
        self.assertIsInstance(filled["data"]["frame_out"], int)
