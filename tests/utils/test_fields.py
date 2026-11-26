import datetime
import unittest
import uuid
from enum import Enum

from babel import Locale
from pytz import timezone

from zou.app.models.person import Person
from zou.app.models.task import Task
from zou.app.utils import fields


class FieldsTestCase(unittest.TestCase):
    def test_serialize_value_keeps_the_fraction_of_a_round_second(self):
        round_second = datetime.datetime(2026, 10, 5, 17, 0, 9)
        self.assertEqual(
            fields.serialize_value(round_second, milliseconds=True),
            "2026-10-05T17:00:09.000000",
        )

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
        # A UUID followed by anything is not one: uuid.UUID() rejects it, so
        # letting it through turns a 400 into a database error.
        for suffix in ("\n", " ", "zz", "?x=1", "/download"):
            self.assertFalse(fields.is_valid_id(f"{unique_id}{suffix}"))

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

    def test_serialize_value_of_an_enum_is_its_value(self):
        Color = Enum("Color", {"RED": "red"})
        self.assertEqual(fields.serialize_value(Color.RED), "red")

    def test_get_default_date_object(self):
        self.assertEqual(
            fields.get_default_date_object("2026-10-05T17:00:09"),
            datetime.datetime(2026, 10, 5, 17, 0, 9),
        )
        self.assertIsNone(fields.get_default_date_object("2026-10-05"))
        self.assertIsNone(fields.get_default_date_object(""))

    def test_boolean(self):
        for value in ("true", "TRUE", "1", "on"):
            self.assertIs(fields.boolean(value), True)
        for value in ("false", "False", "0"):
            self.assertIs(fields.boolean(value), False)
        self.assertIs(fields.boolean(True), True)
        self.assertIs(fields.boolean(False), False)
        for value in ("", None, "yes", "off"):
            with self.assertRaises(ValueError):
                fields.boolean(value)
