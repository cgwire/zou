from tests.base import ApiDBTestCase

# Generic crud routes over tables that hold per person rows, or the studio
# plugin list. None of them overrides a permission hook, so they all inherit
# the admin only default of BaseModelsResource. That inheritance is the whole
# policy: a hook added later on one of them would silently open the table.
PERSONAL_CRUD_ROUTES = [
    "data/chats",
    "data/news",
    "data/notifications",
    "data/plugins",
    "data/production-schedule-version-task-links",
    "data/subscriptions",
]


class PersonalCrudRoutesTestCase(ApiDBTestCase):

    def test_admin_can_list(self):
        for path in PERSONAL_CRUD_ROUTES:
            with self.subTest(path=path):
                self.assertIsInstance(self.get(path), list)

    def test_routes_are_admin_only(self):
        self.generate_fixture_user_manager()
        self.log_in_manager()
        for path in PERSONAL_CRUD_ROUTES:
            with self.subTest(path=path):
                self.get(path, 403)
