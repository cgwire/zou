import os

from tests.base import ApiDBTestCase
from zou.app import db

from zou.app.models.entity import Entity
from zou.app.models.metadata_descriptor import MetadataDescriptor
from zou.app.models.project import ProjectTaskTypeLink
from zou.app.models.task import Task
from zou.app.models.task_type import TaskType

from zou.app.services import assets_service, tasks_service


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
            TaskType.query.filter_by(for_entity="Asset").all()
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
        path = f"/import/csv/projects/{self.project.id}/assets"

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets.csv")
        )
        self.upload_file(path, file_path_fixture)

        entities = Entity.query.all()
        self.assertEqual(len(entities), 3)

        asset_types = assets_service.get_asset_types()
        self.assertEqual(len(asset_types), 2)

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
        self.upload_file(f"{path}?update=true", file_path_fixture)

        entities = Entity.query.all()
        self.assertEqual(len(entities), 3)

        asset = entities[0]
        self.assertEqual(asset.data.get("contractor", None), "contractor 1")

    def link_asset_task_types_to_project(self):
        """
        Enable the three Asset task types of the fixtures on the project and
        return them, so that a CSV column can be named after each of them.
        """
        task_types = [
            self.task_type,
            self.task_type_concept,
            self.task_type_modeling,
        ]
        for task_type in task_types:
            db.session.add(
                ProjectTaskTypeLink(
                    project_id=self.project_id, task_type_id=task_type.id
                )
            )
        db.session.commit()
        return task_types

    def test_import_assets_initializes_empty_task_columns_to_default(self):
        task_types = self.link_asset_task_types_to_project()
        self.generate_fixture_task_status_wip()
        # The status list the importer matches columns against is memoized.
        tasks_service.clear_task_status_cache(str(self.task_status_wip.id))
        default_status_id = tasks_service.get_default_status()["id"]

        path = f"/import/csv/projects/{self.project.id}/assets"
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_task_statuses.csv")
        )
        self.upload_file(path, file_path_fixture)

        # Every asset gets one task per task type of the project, whether
        # its column was filled or left empty.
        for asset_name in ("Cassette Player", "Wood Stick"):
            asset = Entity.get_by(name=asset_name, project_id=self.project_id)
            tasks = {
                str(task.task_type_id): task
                for task in Task.query.filter_by(entity_id=asset.id).all()
            }
            self.assertEqual(len(tasks), len(task_types))
            for task_type in task_types:
                self.assertIn(str(task_type.id), tasks)

        # An empty column means "not started": the task must exist and hold
        # the default status, not be skipped.
        cassette = Entity.get_by(
            name="Cassette Player", project_id=self.project_id
        )
        for task in Task.query.filter_by(entity_id=cassette.id).all():
            self.assertEqual(str(task.task_status_id), default_status_id)

        # A filled column only overrides the status of its own task.
        stick = Entity.get_by(name="Wood Stick", project_id=self.project_id)
        statuses = {
            str(task.task_type_id): str(task.task_status_id)
            for task in Task.query.filter_by(entity_id=stick.id).all()
        }
        self.assertEqual(
            statuses[str(self.task_type.id)], str(self.task_status_wip.id)
        )
        self.assertEqual(
            statuses[str(self.task_type_concept.id)], default_status_id
        )
        self.assertEqual(
            statuses[str(self.task_type_modeling.id)], default_status_id
        )

    def test_import_assets_creates_tasks_of_rows_before_a_failing_one(self):
        task_types = self.link_asset_task_types_to_project()
        default_status_id = tasks_service.get_default_status()["id"]

        path = f"/import/csv/projects/{self.project.id}/assets"
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_broken_task_status.csv")
        )
        error = self.upload_file(path, file_path_fixture, 400)
        self.assertEqual(error["imported_rows"], 2)

        # Rows are committed one by one, so the two valid assets remain.
        # Their tasks must remain too: they used to be created only after
        # the whole file had been read, and were lost with the failing row.
        entities = Entity.query.all()
        self.assertEqual(len(entities), 2)
        for asset in entities:
            tasks = Task.query.filter_by(entity_id=asset.id).all()
            self.assertEqual(len(tasks), len(task_types))
            for task in tasks:
                self.assertEqual(str(task.task_status_id), default_status_id)

    def test_import_assets_repairs_missing_tasks_without_update(self):
        path = f"/import/csv/projects/{self.project.id}/assets"
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_no_metadata.csv")
        )
        self.upload_file(path, file_path_fixture)
        self.assertEqual(len(Task.query.all()), 0)

        # Task types enabled after a first import: re-importing the same
        # file backfills the missing tasks, even without update=true.
        task_types = self.link_asset_task_types_to_project()
        self.upload_file(path, file_path_fixture)

        entities = Entity.query.all()
        self.assertEqual(len(entities), 3)
        self.assertEqual(
            len(Task.query.all()), len(task_types) * len(entities)
        )

    def test_import_assets_duplicates(self):
        path = f"/import/csv/projects/{self.project.id}/assets"

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets.csv")
        )
        self.upload_file(path, file_path_fixture)
        self.upload_file(path, file_path_fixture)

        entities = Entity.query.all()
        self.assertEqual(len(entities), 3)

    def generate_person_descriptor(self):
        self.generate_fixture_person()
        MetadataDescriptor.create(
            project_id=self.project.id,
            name="Reviewer",
            data_type="person",
            field_name="reviewer",
            entity_type="Asset",
        )

    def test_import_assets_person_metadata(self):
        self.generate_person_descriptor()
        path = f"/import/csv/projects/{self.project.id}/assets"
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_person_metadata.csv")
        )
        self.upload_file(path, file_path_fixture)

        # One row matches by full name, the other by email: both must
        # resolve to the person id, not store the raw cell.
        entities = Entity.query.all()
        self.assertEqual(len(entities), 2)
        for asset in entities:
            self.assertEqual(asset.data.get("reviewer"), str(self.person.id))

    def test_import_assets_person_metadata_unknown(self):
        self.generate_person_descriptor()
        path = f"/import/csv/projects/{self.project.id}/assets"
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_person_metadata_unknown.csv")
        )
        error = self.upload_file(path, file_path_fixture, 400)
        self.assertIn("Person not found", error["message"])
        self.assertEqual(len(Entity.query.all()), 0)

    def test_import_assets_with_non_comma_delimiter(self):
        path = f"/import/csv/projects/{self.project.id}/assets"
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_other_delimiter.csv")
        )
        self.upload_file(path, file_path_fixture)
        entities = Entity.query.all()
        self.assertEqual(len(entities), 3)

    def test_import_assets_empty_lines(self):
        # With empty lines. It should work
        path = f"/import/csv/projects/{self.project.id}/assets"
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_broken_01.csv")
        )
        self.upload_file(path, file_path_fixture)
        entities = Entity.query.all()
        self.assertEqual(len(entities), 3)

    def test_import_assets_missing_columns(self):
        # With missing columns on a given line. It should not work.
        path = f"/import/csv/projects/{self.project.id}/assets"
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_broken_02.csv")
        )
        error = self.upload_file(path, file_path_fixture, 400)
        self.assertEqual(error["message"], "Could not determine delimiter")
        entities = Entity.query.all()
        self.assertEqual(len(entities), 0)

    def test_import_assets_missing_header(self):
        # With missing columns on a given line. It should not work.
        path = f"/import/csv/projects/{self.project.id}/assets"
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets_broken_03.csv")
        )
        error = self.upload_file(path, file_path_fixture, 400)
        # The header is file line 1, so the first data row is line 2.
        self.assertEqual(error["line_number"], 2)
        entities = Entity.query.all()
        self.assertEqual(len(entities), 0)
