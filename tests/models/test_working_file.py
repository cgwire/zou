from tests.base import ApiDBTestCase


class WorkingFileTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_task()

    def test_serialize_outputs(self):
        self.generate_fixture_software()
        working_file = self.generate_fixture_working_file()
        self.generate_fixture_file_status()
        self.generate_fixture_output_type()
        output_file = self.generate_fixture_output_file()
        output_file.source_file_id = working_file.id
        output_file.save()
        self.assertEqual(
            working_file.serialize(relations=True)["outputs"],
            [str(output_file.id)],
        )
