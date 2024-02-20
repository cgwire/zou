import datetime

from tests.base import ApiDBTestCase

from zou.app.utils import commands
from zou.app.stores import auth_tokens_store
from zou.app.models.entity_type import EntityType
from zou.app.models.task_type import TaskType


def totimestamp(dt, epoch=datetime.datetime(1970, 1, 1)):
    td = dt - epoch
    return (td.microseconds + (td.seconds + td.days * 86400) * 10**6) / 10**6


class CommandsTestCase(ApiDBTestCase):
    def setUp(self):
        super(CommandsTestCase, self).setUp()
        self.store = auth_tokens_store
        self.store.clear()

    def test_clean_auth_tokens_revoked(self):
        self.store.add("testkey", "false")
        self.store.add("testkey2", "false")
        self.assertEqual(len(self.store.keys()), 2)
        self.store.add("testkey2", "true")
        commands.clean_auth_tokens()
        self.assertEqual(len(self.store.keys()), 1)
        self.assertEqual(self.store.keys()[0], "testkey")

    def test_init_data(self):
        commands.init_data()
        task_types = TaskType.get_all()
        entity_types = EntityType.get_all()
        self.assertEqual(len(task_types), 12)
        self.assertEqual(len(entity_types), 8)
