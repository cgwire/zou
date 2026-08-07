import datetime
import unittest
import uuid

from babel import Locale
from pytz import timezone

from zou.app.utils import fields
from zou.app.models.person import Person
from zou.app.models.task import Task


class FieldsTestCase(unittest.TestCase):
    def test_serialize_value(self):
        now = datetime.datetime.now()
        self.assertEqual(
            now.replace(microsecond=0).isoformat(), fields.serialize_value(now)
        )
        unique_id = uuid.uuid4()
        self.assertEqual(str(unique_id), fields.serialize_value(unique_id))
        self.assertEqual(
            {"now": now.replace(microsecond=0).isoformat()},
            fields.serialize_value({"now": now}),
        )
        self.assertEqual(
            "Europe/Paris", fields.serialize_value(timezone("Europe/Paris"))
        )
        self.assertEqual(
            "Europe/Brussels",
            fields.serialize_value(timezone("Europe/Brussels")),
        )
        self.assertEqual("en_US", fields.serialize_value(Locale("en_US")))

    def test_serialize_dict(self):
        now = datetime.datetime.now()
        unique_id = uuid.uuid4()

        data = {"now": now, "unique_id": unique_id, "string": "test"}
        result = {
            "now": now.replace(microsecond=0).isoformat(),
            "unique_id": str(unique_id),
            "string": "test",
        }
        self.assertEqual(fields.serialize_dict(data), result)
        self.assertEqual(fields.serialize_value(data), result)

    def test_is_valid_id(self):
        unique_id = uuid.uuid4()
        self.assertTrue(fields.is_valid_id(str(unique_id)))
        self.assertTrue(fields.is_valid_id(unique_id))
        self.assertFalse(fields.is_valid_id("undefined"))
        self.assertFalse(fields.is_valid_id(None))

    def test_serialize_orm_array(self):
        person = Person(id=uuid.uuid4(), first_name="Jhon", last_name="Doe")
        person2 = Person(id=uuid.uuid4(), first_name="Emma", last_name="Peel")
        task = Task(
            id=uuid.uuid4(), name="Test Task", assignees=[person, person2]
        )

        is_id = str(person.id) in fields.serialize_orm_arrays(task.assignees)
        self.assertTrue(is_id)
        is_id = str(person2.id) in fields.serialize_orm_arrays(task.assignees)
        self.assertTrue(is_id)
        is_id = str(person.id) in fields.serialize_value(task.assignees)
        self.assertTrue(is_id)
        is_id = str(person2.id) in fields.serialize_value(task.assignees)
        self.assertTrue(is_id)
