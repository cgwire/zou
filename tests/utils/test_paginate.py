from tests.base import ApiDBTestCase
from zou.app.models.person import Person
from zou.app.utils import query as query_utils


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

    def test_limit_only_returns_first_page(self):
        result = self.get("data/persons?limit=10")
        self.assertEqual(len(result["data"]), 10)
        self.assertEqual(result["page"], 1)
        self.assertEqual(result["total"], 251)
        self.assertEqual(result["nb_pages"], 26)

    def test_limit_is_capped(self):
        max_limit = self.flask_app.config["MAX_RECORDS_PER_PAGE"]
        result = self.get(f"data/persons?limit={max_limit + 1}")
        self.assertEqual(result["limit"], max_limit)

    def test_pages_do_not_overlap(self):
        # Rows generated in one go share their timestamps: only the id
        # tiebreak keeps the pages apart.
        ids = []
        for page in range(1, 4):
            result = self.get(f"data/persons?page={page}")
            ids += [person["id"] for person in result["data"]]
        self.assertEqual(len(ids), 251)
        self.assertEqual(len(set(ids)), 251)

    def test_get_paginated_results(self):
        query = Person.query
        self.assertEqual(
            len(query_utils.get_paginated_results(query, -1)), 251
        )
        result = query_utils.get_paginated_results(query, 2, limit=50)
        self.assertEqual(len(result["data"]), 50)
        self.assertEqual(result["nb_pages"], 6)
        ids = []
        for page in range(1, 7):
            result = query_utils.get_paginated_results(query, page, limit=50)
            ids += [person["id"] for person in result["data"]]
        self.assertEqual(len(set(ids)), 251)
        max_limit = self.flask_app.config["MAX_RECORDS_PER_PAGE"]
        result = query_utils.get_paginated_results(
            query, 1, limit=max_limit + 1
        )
        self.assertEqual(result["limit"], max_limit)

    def test_paginate_list(self):
        result = query_utils.paginate_list(list(range(25)), 3, 10)
        self.assertEqual(result["data"], [20, 21, 22, 23, 24])
        self.assertEqual(result["total"], 25)
        self.assertEqual(result["nb_pages"], 3)
        self.assertEqual(result["offset"], 20)
