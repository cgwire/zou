import os
import tempfile

from tests.base import ApiDBTestCase

from zou.app.models.person import Person
from zou.app.models.studio import Studio


class ImportCsvPersonsTestCase(ApiDBTestCase):

    columns = [
        "First Name",
        "Last Name",
        "Email",
        "Phone",
        "Role",
        "Departments",
        "Studio",
        "Country",
        "Contract Type",
        "Position",
        "Seniority",
        "Daily Salary",
        "Active",
    ]

    def setUp(self):
        super(ImportCsvPersonsTestCase, self).setUp()
        # Creates departments "Modeling" and "Animation".
        self.generate_fixture_department()
        Studio.create(name="Test Studio", color="#000000")

    def test_import_persons(self):
        self.upload_file(
            "/import/csv/persons",
            self.get_fixture_file_path(os.path.join("csv", "persons.csv")),
        )

        persons = Person.query.all()
        self.assertEqual(len(persons), 3)

        # First row mixes human labels (Artist / Lead / Senior / Open-ended)
        # and a comma-separated department cell in a ";"-delimited file.
        john = Person.get_by(email="john.doe@gmail.com")
        self.assertEqual(john.role.code, "user")
        self.assertEqual(john.position.code, "lead")
        self.assertEqual(john.seniority.code, "senior")
        self.assertEqual(john.contract_type.code, "open-ended")
        self.assertEqual(john.country, "FR")
        self.assertEqual(john.daily_salary, 320)
        self.assertTrue(john.active)
        self.assertEqual(
            sorted(department.name for department in john.departments),
            ["Animation", "Modeling"],
        )
        self.assertEqual(Studio.get(john.studio_id).name, "Test Studio")

        # Second row uses stored codes (supervisor / artist / junior /
        # freelance) instead of labels.
        ema = Person.get_by(email="ema.doe@gmail.com")
        self.assertEqual(ema.role.code, "supervisor")
        self.assertEqual(ema.position.code, "artist")
        self.assertEqual(ema.seniority.code, "junior")
        self.assertEqual(ema.contract_type.code, "freelance")
        self.assertEqual(ema.country, "US")
        self.assertEqual(ema.daily_salary, 450)
        self.assertFalse(ema.active)
        self.assertEqual(
            [department.name for department in ema.departments], ["Animation"]
        )

    def test_import_persons_update_replaces_departments(self):
        self.upload_file(
            "/import/csv/persons",
            self.get_fixture_file_path(os.path.join("csv", "persons.csv")),
        )
        self._upload_csv(
            self._csv(
                **{
                    "First Name": "John",
                    "Last Name": "Doe",
                    "Email": "john.doe@gmail.com",
                    "Departments": "Animation",
                }
            ),
            update=True,
        )
        john = Person.get_by(email="john.doe@gmail.com")
        self.assertEqual(
            [department.name for department in john.departments], ["Animation"]
        )

    def test_import_persons_update_replaces_scalar_fields(self):
        # The update branch (person.update(data)) must persist the new scalar
        # fields on an existing person, not just departments.
        self.upload_file(
            "/import/csv/persons",
            self.get_fixture_file_path(os.path.join("csv", "persons.csv")),
        )
        Studio.create(name="Other Studio", color="#FFFFFF")
        self._upload_csv(
            self._csv(
                **{
                    "First Name": "John",
                    "Last Name": "Doe",
                    "Email": "john.doe@gmail.com",
                    "Country": "us",
                    "Position": "artist",
                    "Seniority": "junior",
                    "Daily Salary": "500",
                    "Studio": "Other Studio",
                }
            ),
            update=True,
        )
        john = Person.get_by(email="john.doe@gmail.com")
        self.assertEqual(john.country, "US")
        self.assertEqual(john.position.code, "artist")
        self.assertEqual(john.seniority.code, "junior")
        self.assertEqual(john.daily_salary, 500)
        self.assertEqual(Studio.get(john.studio_id).name, "Other Studio")

    def test_import_persons_existing_without_update_is_noop(self):
        # Re-importing an existing email without ?update=true leaves the
        # person untouched (scalar fields and departments) and still
        # returns 201.
        self.upload_file(
            "/import/csv/persons",
            self.get_fixture_file_path(os.path.join("csv", "persons.csv")),
        )
        self._upload_csv(
            self._csv(
                **{
                    "First Name": "John",
                    "Last Name": "Doe",
                    "Email": "john.doe@gmail.com",
                    "Country": "us",
                    "Position": "artist",
                    "Departments": "Animation",
                }
            )
        )
        john = Person.get_by(email="john.doe@gmail.com")
        self.assertEqual(john.country, "FR")
        self.assertEqual(john.position.code, "lead")
        self.assertEqual(
            sorted(department.name for department in john.departments),
            ["Animation", "Modeling"],
        )

    def test_import_persons_invalid_country(self):
        self._upload_csv(self._csv(Country="France"), code=400)

    def test_import_persons_invalid_position(self):
        self._upload_csv(self._csv(Position="Boss"), code=400)

    def test_import_persons_invalid_daily_salary(self):
        self._upload_csv(self._csv(**{"Daily Salary": "lots"}), code=400)

    def test_import_persons_unknown_studio(self):
        self._upload_csv(self._csv(Studio="Ghost Studio"), code=400)
        self.assertIsNone(Person.get_by(email="test.user@gmail.com"))

    def test_import_persons_unknown_department(self):
        # Departments are resolved before the person is written, so a bad
        # name fails the row without leaving an orphan person behind.
        self._upload_csv(self._csv(Departments="Ghost"), code=400)
        self.assertIsNone(Person.get_by(email="test.user@gmail.com"))

    def test_import_persons_studio_and_department_are_case_sensitive(self):
        # Studio "Test Studio" and department "Animation" exist; names are
        # matched exactly, so a casing mismatch fails the row (400) without
        # leaving an orphan person behind.
        self._upload_csv(self._csv(Studio="test studio"), code=400)
        self.assertIsNone(Person.get_by(email="test.user@gmail.com"))
        self._upload_csv(self._csv(Departments="animation"), code=400)
        self.assertIsNone(Person.get_by(email="test.user@gmail.com"))

        # The exact names resolve as expected.
        self._upload_csv(
            self._csv(Studio="Test Studio", Departments="Animation")
        )
        person = Person.get_by(email="test.user@gmail.com")
        self.assertEqual(Studio.get(person.studio_id).name, "Test Studio")
        self.assertEqual(
            [department.name for department in person.departments],
            ["Animation"],
        )

    def _csv(self, **overrides):
        values = {column: "" for column in self.columns}
        values["First Name"] = "Test"
        values["Last Name"] = "User"
        values["Email"] = "test.user@gmail.com"
        values.update(overrides)
        header = ";".join(f'"{column}"' for column in self.columns)
        row = ";".join(f'"{values[column]}"' for column in self.columns)
        return f"{header}\n{row}\n"

    def _upload_csv(self, content, code=201, update=False):
        path = "/import/csv/persons"
        if update:
            path = f"{path}?update=true"
        descriptor, file_path = tempfile.mkstemp(suffix=".csv")
        try:
            with os.fdopen(
                descriptor, "w", encoding="utf-8", newline=""
            ) as csv_file:
                csv_file.write(content)
            return self.upload_file(path, file_path, code)
        finally:
            os.remove(file_path)
