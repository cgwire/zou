import uuid

from tests.base import ApiDBTestCase
from zou.app.models.search_filter import SearchFilter
from zou.app.models.search_filter_group import SearchFilterGroup
from zou.app.services import (
    persons_service,
    projects_service,
    search_filters_service,
)


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
    model = None

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
        self.unknown_id = str(uuid.uuid4())

    def create(self, name, **overrides):
        return self.post(self.path, self.payload(name, **overrides))

    def visible_names(self):
        """
        The names the logged in user sees for the project, sorted, so the
        assertions do not depend on the order the route happens to return.
        """
        self.clear_cache()
        return self.listed_names()

    def listed_names(self):
        """
        The same names as the route gives them now, memoized or not.
        """
        result = self.get(self.path)
        if not result:
            return []
        return sorted(f["name"] for f in result["asset"][self.project_id])

    def department_of(self, row_id):
        department_id = self.model.get(row_id).department_id
        return department_id and str(department_id)

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

    def test_a_shared_one_stays_within_its_project_teams(self):
        self.put_join_the_team_and_the_department()
        # The fixture moves self.project_id onto the new project.
        other_project_id = str(self.generate_fixture_project("Other").id)
        self.create("elsewhere", is_shared=True, project_id=other_project_id)

        self.log_in_cg_artist()
        self.clear_cache()
        result = self.get(self.path)
        self.assertNotIn(other_project_id, result.get("asset", {}))

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

    def test_a_department_one_stays_in_the_list_of_its_owner(self):
        """
        The department tells whom else a row reaches: its owner lists it even
        out of that department and with no manager role.
        """
        animation = str(self.department_animation.id)
        self.log_in_admin()
        self.put_join_the_team_and_the_department()
        for name, is_shared in [("private", False), ("shared", True)]:
            row = self.create(
                name, is_shared=is_shared, department_id=animation
            )
            # Sharing takes a manager, but the owner can lose that role.
            self.model.get(row["id"]).update(
                {"person_id": self.user_cg_artist["id"]}
            )

        self.log_in_cg_artist()
        self.assertEqual(self.visible_names(), ["private", "shared"])

    def test_a_name_of_the_column_length_is_kept(self):
        self.create("n" * 200)
        self.assertEqual(self.visible_names(), ["n" * 200])

    def test_a_name_longer_than_its_column_is_refused(self):
        self.post(self.path, self.payload("n" * 201), 400)
        self.assertEqual(self.visible_names(), [])

    def test_renaming_beyond_the_column_length_is_refused(self):
        created = self.create("before")
        self.put(f"{self.path}{created['id']}", {"name": "n" * 201}, 400)
        self.assertEqual(self.visible_names(), ["before"])

    def test_renaming_to_nothing_is_refused(self):
        created = self.create("before")
        self.put(f"{self.path}{created['id']}", {"name": ""}, 400)
        self.assertEqual(self.visible_names(), ["before"])

    def test_a_list_type_of_the_column_length_is_kept(self):
        self.create("n", list_type="t" * 80)

    def test_a_list_type_longer_than_its_column_is_refused(self):
        self.post(self.path, self.payload("n", list_type="t" * 81), 400)
        self.assertEqual(self.visible_names(), [])

    def test_an_entity_type_of_the_column_length_is_kept(self):
        self.create("n", entity_type="t" * 80)
        self.assertEqual(self.visible_names(), ["n"])

    def test_an_entity_type_longer_than_its_column_is_refused(self):
        self.post(self.path, self.payload("n", entity_type="t" * 81), 400)
        self.assertEqual(self.visible_names(), [])

    def test_a_name_used_in_the_list_is_refused(self):
        self.create("wip")
        self.post(self.path, self.payload("wip"), 400)
        self.assertEqual(self.visible_names(), ["wip"])

    def test_a_name_used_out_of_any_production_is_refused(self):
        self.create("wip", project_id=None)
        self.post(self.path, self.payload("wip", project_id=None), 400)
        self.clear_cache()
        names = [f["name"] for f in self.get(self.path)["asset"]["all"]]
        self.assertEqual(names, ["wip"])

    def test_renaming_to_a_name_used_in_the_list_is_refused(self):
        self.create("wip")
        other = self.create("other")
        self.put(f"{self.path}{other['id']}", {"name": "wip"}, 400)
        self.assertEqual(self.visible_names(), ["other", "wip"])

    def test_a_name_stays_free_in_the_other_lists(self):
        self.create("wip")
        self.create("wip", list_type="shot")
        self.create("wip", entity_type="Shot")
        self.create("wip", project_id=None)
        self.create(
            "wip", project_id=str(self.generate_fixture_project("Other").id)
        )

    def test_two_people_can_use_the_same_name(self):
        self.log_in_cg_artist()
        self.create("wip")
        self.log_in_admin()
        self.create("wip")

    def test_a_new_name_is_checked_among_the_rows_of_the_owner(self):
        self.log_in_cg_artist()
        self.create("used by the artist")
        row = self.create("mine")
        self.log_in_admin()
        self.create("used by the admin")

        path = f"{self.path}{row['id']}"
        self.put(path, {"name": "used by the artist"}, 400)
        self.put(path, {"name": "used by the admin"})

    def test_a_new_name_is_checked_in_the_project_of_the_row(self):
        row = self.create("mine")
        self.create("used here")
        other_project_id = str(self.generate_fixture_project("Other").id)
        self.create("used elsewhere", project_id=other_project_id)

        path = f"{self.path}{row['id']}"
        self.put(
            path, {"name": "used here", "project_id": other_project_id}, 400
        )
        self.put(
            path, {"name": "used elsewhere", "project_id": other_project_id}
        )

    def test_a_new_name_stays_free_in_the_other_lists(self):
        self.create("used in shots", list_type="shot")
        self.create("used on shot tasks", entity_type="Shot")
        row = self.create("mine")

        path = f"{self.path}{row['id']}"
        self.put(path, {"name": "used in shots"})
        self.put(path, {"name": "used on shot tasks"})

    def test_another_project_leaves_a_row_where_it_is(self):
        project_id = self.project_id
        row = self.create("wip")
        other_project_id = str(self.generate_fixture_project("Other").id)

        updated = self.put(
            f"{self.path}{row['id']}", {"project_id": other_project_id}
        )

        self.assertEqual(updated["project_id"], project_id)
        self.assertEqual(str(self.model.get(row["id"]).project_id), project_id)

    def test_another_project_holding_the_name_changes_nothing(self):
        project_id = self.project_id
        row = self.create("wip")
        other_project_id = str(self.generate_fixture_project("Other").id)
        self.create("wip", project_id=other_project_id)

        updated = self.put(
            f"{self.path}{row['id']}",
            {"name": "wip", "project_id": other_project_id},
        )

        self.assertEqual(updated["project_id"], project_id)

    def test_another_project_leaves_a_row_out_of_any_production(self):
        """
        Kitsu used to send the current production for the lists out of any
        production, which moved their rows.
        """
        row = self.create("wip", project_id=None)
        self.create("wip")

        updated = self.put(
            f"{self.path}{row['id']}", {"project_id": self.project_id}
        )

        self.assertIsNone(updated["project_id"])

    def test_a_null_project_leaves_a_row_where_it_is(self):
        """
        Kitsu sends one for the lists out of any production, whose rows
        also stay editable when they share their name.
        """
        self.create("wip", project_id=None)
        other = self.create("other", project_id=None)
        self.model.get(other["id"]).update({"name": "wip"})
        in_project = self.create("mine")

        updated = self.put(
            f"{self.path}{other['id']}", {"name": "wip", "project_id": None}
        )
        self.assertIsNone(updated["project_id"])

        updated = self.put(
            f"{self.path}{in_project['id']}", {"project_id": None}
        )
        self.assertEqual(updated["project_id"], self.project_id)

    def test_a_row_can_keep_a_name_it_already_shares(self):
        """
        The rows saved before the name check stay editable: Kitsu sends the
        name and the project with every other change.
        """
        self.create("wip")
        other = self.create("other")
        self.model.get(other["id"]).update({"name": "wip"})

        self.put(
            f"{self.path}{other['id']}",
            {
                "name": "wip",
                "project_id": self.project_id,
                "is_shared": False,
                "department_id": None,
            },
        )

    def test_a_project_of_no_row_is_refused(self):
        self.post(
            self.path, self.payload("wip", project_id=self.unknown_id), 404
        )

    def test_an_update_ignores_a_project_of_no_row(self):
        row = self.create("wip")

        updated = self.put(
            f"{self.path}{row['id']}", {"project_id": self.unknown_id}
        )

        self.assertEqual(updated["project_id"], self.project_id)

    def test_an_artist_gets_the_same_answer_for_a_project_of_no_row(self):
        self.log_in_cg_artist()

        self.post(
            self.path, self.payload("new", project_id=self.unknown_id), 404
        )

    def test_a_department_of_no_row_is_refused(self):
        self.post(
            self.path, self.payload("wip", department_id=self.unknown_id), 404
        )

    def test_setting_a_department_of_no_row_is_refused(self):
        row = self.create("wip")

        self.put(
            f"{self.path}{row['id']}", {"department_id": self.unknown_id}, 404
        )
        self.assertIsNone(self.model.get(row["id"]).department_id)

    def test_a_null_department_opens_the_row_to_the_team(self):
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
        self.put(f"{self.path}{scoped['id']}", {"department_id": None})

        self.assertIsNone(self.model.get(scoped["id"]).department_id)
        self.log_in_cg_artist()
        self.assertEqual(self.listed_names(), ["department", "team"])

    def test_a_body_without_a_department_keeps_it(self):
        row = self.create(
            "wip", is_shared=True, department_id=str(self.department.id)
        )

        self.put(f"{self.path}{row['id']}", {"name": "renamed"})

        self.assertEqual(
            str(self.model.get(row["id"]).department_id),
            str(self.department.id),
        )

    def a_shared_row_of(self, person, department_id):
        """
        Sharing takes a manager, but the owner can lose that role afterwards.
        """
        self.log_in_admin()
        row = self.create("wip", is_shared=True, department_id=department_id)
        self.model.get(row["id"]).update({"person_id": person["id"]})
        return f"{self.path}{row['id']}", row["id"]

    def test_a_department_change_is_ignored_without_the_right_to_share(self):
        animation = str(self.department_animation.id)
        self.put_join_the_team_and_the_department()
        path, row_id = self.a_shared_row_of(self.user_cg_artist, animation)
        self.log_in_cg_artist()

        self.put(path, {"department_id": None})
        self.assertEqual(self.department_of(row_id), animation)

        self.put(path, {"department_id": str(self.department.id)})
        self.assertEqual(self.department_of(row_id), animation)

        # The whole form, as Kitsu sends it.
        self.put(
            path,
            {
                "is_shared": True,
                "project_id": self.project_id,
                "department_id": None,
            },
        )
        self.assertEqual(self.department_of(row_id), animation)

    def test_the_rest_of_a_body_applies_without_the_right_to_share(self):
        animation = str(self.department_animation.id)
        self.put_join_the_team_and_the_department()
        path, row_id = self.a_shared_row_of(self.user_cg_artist, animation)
        self.log_in_cg_artist()

        self.put(path, {"name": "renamed", "department_id": None})

        self.assertEqual(self.model.get(row_id).name, "renamed")
        self.assertEqual(self.department_of(row_id), animation)

    def test_unsharing_drops_the_department_without_the_right_to_share(self):
        animation = str(self.department_animation.id)
        self.put_join_the_team_and_the_department()
        path, row_id = self.a_shared_row_of(self.user_cg_artist, animation)
        self.log_in_cg_artist()

        self.put(path, {"is_shared": False, "department_id": None})

        self.assertFalse(self.model.get(row_id).is_shared)
        self.assertIsNone(self.department_of(row_id))

    def test_a_private_row_takes_a_department_without_the_right_to_share(self):
        department_id = str(self.department.id)
        self.put_join_the_team_and_the_department()
        self.log_in_cg_artist()
        row = self.create("wip")

        self.put(f"{self.path}{row['id']}", {"department_id": department_id})

        self.assertEqual(self.department_of(row["id"]), department_id)

    def test_a_manager_of_the_project_changes_the_department(self):
        self.generate_fixture_user_manager()
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        path, row_id = self.a_shared_row_of(
            self.user_manager, str(self.department_animation.id)
        )
        self.log_in_manager()

        self.put(path, {"department_id": None})

        self.assertIsNone(self.department_of(row_id))

    def test_naming_a_project_of_the_caller_gives_no_right_on_the_row(self):
        animation = str(self.department_animation.id)
        self.generate_fixture_user_manager()
        path, row_id = self.a_shared_row_of(self.user_manager, animation)
        other_project_id = str(self.generate_fixture_project("Other").id)
        projects_service.add_team_member(
            other_project_id, self.user_manager["id"]
        )
        self.log_in_manager()

        self.put(path, {"project_id": other_project_id, "department_id": None})

        self.assertEqual(self.department_of(row_id), animation)

    def test_unsharing_drops_the_listing_of_the_team(self):
        self.log_in_admin()
        self.put_join_the_team_and_the_department()
        row = self.create("team", is_shared=True)
        self.log_in_cg_artist()
        self.assertEqual(self.visible_names(), ["team"])

        self.log_in_admin()
        self.put(f"{self.path}{row['id']}", {"is_shared": False})

        self.log_in_cg_artist()
        self.assertEqual(self.listed_names(), [])

    def test_an_admin_unsharing_a_row_drops_the_listing_of_its_owner(self):
        self.generate_fixture_user_manager()
        _, row_id = self.a_shared_row_of(self.user_manager, None)
        self.log_in_manager()
        self.clear_cache()
        listing = self.get(self.path)["asset"][self.project_id]
        self.assertTrue(listing[0]["is_shared"])

        self.log_in_admin()
        self.put(f"{self.path}{row_id}", {"is_shared": False})

        self.log_in_manager()
        listing = self.get(self.path)["asset"][self.project_id]
        self.assertFalse(listing[0]["is_shared"])

    def test_an_admin_renaming_a_row_drops_the_listing_of_its_owner(self):
        self.log_in_cg_artist()
        row = self.create("before")
        self.assertEqual(self.visible_names(), ["before"])

        self.log_in_admin()
        self.put(f"{self.path}{row['id']}", {"name": "after"})

        self.log_in_cg_artist()
        self.assertEqual(self.listed_names(), ["after"])

    def test_an_admin_removing_a_row_drops_the_listing_of_its_owner(self):
        self.log_in_cg_artist()
        row = self.create("gone")
        self.assertEqual(self.visible_names(), ["gone"])

        self.log_in_admin()
        self.delete(f"{self.path}{row['id']}")

        self.log_in_cg_artist()
        self.assertEqual(self.listed_names(), [])

    def test_a_new_row_drops_the_listing_of_its_owner(self):
        self.assertEqual(self.visible_names(), [])

        self.create("new")

        self.assertEqual(self.listed_names(), ["new"])

    def test_a_row_shared_for_the_first_time_takes_its_department(self):
        department_id = str(self.department.id)
        self.generate_fixture_user_manager()
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        self.log_in_manager()
        row = self.create("wip")

        self.put(
            f"{self.path}{row['id']}",
            {"is_shared": True, "department_id": department_id},
        )

        self.assertTrue(self.model.get(row["id"]).is_shared)
        self.assertEqual(self.department_of(row["id"]), department_id)

    def test_naming_a_project_of_the_caller_does_not_share_the_row(self):
        self.generate_fixture_user_manager()
        self.log_in_manager()
        row = self.create("wip")
        other_project_id = str(self.generate_fixture_project("Other").id)
        projects_service.add_team_member(
            other_project_id, self.user_manager["id"]
        )

        self.put(
            f"{self.path}{row['id']}",
            {"is_shared": True, "project_id": other_project_id},
        )

        self.assertFalse(self.model.get(row["id"]).is_shared)

    def test_naming_a_project_does_not_share_a_row_out_of_any_production(self):
        row = self.create("wip", project_id=None)

        updated = self.put(
            f"{self.path}{row['id']}",
            {"is_shared": True, "project_id": self.project_id},
        )

        self.assertFalse(updated["is_shared"])
        self.assertIsNone(updated["project_id"])


class SharedFilterTestCase(SharedFilterMixin, ApiDBTestCase):
    path = "data/user/filters/"
    detail_path = "data/search-filters/"
    model = SearchFilter

    def clear_cache(self):
        search_filters_service.clear_filter_cache()

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

    def a_group(self, name="group"):
        return self.post(
            "data/user/filter-groups/",
            {
                "list_type": "asset",
                "name": name,
                "project_id": self.project_id,
            },
        )

    def a_shared_group_with_a_filter(
        self, group_department, filter_department
    ):
        self.log_in_admin()
        self.put_join_the_team_and_the_department()
        group = self.post(
            "data/user/filter-groups/",
            {
                "list_type": "asset",
                "name": "group",
                "project_id": self.project_id,
                "is_shared": True,
                "department_id": group_department,
            },
        )
        row = self.create(
            "wip",
            is_shared=True,
            search_filter_group_id=group["id"],
            department_id=filter_department,
        )
        return f"data/user/filter-groups/{group['id']}", row["id"]

    def test_a_filter_follows_its_group_to_a_new_department(self):
        animation = str(self.department_animation.id)
        group_path, filter_id = self.a_shared_group_with_a_filter(
            animation, animation
        )

        self.put(group_path, {"department_id": str(self.department.id)})

        self.assertEqual(
            self.department_of(filter_id), str(self.department.id)
        )

    def test_a_filter_follows_its_group_into_a_first_department(self):
        group_path, filter_id = self.a_shared_group_with_a_filter(None, None)

        self.put(group_path, {"department_id": str(self.department.id)})

        self.assertEqual(
            self.department_of(filter_id), str(self.department.id)
        )

    def test_a_filter_follows_its_group_out_of_its_department(self):
        animation = str(self.department_animation.id)
        group_path, filter_id = self.a_shared_group_with_a_filter(
            animation, animation
        )
        # The artist belongs to self.department, not to this one. The listing
        # stays memoized from here on: the update has to clear it.
        self.log_in_cg_artist()
        self.assertEqual(self.visible_names(), [])

        self.log_in_admin()
        self.put(group_path, {"department_id": None})

        self.assertIsNone(self.department_of(filter_id))
        self.log_in_cg_artist()
        self.assertEqual(self.listed_names(), ["wip"])

    def test_a_filter_follows_its_group_and_stays_in_the_list_of_its_owner(
        self,
    ):
        group_path, filter_id = self.a_shared_group_with_a_filter(None, None)
        # Shared as a manager, by an owner who lost that role since.
        SearchFilter.get(filter_id).update(
            {"person_id": self.user_cg_artist["id"]}
        )

        self.put(
            group_path, {"department_id": str(self.department_animation.id)}
        )

        self.assertEqual(
            self.department_of(filter_id), str(self.department_animation.id)
        )
        self.log_in_cg_artist()
        self.assertEqual(self.visible_names(), ["wip"])

    def test_a_filter_leaves_the_department_of_a_group_no_longer_shared(self):
        animation = str(self.department_animation.id)
        group_path, filter_id = self.a_shared_group_with_a_filter(
            animation, animation
        )

        self.put(group_path, {"is_shared": False, "department_id": None})

        row = SearchFilter.get(filter_id)
        self.assertFalse(row.is_shared)
        self.assertIsNone(row.department_id)

    def test_unsharing_a_group_drops_the_listing_of_the_team(self):
        group_path, _ = self.a_shared_group_with_a_filter(None, None)
        self.log_in_cg_artist()
        self.assertEqual(self.visible_names(), ["wip"])

        self.log_in_admin()
        self.put(group_path, {"is_shared": False})

        self.log_in_cg_artist()
        self.assertEqual(self.listed_names(), [])

    def test_removing_a_group_drops_the_listing_of_the_team(self):
        group_path, _ = self.a_shared_group_with_a_filter(None, None)
        self.log_in_cg_artist()
        self.assertEqual(self.visible_names(), ["wip"])

        self.log_in_admin()
        self.delete(group_path)

        self.log_in_cg_artist()
        self.assertEqual(self.listed_names(), [])

    def test_a_filter_on_another_department_stays_on_it(self):
        group_path, filter_id = self.a_shared_group_with_a_filter(
            str(self.department_animation.id), str(self.department.id)
        )

        self.put(group_path, {"department_id": None})

        self.assertEqual(
            self.department_of(filter_id), str(self.department.id)
        )

    def test_a_filter_of_another_group_keeps_its_department(self):
        animation = str(self.department_animation.id)
        group_path, _ = self.a_shared_group_with_a_filter(animation, animation)
        other_group = self.post(
            "data/user/filter-groups/",
            {
                "list_type": "asset",
                "name": "other group",
                "project_id": self.project_id,
                "is_shared": True,
                "department_id": animation,
            },
        )
        other = self.create(
            "other",
            is_shared=True,
            search_filter_group_id=other_group["id"],
            department_id=animation,
        )

        self.put(group_path, {"department_id": None})

        self.assertEqual(self.department_of(other["id"]), animation)

    def test_a_filter_keeps_its_department_when_its_group_keeps_its_own(self):
        animation = str(self.department_animation.id)
        group_path, filter_id = self.a_shared_group_with_a_filter(
            animation, animation
        )

        self.put(group_path, {"name": "renamed"})

        self.assertEqual(self.department_of(filter_id), animation)

    def a_shared_group_on(self, department_id):
        self.log_in_admin()
        return self.post(
            "data/user/filter-groups/",
            {
                "list_type": "asset",
                "name": "group",
                "project_id": self.project_id,
                "is_shared": True,
                "department_id": department_id,
            },
        )["id"]

    def test_a_new_filter_takes_the_department_of_its_group(self):
        animation = str(self.department_animation.id)
        group_id = self.a_shared_group_on(animation)

        row = self.create(
            "wip", is_shared=True, search_filter_group_id=group_id
        )

        self.assertEqual(self.department_of(row["id"]), animation)

    def test_a_filter_joining_a_group_takes_its_department(self):
        animation = str(self.department_animation.id)
        group_id = self.a_shared_group_on(animation)
        row = self.create(
            "wip", is_shared=True, department_id=str(self.department.id)
        )

        # The whole form, as Kitsu sends it.
        self.put(
            f"{self.path}{row['id']}",
            {
                "search_filter_group_id": group_id,
                "department_id": str(self.department.id),
            },
        )

        self.assertEqual(self.department_of(row["id"]), animation)

    def test_a_group_without_department_leaves_the_filter_on_its_own(self):
        animation = str(self.department_animation.id)
        group_id = self.a_shared_group_on(None)
        row = self.create("wip", is_shared=True, department_id=animation)

        self.put(
            f"{self.path}{row['id']}",
            {"search_filter_group_id": group_id, "department_id": animation},
        )

        self.assertEqual(self.department_of(row["id"]), animation)

    def test_a_department_picked_with_the_group_is_kept(self):
        department_id = str(self.department.id)
        group_id = self.a_shared_group_on(str(self.department_animation.id))
        row = self.create("wip", is_shared=True)

        self.put(
            f"{self.path}{row['id']}",
            {
                "search_filter_group_id": group_id,
                "department_id": department_id,
            },
        )

        self.assertEqual(self.department_of(row["id"]), department_id)

    def test_a_group_gives_no_department_without_the_right_to_share(self):
        department_id = str(self.department.id)
        group_id = self.a_shared_group_on(str(self.department_animation.id))
        path, row_id = self.a_shared_row_of(self.user_cg_artist, department_id)
        self.log_in_cg_artist()

        updated = self.put(path, {"search_filter_group_id": group_id})

        self.assertEqual(updated["search_filter_group_id"], group_id)
        self.assertEqual(self.department_of(row_id), department_id)

    def test_a_name_used_in_the_group_is_refused(self):
        group_id = self.a_group()["id"]
        self.create("wip", search_filter_group_id=group_id)

        self.post(
            self.path,
            self.payload("wip", search_filter_group_id=group_id),
            400,
        )

    def test_a_name_stays_free_in_another_group(self):
        self.create("wip")
        self.create("wip", search_filter_group_id=self.a_group("one")["id"])
        self.create("wip", search_filter_group_id=self.a_group("two")["id"])

    def test_a_new_name_is_checked_in_the_group_of_the_row(self):
        group_id = self.a_group()["id"]
        self.create("out of the group")
        self.create("in the group", search_filter_group_id=group_id)
        row = self.create("mine", search_filter_group_id=group_id)

        path = f"{self.path}{row['id']}"
        self.put(path, {"name": "in the group"}, 400)
        self.put(path, {"name": "out of the group"})

    def test_a_new_name_is_checked_in_the_group_the_body_names(self):
        group_id = self.a_group()["id"]
        self.create("in the group", search_filter_group_id=group_id)
        row = self.create("mine")

        path = f"{self.path}{row['id']}"
        self.put(
            path,
            {"name": "in the group", "search_filter_group_id": group_id},
            400,
        )
        self.put(path, {"name": "in the group"})

    def test_a_new_name_is_checked_where_the_body_takes_the_row_out(self):
        group_id = self.a_group()["id"]
        self.create("out of the group")
        row = self.create("mine", search_filter_group_id=group_id)

        self.put(
            f"{self.path}{row['id']}",
            {"name": "out of the group", "search_filter_group_id": None},
            400,
        )

    def test_changing_group_under_the_same_name_is_accepted(self):
        """
        A duplicate made by taking a filter out of a group or by putting it
        in one does no harm: only a new name is checked.
        """
        group_id = self.a_group()["id"]
        self.create("wip")
        in_group = self.create("wip", search_filter_group_id=group_id)

        updated = self.put(
            f"{self.path}{in_group['id']}", {"search_filter_group_id": None}
        )
        self.assertIsNone(updated["search_filter_group_id"])

        updated = self.put(
            f"{self.path}{in_group['id']}",
            {"search_filter_group_id": group_id},
        )
        self.assertEqual(updated["search_filter_group_id"], group_id)

    def test_a_new_filter_cannot_join_a_group_of_another_project(self):
        group_id = self.a_group()["id"]
        other_project_id = str(self.generate_fixture_project("Other").id)

        for project_id in [other_project_id, None]:
            self.post(
                self.path,
                self.payload(
                    "wip",
                    project_id=project_id,
                    search_filter_group_id=group_id,
                ),
                400,
            )

    def test_a_filter_cannot_join_a_group_of_another_project(self):
        """
        Sharing a group takes a manager of its project, and its filters follow
        it: a filter of another project would reach a team beyond that right.
        """
        in_a_project = self.create("in a project")
        out_of_any = self.create("out of any", project_id=None)
        # The fixture moves self.project_id onto the new project.
        self.generate_fixture_project("Other")
        group_id = self.a_group()["id"]

        for row in [in_a_project, out_of_any]:
            self.put(
                f"{self.path}{row['id']}",
                {"search_filter_group_id": group_id},
                400,
            )
            self.assertIsNone(
                SearchFilter.get(row["id"]).search_filter_group_id
            )

    def test_a_filter_out_of_any_production_joins_a_group_out_of_any(self):
        group_id = self.post(
            "data/user/filter-groups/",
            {"list_type": "asset", "name": "group"},
        )["id"]
        self.create("new", project_id=None, search_filter_group_id=group_id)
        row = self.create("existing", project_id=None)

        updated = self.put(
            f"{self.path}{row['id']}", {"search_filter_group_id": group_id}
        )

        self.assertEqual(updated["search_filter_group_id"], group_id)

    def test_a_filter_already_in_a_group_of_another_project_stays_editable(
        self,
    ):
        """
        A group could move without its filters before this rule, and gazu
        sends the group of a filter back with every other change.
        """
        group_id = self.a_group()["id"]
        row = self.create("wip", search_filter_group_id=group_id)
        SearchFilterGroup.get(group_id).update(
            {"project_id": str(self.generate_fixture_project("Other").id)}
        )
        path = f"{self.path}{row['id']}"

        updated = self.put(
            path, {"name": "renamed", "search_filter_group_id": group_id}
        )
        self.assertEqual(updated["name"], "renamed")

        updated = self.put(path, {"search_filter_group_id": None})
        self.assertIsNone(updated["search_filter_group_id"])

        self.put(path, {"search_filter_group_id": group_id}, 400)

    def test_a_query_of_the_column_length_is_kept(self):
        self.create("long", query="q" * 500)
        self.assertEqual(self.visible_names(), ["long"])

    def test_a_query_longer_than_its_column_is_refused(self):
        self.post(self.path, self.payload("long", query="q" * 501), 400)
        self.assertEqual(self.visible_names(), [])

    def test_editing_a_query_beyond_the_column_length_is_refused(self):
        created = self.create("mine")
        self.put(
            f"{self.path}{created['id']}", {"search_query": "q" * 501}, 400
        )
        self.assertEqual(self.saved_query(), "props")

    def test_editing_a_query_to_nothing_is_refused(self):
        created = self.create("mine")
        self.put(f"{self.path}{created['id']}", {"search_query": ""}, 400)
        self.assertEqual(self.saved_query(), "props")

    def saved_query(self):
        self.clear_cache()
        result = self.get(self.path)
        return result["asset"][self.project_id][0]["search_query"]


class SharedFilterGroupTestCase(SharedFilterMixin, ApiDBTestCase):
    path = "data/user/filter-groups/"
    detail_path = "data/search-filter-groups/"
    model = SearchFilterGroup

    def clear_cache(self):
        search_filters_service.clear_filter_group_cache()

    def payload(self, name, **overrides):
        return {
            "list_type": "asset",
            "name": name,
            "color": "",
            "project_id": self.project_id,
            **overrides,
        }

    def test_a_color_of_the_column_length_is_kept(self):
        self.create("n", color="#ffffff0")
        self.assertEqual(self.visible_names(), ["n"])

    def test_a_color_longer_than_its_column_is_refused(self):
        self.post(self.path, self.payload("n", color="#ffffff00"), 400)
        self.assertEqual(self.visible_names(), [])

    def test_editing_a_color_beyond_the_column_length_is_refused(self):
        created = self.create("mine", color="#000000")
        self.put(f"{self.path}{created['id']}", {"color": "#ffffff00"}, 400)
        self.clear_cache()
        result = self.get(self.path)
        self.assertEqual(
            result["asset"][self.project_id][0]["color"], "#000000"
        )
