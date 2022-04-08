import os
import json

from tests.base import ApiDBTestCase
from zou.app import db

from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType


class ImportCsvAssetsTestCase(ApiDBTestCase):
    def setUp(self):
        super(ImportCsvAssetsTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_metadata_descriptor(entity_type="Asset")
        self.generate_fixture_department()
        self.generate_fixture_task_type()

    def test_import_assets(self):
        self.assertEqual(len(Task.query.all()), 0)
        number_of_task_per_entity_to_create = len(
            TaskType.query.filter_by(for_shots=False, for_entity="Asset").all()
        )
        db.session.add(
            ProjectTaskTypeLink(
                project_id=self.project_id, task_type_id=self.task_type.id
            )
        )
        db.session.add(
            ProjectTaskTypeLink(
                project_id=self.project_id,
                task_type_id=self.task_type_concept.id,
            )
        )
        db.session.add(
            ProjectTaskTypeLink(
                project_id=self.project_id,
                task_type_id=self.task_type_modeling.id,
            )
        )
        db.session.add(
            ProjectTaskTypeLink(
                project_id=self.project_id,
                task_type_id=self.task_type_layout.id,
            )
        )
        db.session.add(
            ProjectTaskTypeLink(
                project_id=self.project_id,
                task_type_id=self.task_type_animation.id,
            )
        )
        db.session.commit()
        self.assertEqual(number_of_task_per_entity_to_create, 3)
        path = "/import/csv/projects/%s/assets" % self.project.id

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets.csv")
        )
        self.upload_file(path, file_path_fixture)

        entities = Entity.query.all()
        self.assertEqual(len(entities), 3)

        entity_types = EntityType.query.all()
        self.assertEqual(len(entity_types), 2)

        tasks = Task.query.all()
        self.assertEqual(
            len(tasks),
            number_of_task_per_entity_to_create * len(entities),
        )

        asset = entities[0]
        self.assertEqual(asset.data.get("contractor", None), "contractor 1")

        task = tasks[0]
        self.assertEqual(task.entity_id, asset.id)

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_no_metadata.csv")
        )
        self.upload_file("%s?update=true" % path, file_path_fixture)

        entities = Entity.query.all()
        self.assertEqual(len(entities), 3)

        asset = entities[0]
        self.assertEqual(asset.data.get("contractor", None), "contractor 1")

    def test_import_assets_duplicates(self):
        path = "/import/csv/projects/%s/assets" % self.project.id

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets.csv")
        )
        self.upload_file(path, file_path_fixture)
        self.upload_file(path, file_path_fixture)

        entities = Entity.query.all()
        self.assertEqual(len(entities), 3)

    def test_import_assets_with_non_comma_delimiter(self):
        path = "/import/csv/projects/%s/assets" % self.project.id
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_other_delimiter.csv")
        )
        self.upload_file(path, file_path_fixture)
        entities = Entity.query.all()
        self.assertEqual(len(entities), 3)

    def test_import_assets_empty_lines(self):
        # With empty lines. It should work
        path = "/import/csv/projects/%s/assets" % self.project.id
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_broken_01.csv")
        )
        self.upload_file(path, file_path_fixture)
        entities = Entity.query.all()
        self.assertEqual(len(entities), 3)

    def test_import_assets_missing_columns(self):
        # With missing columns on a given line. It should not work.
        path = "/import/csv/projects/%s/assets" % self.project.id
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_broken_02.csv")
        )
        result = self.upload_file(path, file_path_fixture, 400)
        if type(result) != str:
            result = result.decode("utf-8")
        error = json.loads(result)
        self.assertEqual(error["line_number"], 2)
        entities = Entity.query.all()
        self.assertEqual(len(entities), 1)

    def test_import_assets_missing_header(self):
        # With missing columns on a given line. It should not work.
        path = "/import/csv/projects/%s/assets" % self.project.id
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_broken_03.csv")
        )
        result = self.upload_file(path, file_path_fixture, 400)
        if type(result) != str:
            result = result.decode("utf-8")
        error = json.loads(result)
        self.assertEqual(error["line_number"], 1)
        entities = Entity.query.all()
        self.assertEqual(len(entities), 0)
