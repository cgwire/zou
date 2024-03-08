from tests.base import ApiDBTestCase


class PersonsCsvExportTestCase(ApiDBTestCase):
    def setUp(self):
        super(PersonsCsvExportTestCase, self).setUp()

        self.generate_fixture_person()

    def test_export(self):
        csv_persons = self.get_raw("/export/csv/persons.csv")
        expected_result = """Last Name;First Name;Email;Phone;Role;Contract Type;Active\r
Did;John;john.did@gmail.com;;admin;open-ended;yes\r
Doe;John;john.doe@gmail.com;;user;open-ended;yes\r\n"""
        self.assertEqual(csv_persons, expected_result)
