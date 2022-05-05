# -*- coding: UTF-8 -*-
from tests.base import ApiDBTestCase
from zou.app.models.department import Department
from zou.app.models.person import Person

from zou.app.utils import fields


class PersonTestCase(ApiDBTestCase):
    def setUp(self):
        super(PersonTestCase, self).setUp()
        self.generate_fixture_person(
            first_name="Ema",
            last_name="Doe",
            desktop_login="ema.doe",
            email="ema.doe@gmail.com",
        )
        self.generate_fixture_person(
            first_name="Jérémy",
            last_name="Utêfœuit",
            desktop_login="jeremy.utf8",
            email="jeremy.utf8@gmail.com",
        )
        self.generate_fixture_person()

    def test_repr(self):
        self.assertEqual(str(self.person), "<Person John Doe>")
        self.person.first_name = "Léon"
        self.assertEqual(str(self.person), "<Person Léon Doe>")

    def test_get_persons(self):
        persons = self.get("data/persons")
        self.assertEqual(len(persons), 4)
        self.assertEqual(persons[0]["type"], "Person")

    def test_get_person(self):
        person = self.get_first("data/persons")
        person_again = self.get("data/persons/%s" % person["id"])
        del person["departments"]
        self.assertEqual(person, person_again)
        self.get_404("data/persons/%s" % fields.gen_uuid())

    def test_create_person(self):
        data = {
            "first_name": "John2",
            "last_name": "Doe",
            "email": "john2.doe@gmail.com",
        }
        self.person = self.post("data/persons/new", data)
        self.assertIsNotNone(self.person["id"])

        persons = self.get("data/persons")
        self.assertEqual(len(persons), 5)

    def test_create_too_much_person(self):
        from zou.app import config

        config.USER_LIMIT = 4
        data = {
            "first_name": "John3",
            "last_name": "Doe",
            "email": "john3.doe@gmail.com",
        }
        resp = self.post("data/persons/new", data, 400)
        self.assertEqual(resp["limit"], 4)
        config.USER_LIMIT = 100

    def test_create_person_with_no_data(self):
        data = {}
        self.person = self.post("data/persons/new", data, 400)

    def test_create_person_with_wrong_data(self):
        data = {
            "name": "John Doe",
            "first_name": "John",
            "last_name": "Doe",
        }
        self.person = self.post("data/persons/new", data, 400)

    def test_create_person_with_departments(self):
        self.generate_fixture_department()
        departments = [
            str(department.id) for department in Department.query.all()
        ]
        data = {
            "first_name": "John2",
            "last_name": "Doe",
            "email": "john2.doe@gmail.com",
            "departments": departments,
        }
        person = self.post("data/persons/new", data)
        self.assertIsNotNone(person["id"])
        self.assertEqual(
            set(person["departments"]),
            set(departments),
        )

        created_person = Person.get(person["id"])
        self.assertEqual(
            set(
                str(department.id) for department in created_person.departments
            ),
            set(departments),
        )

    def test_update_person(self):
        person = self.get_first("data/persons")
        data = {
            "first_name": "Johnny",
        }
        self.put("data/persons/%s" % person["id"], data)
        person_again = self.get("data/persons/%s" % person["id"])
        self.assertEqual(data["first_name"], person_again["first_name"])
        self.put_404("data/persons/%s" % fields.gen_uuid(), data)

    def test_update_person_with_departments(self):
        self.generate_fixture_department()
        person = self.get_first("data/persons")
        departments = [
            str(department.id) for department in Department.query.all()
        ]
        data = {
            "first_name": "Johnny",
            "departments": departments,
        }
        self.put("data/persons/%s" % person["id"], data)
        person_again = Person.get(person["id"])
        self.assertEqual(
            set(str(department.id) for department in person_again.departments),
            set(departments),
        )

    def test_set_active_when_too_much_person(self):
        from zou.app import config

        config.USER_LIMIT = 3
        persons = self.get("data/persons")
        person = [
            person for person in persons if person["id"] != self.user["id"]
        ][0]
        data = {"active": False}
        self.put("data/persons/%s" % person["id"], data, 200)
        data = {"active": True}
        self.put("data/persons/%s" % person["id"], data, 400)
        config.USER_LIMIT = 100
        data = {"active": True}
        self.put("data/persons/%s" % person["id"], data)

    def test_delete_person(self):
        persons = self.get("data/persons")
        self.assertEqual(len(persons), 4)

        person = persons[1]
        self.delete("data/persons/%s" % person["id"])
        persons = self.get("data/persons")
        self.assertEqual(len(persons), 3)

        self.delete_404("data/persons/%s" % fields.gen_uuid())
        persons = self.get("data/persons")
        self.assertEqual(len(persons), 3)

    def test_force_delete(self):
        self.generate_fixture_task_status_todo()
        self.generate_shot_suite()
        self.generate_assigned_task()
        self.generate_fixture_comment()
        self.person_id = str(self.person.id)
        self.get("data/persons/%s" % self.person_id)
        self.delete("data/persons/%s" % self.person_id, 400)
        self.delete("data/persons/%s?force=true" % self.person_id)
        self.get("data/persons/%s" % self.person_id, 404)
