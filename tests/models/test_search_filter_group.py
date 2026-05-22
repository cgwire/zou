from tests.base import ApiDBTestCase
from zou.app.models.search_filter_group import SearchFilterGroup
from zou.app.utils import fields


class SearchFilterGroupTestCase(ApiDBTestCase):
    def setUp(self):
        super(SearchFilterGroupTestCase, self).setUp()
        self.generate_data(SearchFilterGroup, 3)

    def test_get_search_filter_groups(self):
        groups = self.get("data/search-filter-groups")
        self.assertEqual(len(groups), 3)

    def test_get_search_filter_group(self):
        group = self.get_first("data/search-filter-groups")
        group_again = self.get(f"data/search-filter-groups/{group['id']}")
        self.assertEqual(group, group_again)
        self.get_404(f"data/search-filter-groups/{fields.gen_uuid()}")

    def test_create_search_filter_group(self):
        data = {
            "name": "My Group",
            "list_type": "assets",
            "color": "#FF0000",
        }
        group = self.post("data/search-filter-groups", data)
        self.assertIsNotNone(group["id"])
        groups = self.get("data/search-filter-groups")
        self.assertEqual(len(groups), 4)

    def test_update_search_filter_group(self):
        group = self.get_first("data/search-filter-groups")
        data = {"name": "Updated Group"}
        self.put(f"data/search-filter-groups/{group['id']}", data)
        group_again = self.get(f"data/search-filter-groups/{group['id']}")
        self.assertEqual(data["name"], group_again["name"])
        self.put_404(f"data/search-filter-groups/{fields.gen_uuid()}", data)

    def test_delete_search_filter_group(self):
        groups = self.get("data/search-filter-groups")
        self.assertEqual(len(groups), 3)
        group = groups[0]
        self.delete(f"data/search-filter-groups/{group['id']}")
        groups = self.get("data/search-filter-groups")
        self.assertEqual(len(groups), 2)
        self.delete_404(f"data/search-filter-groups/{fields.gen_uuid()}")
