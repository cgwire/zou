import os

from tests.base import ApiDBTestCase
from zou.app import db

from zou.app.models.entity_type import EntityType
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task import Task
from zou.app.services import shots_service


class ImportCsvShotsTestCase(ApiDBTestCase):
    def setUp(self):
        super(ImportCsvShotsTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_metadata_descriptor(entity_type="Shot")
        self.generate_fixture_department()
        self.generate_fixture_task_type()

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
        path = "/import/csv/projects/%s/shots" % self.project.id
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

        self.assertEqual(
            set(str(task.entity_id) for task in tasks),
            set(shot["id"] for shot in shots),
        )

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "shots_no_metadata.csv")
        )
        self.upload_file("%s?update=true" % path, file_path_fixture)

        shots = shots_service.get_shots()
        self.assertEqual(len(shots), 4)

        entity_types = EntityType.query.all()
        self.assertEqual(len(entity_types), 4)

        shot = shots[0]
        self.assertEqual(shot["data"].get("contractor", None), "contractor 1")
