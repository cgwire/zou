from tests.base import ApiDBTestCase

from zou.app.models.department import Department


class CrudFieldsParamTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_data(Department, 3)

    def test_fields_param_trims_entries(self):
        departments = self.get("data/departments?fields=name")
        self.assertEqual(len(departments), 3)
        for department in departments:
            self.assertIn("name", department)
            self.assertIn("id", department)
            self.assertNotIn("color", department)

    def test_fields_param_paginated(self):
        result = self.get("data/departments?page=1&fields=name")
        self.assertEqual(result["total"], 3)
        for department in result["data"]:
            self.assertIn("name", department)
            self.assertIn("id", department)
            self.assertNotIn("color", department)

    def test_fields_param_unknown_field_is_ignored(self):
        departments = self.get("data/departments?fields=name,nonexistent")
        for department in departments:
            self.assertIn("name", department)
            self.assertNotIn("nonexistent", department)
            self.assertNotIn("color", department)

    def test_no_fields_param_returns_everything(self):
        departments = self.get("data/departments")
        for department in departments:
            self.assertIn("color", department)
