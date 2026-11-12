import datetime

from tests.base import ApiDBTestCase
from zou.app.models.person import Person
from zou.app.utils import fields


class PaginationTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
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
        self.assertEqual(result["data"], [])
        self.assertEqual(result["total"], 251)
        result = self.get("data/persons?page=0")
        self.assertEqual(result["data"], [])
        self.assertEqual(result["total"], 251)

    def test_walk_by_cursor(self):
        page = self.get("data/persons?limit=100")
        self.assertEqual(len(page), 100)
        # Rows created together and rows without a date: the cursor lands
        # among both and must neither skip nor repeat one.
        # The logged in user is left out: the listing serves their own row
        # from a cache, with the date they had before the test changed it.
        persons = (
            Person.query.filter(Person.id != self.user["id"]).limit(60).all()
        )
        for person in persons[:30]:
            person.update({"created_at": datetime.datetime(2020, 1, 1)})
        for person in persons[30:]:
            person.update({"created_at": None})
        walked = self.get_by_cursor("data/persons", 20)
        ids = [person["id"] for person in walked]
        self.assertEqual(len(set(ids)), 251)
        self.assertEqual(
            set(ids), {person["id"] for person in self.get("data/persons")}
        )
        dates = [
            person["created_at"] for person in walked if person["created_at"]
        ]
        self.assertEqual(len(dates), 221)
        self.assertEqual(dates, sorted(dates, reverse=True))
        # A cursor alone falls back on the default page size.
        page = self.get(f"data/persons?cursor_id={ids[199]}")
        self.assertEqual([person["id"] for person in page], ids[200:])

    def test_walk_by_cursor_keeps_the_filters(self):
        for person in Person.query.limit(3).all():
            person.update({"last_name": "Cursor"})
        persons = self.get_by_cursor("data/persons?last_name=Cursor", 2)
        self.assertEqual(len(persons), 3)

    def test_malformed_cursor_returns_400(self):
        self.get("data/persons?cursor_id=foo", 400)
        self.get(f"data/persons?cursor_id={fields.gen_uuid()}", 400)
        self.get("data/persons?limit=-1", 400)

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
