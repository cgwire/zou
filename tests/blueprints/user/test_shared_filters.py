from tests.base import ApiDBTestCase

from zou.app.services import persons_service, projects_service, user_service


class SharedFilterMixin:
    """
    Filters and filter groups share one sharing rule, so they share one
    story here. A filter is private to its author until is_shared is set;
    a shared one reaches the whole team, unless it names a department, in
    which case it reaches that department only.

    Not a TestCase, so neither loader collects it on its own.
    """

    path = None
    detail_path = None

    def clear_cache(self):
        raise NotImplementedError

    def payload(self, name, **overrides):
        raise NotImplementedError

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_department()
        self.generate_fixture_user_cg_artist()
        self.project_id = str(self.project.id)

    def create(self, name, **overrides):
        return self.post(self.path, self.payload(name, **overrides))

    def visible_names(self):
        """
        The names the logged in user sees for the project, sorted, so the
        assertions do not depend on the order the route happens to return.
        """
        self.clear_cache()
        result = self.get(self.path)
        if not result:
            return []
        return sorted(f["name"] for f in result["asset"][self.project_id])

    def put_join_the_team_and_the_department(self):
        projects_service.add_team_member(
            self.project_id, self.user_cg_artist["id"]
        )
        artist = persons_service.get_person_raw(self.user_cg_artist["id"])
        artist.departments.append(self.department)
        artist.save()
        persons_service.clear_person_cache()

    def test_the_listing_is_grouped_by_list_type_and_project(self):
        for list_type, name in [
            ("asset", "a1"),
            ("shot", "s1"),
            ("all", "x1"),
        ]:
            self.create(name, list_type=list_type)
        self.clear_cache()
        result = self.get(self.path)
        self.assertEqual(
            {
                list_type: [
                    row["name"] for row in per_project[self.project_id]
                ]
                for list_type, per_project in result.items()
            },
            {"asset": ["a1"], "shot": ["s1"], "all": ["x1"]},
        )

    def test_updating_one_shows_on_its_own_route(self):
        created = self.create("before")
        self.put(f"{self.path}{created['id']}", {"name": "after"})
        result = self.get(f"{self.detail_path}{created['id']}")
        self.assertEqual(result["name"], "after")

    def test_removing_one_empties_the_listing(self):
        created = self.create("gone")
        self.assertEqual(self.visible_names(), ["gone"])
        self.delete(f"{self.path}{created['id']}")
        self.assertEqual(self.visible_names(), [])

    def test_a_private_one_is_invisible_to_everyone_else(self):
        self.log_in_cg_artist()
        self.create("mine", is_shared=False)
        self.assertEqual(self.visible_names(), ["mine"])

        self.log_in_admin()
        self.assertEqual(self.visible_names(), [])

    def test_a_shared_one_reaches_the_team(self):
        self.log_in_cg_artist()
        self.create("mine", is_shared=False)
        self.log_in_admin()
        self.put_join_the_team_and_the_department()
        self.create("team", is_shared=True)

        self.log_in_cg_artist()
        self.assertEqual(self.visible_names(), ["mine", "team"])

    def test_only_the_author_can_update_a_shared_one(self):
        self.log_in_admin()
        self.put_join_the_team_and_the_department()
        shared = self.create("team", is_shared=True)

        self.put(f"{self.path}{shared['id']}", {"name": "team updated"})
        self.assertEqual(self.visible_names(), ["team updated"])

        # A reader of a shared filter is not an owner of it: the route
        # answers 404 rather than telling them it exists.
        self.log_in_cg_artist()
        self.put(f"{self.path}{shared['id']}", {"name": "stolen"}, 404)
        self.assertEqual(self.visible_names(), ["team updated"])

    def test_a_department_one_only_reaches_that_department(self):
        self.log_in_admin()
        self.put_join_the_team_and_the_department()
        self.create("team", is_shared=True)
        # The artist belongs to self.department, not to this one.
        scoped = self.create(
            "department",
            is_shared=True,
            department_id=str(self.department_animation.id),
        )

        self.log_in_cg_artist()
        self.assertEqual(self.visible_names(), ["team"])

        self.log_in_admin()
        self.put(
            f"{self.path}{scoped['id']}",
            {
                "name": "department",
                "is_shared": True,
                "department_id": str(self.department.id),
            },
        )

        self.log_in_cg_artist()
        self.assertEqual(self.visible_names(), ["department", "team"])


class SharedFilterTestCase(SharedFilterMixin, ApiDBTestCase):
    path = "data/user/filters/"
    detail_path = "data/search-filters/"

    def clear_cache(self):
        user_service.clear_filter_cache()

    def payload(self, name, **overrides):
        return {
            "list_type": "asset",
            "name": name,
            "query": "props",
            "project_id": self.project_id,
            **overrides,
        }

    def test_the_query_is_stored_as_search_query(self):
        """
        The route takes "query" and the row carries "search_query": the two
        names are part of the contract, so renaming either breaks clients.
        """
        self.create("props")
        self.clear_cache()
        result = self.get(self.path)
        self.assertEqual(
            result["asset"][self.project_id][0]["search_query"], "props"
        )


class SharedFilterGroupTestCase(SharedFilterMixin, ApiDBTestCase):
    path = "data/user/filter-groups/"
    detail_path = "data/search-filter-groups/"

    def clear_cache(self):
        user_service.clear_filter_group_cache()

    def payload(self, name, **overrides):
        return {
            "list_type": "asset",
            "name": name,
            "color": "",
            "project_id": self.project_id,
            **overrides,
        }
