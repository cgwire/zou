from tests.base import ApiDBTestCase

from zou.app.models.person import Person


class PaginationTestCase(ApiDBTestCase):
    def setUp(self):
        super(PaginationTestCase, self).setUp()
        self.generate_data(Person, 250, departments=[])

    def test_paginate(self):
        persons = self.get("data/persons?page=1")["data"]
        self.assertEqual(len(persons), 100)
        persons = self.get("data/persons?page=2")["data"]
        self.assertEqual(len(persons), 100)
        persons = self.get("data/persons?page=3")["data"]
        self.assertEqual(len(persons), 51)

    def test_404(self):
        result = self.get("data/persons?page=4")
        self.assertEqual(len(result["data"]), 0)
        self.assertEqual(result["total"], 251)
        result = self.get("data/persons?page=0")
        self.assertEqual(len(result["data"]), 0)
        self.assertEqual(result["total"], 251)

    def test_malformed_page_returns_400(self):
        self.get("data/persons?page=foo", 400)
        self.get("data/persons?page=1&limit=bar", 400)

    def test_metadata(self):
        pagination_infos = self.get("data/persons?page=2")
        self.assertEqual(pagination_infos["total"], 251)
        self.assertEqual(pagination_infos["nb_pages"], 3)
        self.assertEqual(pagination_infos["page"], 2)
        self.assertEqual(pagination_infos["offset"], 100)
        self.assertEqual(pagination_infos["limit"], 100)
