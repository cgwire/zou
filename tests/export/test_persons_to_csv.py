from tests.base import ApiDBTestCase

from zou.app.models.studio import Studio


class PersonsCsvExportTestCase(ApiDBTestCase):
    def setUp(self):
        super(PersonsCsvExportTestCase, self).setUp()

        # Creates departments "Modeling" and "Animation".
        self.generate_fixture_department()
        studio = Studio.create(name="Test Studio", color="#000000")
        self.person = self.generate_fixture_person(country="fr")
        self.person.update(
            {
                "position": "lead",
                "seniority": "senior",
                "daily_salary": 300,
                "studio_id": studio.id,
            }
        )
        self.person.set_departments(
            [self.department.id, self.department_animation.id]
        )

    def test_export(self):
        csv_persons = self.get_raw("/export/csv/persons.csv")
        expected_result = (
            "First Name;Last Name;Email;Phone;Role;Departments;Studio;"
            "Country;Contract Type;Position;Seniority;Daily Salary;Active\r\n"
            "John;Did;john.did@gmail.com;;admin;;;;open-ended;artist;mid;0;"
            "yes\r\n"
            "John;Doe;john.doe@gmail.com;;user;Animation,Modeling;"
            "Test Studio;FR;open-ended;lead;senior;300;yes\r\n"
        )
        self.assertEqual(csv_persons, expected_result)
