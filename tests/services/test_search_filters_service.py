from zou.app.models.search_filter import SearchFilter
from zou.app.models.search_filter_group import SearchFilterGroup
from zou.app.services import (
    projects_service,
    search_filters_service,
    cascade_deletion_service,
)
from zou.app.exceptions import (
    DepartmentNotFoundException,
    SearchFilterNotFoundException,
    SearchFilterGroupNotFoundException,
    WrongParameterException,
)
from tests.services.cases import UserContextTestCase

UNKNOWN = "00000000-0000-0000-0000-000000000000"


class SavedSearchTestCase(UserContextTestCase):
    """
    One production, one department and the people the saved searches are
    read as. Holds no test of its own.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_department()
        self.generate_fixture_user_manager()
        self.generate_fixture_user_cg_artist()
        self.project_id = str(self.project.id)
        self.department_id = str(self.department.id)

    def a_filter(self, name="mine", **kwargs):
        kwargs.setdefault("project_id", self.project_id)
        return search_filters_service.create_filter(
            "shot", name, '{"status": "wip"}', **kwargs
        )

    def a_group(self, name="group", **kwargs):
        kwargs.setdefault("project_id", self.project_id)
        return search_filters_service.create_filter_group(
            "shot", name, "#000000", **kwargs
        )

    def filters_of(self, user):
        with self.as_user(user):
            return search_filters_service.get_filters()


class SearchFilterTestCase(SavedSearchTestCase):
    """
    The saved searches of the side panel. A filter belongs to one person
    unless a manager of the production shares it with the team, and the
    listing is memoized per person, so who may see what and when the cache
    is dropped are the same question.
    """

    def test_get_filters_groups_by_list_type_and_production(self):
        with self.as_user():
            self.a_filter("with a production")
            self.a_filter("without one", project_id=None)

            result = search_filters_service.get_filters()

        self.assertEqual(list(result), ["shot"])
        self.assertEqual(
            {
                key: [held["name"] for held in value]
                for key, value in result["shot"].items()
            },
            {
                self.project_id: ["with a production"],
                # A filter that belongs to no production is filed under
                # "all", which is what the panel shows everywhere.
                "all": ["without one"],
            },
        )

    def test_a_private_filter_belongs_to_its_owner_alone(self):
        with self.as_user():
            self.a_filter()

        self.assertEqual(self.filters_of(self.user_cg_artist), {})

    def test_a_shared_filter_is_visible_to_the_whole_team(self):
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )

        with self.as_user(self.user_manager):
            self.a_filter("shared", is_shared=True)

        self.assertEqual(
            [
                held["name"]
                for held in self.filters_of(self.user_cg_artist)["shot"][
                    self.project_id
                ]
            ],
            ["shared"],
        )

    def test_sharing_needs_manager_access_to_the_production(self):
        # Silently turned off rather than refused: the filter is created,
        # private.
        with self.as_user(self.user_cg_artist):
            search_filter = self.a_filter("wanted shared", is_shared=True)

        self.assertFalse(search_filter["is_shared"])

    def test_a_filter_of_no_production_cannot_be_shared(self):
        with self.as_user():
            search_filter = self.a_filter(
                "global", project_id=None, is_shared=True
            )

        self.assertFalse(search_filter["is_shared"])

    def test_a_filter_of_a_closed_production_is_left_out(self):
        with self.as_user():
            self.a_filter()

            projects_service.update_project(
                self.project_id,
                {
                    "project_status_id": projects_service.get_closed_status()[
                        "id"
                    ]
                },
            )
            search_filters_service.clear_filter_cache()

            self.assertEqual(search_filters_service.get_filters(), {})

    def test_a_department_filter_is_held_to_that_department(self):
        """
        A filter can be narrowed to a department: only its members see it,
        managers excepted.
        """
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        with self.as_user(self.user_manager):
            self.a_filter(
                "rigging only",
                is_shared=True,
                department_id=self.department_id,
            )

        self.assertEqual(self.filters_of(self.user_cg_artist), {})
        self.assertIn("shot", self.filters_of(self.user_manager))

    def test_a_department_filter_reaches_the_members_of_it(self):
        from zou.app.services import persons_service

        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        with self.as_user(self.user_manager):
            self.a_filter(
                "rigging only",
                is_shared=True,
                department_id=self.department_id,
            )
        persons_service.add_to_department(
            self.department_id, self.user_cg_artist["id"]
        )

        self.assertIn("shot", self.filters_of(self.user_cg_artist))

    def test_create_filter_refuses_a_department_that_is_not_there(self):
        # The WrongParameterException the service raises next to this one
        # is unreachable: get_department raises rather than answering None.
        with self.as_user():
            with self.assertRaises(DepartmentNotFoundException):
                self.a_filter(department_id=UNKNOWN)

    def test_a_filter_and_its_group_agree_on_being_shared(self):
        with self.as_user():
            group = search_filters_service.create_filter_group(
                "shot", "group", "#000000", project_id=self.project_id
            )

            with self.assertRaises(WrongParameterException):
                self.a_filter(
                    is_shared=True, search_filter_group_id=group["id"]
                )
            with self.assertRaises(SearchFilterGroupNotFoundException):
                self.a_filter(search_filter_group_id=UNKNOWN)

    def test_update_filter(self):
        with self.as_user():
            search_filter = self.a_filter()

            updated = search_filters_service.update_filter(
                search_filter["id"], {"name": "renamed"}
            )

        self.assertEqual(updated["name"], "renamed")

    def test_update_filter_cannot_share_without_manager_access(self):
        with self.as_user(self.user_cg_artist):
            search_filter = self.a_filter()

            updated = search_filters_service.update_filter(
                search_filter["id"], {"is_shared": True}
            )

        self.assertFalse(updated["is_shared"])

    def test_a_filter_of_someone_else_is_out_of_reach(self):
        with self.as_user():
            search_filter = self.a_filter()

        with self.as_user(self.user_cg_artist):
            with self.assertRaises(SearchFilterNotFoundException):
                search_filters_service.update_filter(
                    search_filter["id"], {"name": "stolen"}
                )
            with self.assertRaises(SearchFilterNotFoundException):
                search_filters_service.remove_filter(search_filter["id"])

    def test_an_admin_reaches_a_filter_of_someone_else(self):
        with self.as_user(self.user_cg_artist):
            search_filter = self.a_filter()

        with self.as_user():
            self.assertEqual(
                search_filters_service.remove_filter(search_filter["id"])[
                    "id"
                ],
                search_filter["id"],
            )

    def test_remove_filter(self):
        with self.as_user():
            search_filter = self.a_filter()

            search_filters_service.remove_filter(search_filter["id"])

            self.assertEqual(search_filters_service.get_filters(), {})

    def test_sharing_a_filter_drops_the_listing_of_everyone(self):
        """
        The listing is memoized per person. A private filter only changes
        its owner's, but a shared one changes the whole team's, so theirs
        has to go too.
        """
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )
        # Warm the artist's listing before the manager shares anything.
        self.assertEqual(self.filters_of(self.user_cg_artist), {})

        with self.as_user(self.user_manager):
            self.a_filter("shared", is_shared=True)

        self.assertIn("shot", self.filters_of(self.user_cg_artist))


class SearchFilterGroupTestCase(SavedSearchTestCase):
    """
    A group of saved searches. update_filter refuses a filter whose
    is_shared differs from its group's, so the two are one state: whatever
    moves the group has to move the filters it holds, or they can never be
    written to again.
    """

    def setUp(self):
        super().setUp()
        projects_service.add_team_member(
            self.project_id, self.user_manager["id"]
        )

    def a_shared_group_holding_a_filter(self):
        group = self.a_group(is_shared=True)
        search_filter = self.a_filter(
            is_shared=True, search_filter_group_id=group["id"]
        )
        return group, search_filter

    def sharings(self, group, search_filter):
        return (
            SearchFilterGroup.get(group["id"]).is_shared,
            SearchFilter.get(search_filter["id"]).is_shared,
        )

    def test_get_filter_group(self):
        with self.as_user():
            group = self.a_group()

            self.assertEqual(
                search_filters_service.get_filter_group(group["id"]), group
            )
            with self.assertRaises(SearchFilterGroupNotFoundException):
                search_filters_service.get_filter_group(UNKNOWN)

    def test_a_group_of_someone_else_is_out_of_reach(self):
        with self.as_user():
            group = self.a_group()

        with self.as_user(self.user_cg_artist):
            with self.assertRaises(SearchFilterGroupNotFoundException):
                search_filters_service.get_filter_group(group["id"])
            with self.assertRaises(SearchFilterGroupNotFoundException):
                search_filters_service.update_filter_group(
                    group["id"], {"name": "his"}
                )
            with self.assertRaises(SearchFilterGroupNotFoundException):
                search_filters_service.remove_filter_group(group["id"])

    def test_an_admin_reaches_a_group_of_someone_else(self):
        with self.as_user(self.user_cg_artist):
            group = self.a_group()

        with self.as_user():
            self.assertEqual(
                search_filters_service.get_filter_group(group["id"])["id"],
                group["id"],
            )

    def test_update_filter_group(self):
        with self.as_user():
            group = self.a_group()

            renamed = search_filters_service.update_filter_group(
                group["id"], {"name": "renamed", "color": "#FFFFFF"}
            )
        self.assertEqual(renamed["name"], "renamed")
        self.assertEqual(renamed["color"], "#FFFFFF")

    def test_update_filter_group_cannot_share_without_manager_access(self):
        with self.as_user(self.user_cg_artist):
            group = self.a_group()

            shared = search_filters_service.update_filter_group(
                group["id"],
                {"is_shared": True, "project_id": self.project_id},
            )
        self.assertFalse(shared["is_shared"])

    def test_sharing_a_group_shares_the_filters_it_holds(self):
        with self.as_user(self.user_manager):
            group = self.a_group()
            search_filter = self.a_filter(search_filter_group_id=group["id"])
            self.assertEqual(
                self.sharings(group, search_filter), (False, False)
            )

            search_filters_service.update_filter_group(
                group["id"],
                {"is_shared": True, "project_id": self.project_id},
            )
        self.assertEqual(self.sharings(group, search_filter), (True, True))

    def test_unsharing_a_group_unshares_them_too(self):
        """
        A client that only sends the field it changed leaves project_id out.
        The cascade used to hang on it, so the group turned private while
        its filters stayed shared: still visible to the whole team, and
        refused by update_filter from then on, whatever the change.
        """
        with self.as_user(self.user_manager):
            group, search_filter = self.a_shared_group_holding_a_filter()
            self.assertEqual(self.sharings(group, search_filter), (True, True))

            search_filters_service.update_filter_group(
                group["id"], {"is_shared": False}
            )

            self.assertEqual(
                self.sharings(group, search_filter), (False, False)
            )
            renamed = search_filters_service.update_filter(
                search_filter["id"], {"name": "renamed"}
            )
        self.assertEqual(renamed["name"], "renamed")

    def test_remove_filter_group_takes_its_filters_with_it(self):
        with self.as_user(self.user_manager):
            group, search_filter = self.a_shared_group_holding_a_filter()

            search_filters_service.remove_filter_group(group["id"])

            with self.assertRaises(SearchFilterGroupNotFoundException):
                search_filters_service.get_filter_group(group["id"])
        self.assertIsNone(SearchFilter.get(search_filter["id"]))

    def test_removing_the_owner_of_a_group_drops_its_filters_everywhere(self):
        """
        Removing a person takes their groups with them, and the filters
        those hold whoever owns them. The listings are memoized per person:
        every one showing such a filter has to go.
        """
        with self.as_user(self.user_manager):
            group = self.a_group(is_shared=True)
        with self.as_user():
            self.a_filter(is_shared=True, search_filter_group_id=group["id"])
        # Warm the admin's listing before the removal.
        self.assertIn("shot", self.filters_of(self.user))

        cascade_deletion_service.remove_person(self.user_manager["id"])

        self.assertEqual(self.filters_of(self.user), {})
