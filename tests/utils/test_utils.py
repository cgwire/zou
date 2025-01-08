import os
import datetime
import pytest
import unittest
import uuid

from babel import Locale
from pytz import timezone

from zou.app.utils import colors, fields, query, fs, shell, date_helpers, redis
from zou.app.models.person import Person
from zou.app.models.task import Task
from zou.app import config


class UtilsTestCase(unittest.TestCase):
    def test_rgb_to_hex(self):
        self.assertEqual(colors.rgb_to_hex("0,0,0"), "#000000")
        self.assertEqual(colors.rgb_to_hex("255,255,255"), "#ffffff")

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

    def test_get_query_criterions(self):
        request = type("test", (object,), {})()
        request.args = {"page": "1", "name": "Test", "project_id": "1234"}
        criterions = query.get_query_criterions_from_request(request)
        self.assertDictEqual(
            criterions, {"name": "Test", "project_id": "1234"}
        )

    def test_mkdirp(self):
        folder = "one/two/three"
        fs.mkdir_p(folder)
        self.assertTrue(os.path.exists(folder))
        fs.rm_rf("one")
        self.assertTrue(not os.path.exists(folder))

    def test_run_command(self):
        out = shell.run_command(["ls"])
        self.assertTrue(len(out) > 0)
        with pytest.raises(shell.ShellCommandFailed):
            shell.run_command(["nonexist"])

    def test_date(self):
        date_string = date_helpers.get_date_string_with_timezone(
            "2021-02-10T12:00:00", "Europe/Paris"
        )
        self.assertEqual(date_string, "2021-02-10T13:00:00")

        date_string = date_helpers.get_simple_string_with_timezone_from_date(
            datetime.datetime(2021, 2, 10, 23, 30, 0), "Europe/Paris"
        )
        self.assertEqual(date_string, "2021-02-11")

        date_obj = date_helpers.get_date_from_string("2021-02-10")
        self.assertEqual(date_obj.strftime("%Y-%m-%d"), "2021-02-10")

        start, end = date_helpers.get_year_interval(2021)
        self.assertEqual(start.strftime("%Y-%m-%d"), "2021-01-01")
        self.assertEqual(end.strftime("%Y-%m-%d"), "2022-01-01")

        start, end = date_helpers.get_month_interval(2021, 2)
        self.assertEqual(start.strftime("%Y-%m-%d"), "2021-02-01")
        self.assertEqual(end.strftime("%Y-%m-%d"), "2021-03-01")

        start, end = date_helpers.get_week_interval(2021, 30)
        self.assertEqual(start.strftime("%Y-%m-%d"), "2021-07-26")
        self.assertEqual(end.strftime("%Y-%m-%d"), "2021-08-02")

        start, end = date_helpers.get_day_interval(2021, 2, 10)
        self.assertEqual(start.strftime("%Y-%m-%d"), "2021-02-10")
        self.assertEqual(end.strftime("%Y-%m-%d"), "2021-02-11")

    def test_get_redis_url(self):
        db_index = 0
        self.assertEqual(
            redis.get_redis_url(db_index),
            f"redis://{config.KEY_VALUE_STORE['host']}:{config.KEY_VALUE_STORE['port']}/{db_index}",
        )
        config.KEY_VALUE_STORE["password"] = "password"
        self.assertEqual(
            redis.get_redis_url(db_index),
            f"redis://:{config.KEY_VALUE_STORE['password']}@{config.KEY_VALUE_STORE['host']}:{config.KEY_VALUE_STORE['port']}/{db_index}",
        )
