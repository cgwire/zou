from zou.app.models.metadata_descriptor import MetadataDescriptor

from tests.edits.base import BaseEditTestCase


class EditCsvExportTestCase(BaseEditTestCase):
    def test_export(self):
        csv_edits = self.get_raw(
            "/export/csv/projects/%s/edits.csv" % self.project.id
        )
        expected_result = """Project;Episode;Name;Description;Time Spent;Contractor;Edit;Assignations\r
Cosmos Landromat;E01;Edit;Description of the Edit;0.21;;opn;John Doe\r\n"""
        self.assertEqual(csv_edits, expected_result)

    def test_export_with_metadata(self):
        MetadataDescriptor.create(
            project_id=self.project.id,
            name="Start frame",
            field_name="start_frame",
            data_type="list",
            choices=["0", "100"],
            entity_type="Edit",
        )
        self.edit.update(
            {
                "data": {
                    "start_frame": "100",
                }
            }
        )
        csv_edits = self.get_raw(
            "/export/csv/projects/%s/edits.csv" % self.project.id
        )
        expected_result = """Project;Episode;Name;Description;Time Spent;Contractor;Start frame;Edit;Assignations\r
Cosmos Landromat;E01;Edit;Description of the Edit;0.21;;100;opn;John Doe\r\n"""
        self.assertEqual(csv_edits, expected_result)
