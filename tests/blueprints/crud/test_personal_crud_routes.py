from tests.base import ApiDBTestCase

from zou.app.models.chat import Chat
from zou.app.models.news import News
from zou.app.models.notification import Notification
from zou.app.models.plugin import Plugin
from zou.app.models.production_schedule_version import (
    ProductionScheduleVersion,
    ProductionScheduleVersionTaskLink,
)
from zou.app.models.subscription import Subscription

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


class PersonalCrudInstanceRoutesTestCase(ApiDBTestCase):
    """
    The single item routes of the same tables. They are reached with an id,
    so they need a row to load: the lookup answers 404 before the permission
    hook ever runs, which is why the list tests above cannot stand in for
    them.
    """

    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.generate_fixture_asset()
        self.generate_fixture_person()
        self.generate_fixture_task()
        self.rows = self.build_one_row_per_table()

    def build_one_row_per_table(self):
        """
        The smallest row each table accepts, keyed by the route that reads
        it back.
        """
        person_id = self.person.id
        task_id = self.task.id
        schedule_version = ProductionScheduleVersion.create(
            name="v1", project_id=self.project.id
        )
        return {
            "data/chats": Chat.create(object_id=self.asset.id).id,
            "data/news": News.create(author_id=person_id, task_id=task_id).id,
            "data/notifications": Notification.create(
                type="comment", person_id=person_id, author_id=person_id
            ).id,
            "data/plugins": Plugin.create(
                plugin_id="test-plugin",
                name="Test plugin",
                version="1.0.0",
                maintainer_name="CGWire",
                license="AGPL-3.0",
            ).id,
            "data/production-schedule-version-task-links": (
                ProductionScheduleVersionTaskLink.create(
                    production_schedule_version_id=schedule_version.id,
                    task_id=task_id,
                ).id
            ),
            "data/subscriptions": Subscription.create(
                person_id=person_id, task_id=task_id
            ).id,
        }

    def test_admin_can_read_one(self):
        for path, instance_id in self.rows.items():
            with self.subTest(path=path):
                result = self.get(f"{path}/{instance_id}")
                self.assertEqual(result["id"], str(instance_id))

    def test_instance_routes_are_admin_only(self):
        self.generate_fixture_user_manager()
        self.log_in_manager()
        for path, instance_id in self.rows.items():
            with self.subTest(path=path):
                self.get(f"{path}/{instance_id}", 403)
