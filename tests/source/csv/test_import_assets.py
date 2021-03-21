import os
import json

from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity
from zou.app.models.entity_type import EntityType


class ImportCsvAssetsTestCase(ApiDBTestCase):
    def setUp(self):
        super(ImportCsvAssetsTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_metadata_descriptor(entity_type="Asset")

    def test_import_assets(self):
        path = "/import/csv/projects/%s/assets" % self.project.id

        file_path_fixture = self.get_fixture_file_path(
            os.path.join("csv", "assets.csv")
        )
        self.upload_file(path, file_path_fixture)

        entities = Entity.query.all()
        self.assertEqual(len(entities), 3)

        entity_types = EntityType.query.all()
        self.assertEqual(len(entity_types), 2)

        asset = entities[0]
        self.assertEqual(asset.data.get("contractor", None), "contractor 1")

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
