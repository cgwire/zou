from tests.base import ApiDBTestCase
from zou.app.utils import fields


class SearchFilterTestCase(ApiDBTestCase):
    def setUp(self):
        super(SearchFilterTestCase, self).setUp()
        self.generate_base_context()
        self.person_id = str(self.user["id"])
        self.project_id = str(self.project.id)
        for i in range(3):
            self.post(
                "data/search-filters",
                {
                    "name": "Filter %d" % i,
                    "list_type": "assets",
                    "search_query": "query%d" % i,
                    "person_id": self.person_id,
                    "project_id": self.project_id,
                },
            )

    def test_get_search_filters(self):
        filters = self.get("data/search-filters")
        self.assertEqual(len(filters), 3)

    def test_get_search_filter(self):
        search_filter = self.get_first("data/search-filters")
        search_filter_again = self.get(
            "data/search-filters/%s" % search_filter["id"]
        )
        self.assertEqual(search_filter, search_filter_again)
        self.get_404("data/search-filters/%s" % fields.gen_uuid())

    def test_create_search_filter(self):
        data = {
            "name": "New Filter",
            "list_type": "shots",
            "search_query": "new_query",
            "person_id": self.person_id,
            "project_id": self.project_id,
        }
        search_filter = self.post("data/search-filters", data)
        self.assertIsNotNone(search_filter["id"])
        filters = self.get("data/search-filters")
        self.assertEqual(len(filters), 4)

    def test_update_search_filter(self):
        search_filter = self.get_first("data/search-filters")
        data = {"name": "Updated Filter"}
        self.put(
            "data/search-filters/%s" % search_filter["id"], data
        )
        search_filter_again = self.get(
            "data/search-filters/%s" % search_filter["id"]
        )
        self.assertEqual(data["name"], search_filter_again["name"])
        self.put_404(
            "data/search-filters/%s" % fields.gen_uuid(), data
        )

    def test_delete_search_filter(self):
        filters = self.get("data/search-filters")
        self.assertEqual(len(filters), 3)
        search_filter = filters[0]
        self.delete("data/search-filters/%s" % search_filter["id"])
        filters = self.get("data/search-filters")
        self.assertEqual(len(filters), 2)
        self.delete_404(
            "data/search-filters/%s" % fields.gen_uuid()
        )
