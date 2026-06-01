# -*- coding: UTF-8 -*-
from tests.base import ApiDBTestCase
from zou.app.models.department import Department
from zou.app.models.person import Person

from zou.app.utils import fields

from operator import itemgetter


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

    def test_present(self):
        person = self.get_first("data/persons")
        person_model = Person.get(person["id"])
        person_dict = person_model.present_minimal()
        self.assertEqual(person_dict["departments"], [])
        person_dict = person_model.present_minimal(relations=True)
        self.assertEqual(person_dict["departments"], [])

    def test_get_person(self):
        person = self.get_first("data/persons")
        person_again = self.get(f"data/persons/{person['id']}?relations=false")
        self.assertEqual(person, person_again)
        person_with_relations = self.get(
            f"data/persons/{person['id']}?relations=true"
        )
        self.assertTrue("departments" in person_with_relations)
        self.get_404(f"data/persons/{fields.gen_uuid()}")

    def test_create_person(self):
        data = {
            "first_name": "John2",
            "last_name": "Doe",
            "email": "john3.doe@gmail.com",
        }
        self.person = self.post("data/persons", data)
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
        resp = self.post("data/persons", data, 400)
        self.assertEqual(resp["data"]["limit"], 4)
        config.USER_LIMIT = 100

    def test_create_person_with_no_data(self):
        data = {}
        self.person = self.post("data/persons", data, 400)

    def test_create_person_with_wrong_data(self):
        data = {
            "name": "John Doe",
            "first_name": "John",
            "last_name": "Doe",
        }
        self.person = self.post("data/persons", data, 400)

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

        person = self.post("data/persons", data)
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

    def test_create_person_with_duplicate_email(self):
        data = {
            "first_name": "John2",
            "last_name": "Doe",
            "email": "ema.doe@gmail.com",
        }
        response = self.post("data/persons", data, 400)
        self.assertIn("Email already in use", response["message"])

    def test_create_bot_can_share_email_with_person(self):
        data = {
            "first_name": "Bot",
            "last_name": "Bot",
            "email": "ema.doe@gmail.com",
            "is_bot": True,
        }
        person = self.post("data/persons", data)
        self.assertIsNotNone(person["id"])

    def test_update_person(self):
        person = self.get_first("data/persons")
        data = {
            "first_name": "Johnny",
        }
        self.put(f"data/persons/{person['id']}", data)
        person_again = self.get(f"data/persons/{person['id']}")
        self.assertEqual(data["first_name"], person_again["first_name"])
        self.put_404(f"data/persons/{fields.gen_uuid()}", data)

    def test_person_country_round_trip(self):
        data = {
            "first_name": "Country",
            "last_name": "Tester",
            "email": "country.tester@gmail.com",
            "country": "fr",  # lower-case input is normalized to "FR"
        }
        person = self.post("data/persons", data)
        self.assertEqual(person["country"], "FR")

        person_again = self.get(f"data/persons/{person['id']}")
        self.assertEqual(person_again["country"], "FR")
        person_with_relations = self.get(
            f"data/persons/{person['id']}?relations=true"
        )
        self.assertEqual(person_with_relations["country"], "FR")
        listed = next(
            p for p in self.get("data/persons") if p["id"] == person["id"]
        )
        self.assertEqual(listed["country"], "FR")

        self.put(f"data/persons/{person['id']}", {"country": "us"})
        person_again = self.get(f"data/persons/{person['id']}")
        self.assertEqual(person_again["country"], "US")

        self.put(f"data/persons/{person['id']}", {"country": None})
        person_again = self.get(f"data/persons/{person['id']}")
        self.assertIsNone(person_again["country"])

        self.put(f"data/persons/{person['id']}", {"country": ""})
        person_again = self.get(f"data/persons/{person['id']}")
        self.assertIsNone(person_again["country"])

    def test_create_person_without_country(self):
        data = {
            "first_name": "NoCountry",
            "last_name": "Doe",
            "email": "no.country@gmail.com",
        }
        person = self.post("data/persons", data)
        self.assertIsNone(person["country"])

    def test_create_person_with_invalid_country(self):
        data = {
            "first_name": "Bad",
            "last_name": "Country",
            "email": "bad.country@gmail.com",
            "country": "France",
        }
        self.post("data/persons", data, 400)

    def test_update_person_with_invalid_country(self):
        person = self.get_first("data/persons")
        self.put(f"data/persons/{person['id']}", {"country": "xyz"}, 400)
        self.put(f"data/persons/{person['id']}", {"country": "f1"}, 400)

    def test_update_person_country_is_normalized(self):
        person = self.get_first("data/persons")
        self.put(f"data/persons/{person['id']}", {"country": " fr "})
        person_again = self.get(f"data/persons/{person['id']}")
        self.assertEqual(person_again["country"], "FR")

    def test_update_person_with_non_ascii_country(self):
        person = self.get_first("data/persons")
        # Two non-ASCII letters must be rejected (isascii guard).
        self.put(f"data/persons/{person['id']}", {"country": "éé"}, 400)

    def test_update_person_with_non_string_country(self):
        # A non-string body (int, or a single-element list as produced by a
        # SAML assertion) must yield a clean 400, not a 500.
        person = self.get_first("data/persons")
        self.put(f"data/persons/{person['id']}", {"country": 123}, 400)
        self.put(f"data/persons/{person['id']}", {"country": ["FR"]}, 400)

    def test_country_validator_never_raises_on_direct_write(self):
        # Direct writes (SSO sign-in, imports, scripts) bypass the API guard,
        # so the model validator must silently discard bad input instead of
        # raising.
        person = Person.get_by(email="ema.doe@gmail.com")
        person.update({"country": ["FR"]})
        self.assertIsNone(person.country)
        person.update({"country": 123})
        self.assertIsNone(person.country)
        person.update({"country": "FRA"})
        self.assertIsNone(person.country)
        person.update({"country": " us "})
        self.assertEqual(person.country, "US")

    def test_country_not_exposed_in_present_minimal(self):
        # The minimal representation is served to non-managers (including
        # external client/vendor roles), so it must not leak the country.
        person = Person.get_by(email="ema.doe@gmail.com")
        person.update({"country": "FR"})
        self.assertNotIn("country", person.present_minimal())
        safe = person.serialize_safe()
        self.assertEqual(safe["country"], "FR")

    def test_update_person_with_duplicate_email(self):
        persons = sorted(self.get("data/persons"), key=itemgetter("email"))
        target = persons[0]
        other = next(p for p in persons if p["id"] != target["id"])
        response = self.put(
            f"data/persons/{target['id']}",
            {"email": other["email"]},
            400,
        )
        self.assertIn("Email already in use", response["message"])

    def test_update_person_keep_own_email(self):
        person = self.get_first("data/persons")
        self.put(
            f"data/persons/{person['id']}",
            {"email": person["email"], "first_name": "Johnny"},
        )
        person_again = self.get(f"data/persons/{person['id']}")
        self.assertEqual(person_again["first_name"], "Johnny")
        self.assertEqual(person_again["email"], person["email"])

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
        self.put(f"data/persons/{person['id']}", data)
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
        self.put(f"data/persons/{person['id']}", data, 200)
        data = {"active": True}
        self.put(f"data/persons/{person['id']}", data, 400)
        config.USER_LIMIT = 100
        data = {"active": True}
        self.put(f"data/persons/{person['id']}", data)

    def test_delete_person(self):
        persons = self.get("data/persons")
        self.assertEqual(len(persons), 4)
        persons = sorted(persons, key=itemgetter("email"))
        person = persons[1]
        self.delete(f"data/persons/{person['id']}")
        persons = self.get("data/persons")
        self.assertEqual(len(persons), 3)

        self.delete_404(f"data/persons/{fields.gen_uuid()}")
        persons = self.get("data/persons")
        self.assertEqual(len(persons), 3)

    def test_cant_delete(self):
        self.generate_fixture_task_status_todo()
        self.generate_shot_suite()
        self.generate_assigned_task()
        self.generate_fixture_comment()
        self.person_id = str(self.person.id)
        self.get(f"data/persons/{self.person_id}")
        self.delete(f"data/persons/{self.person_id}", 400)

    def test_force_delete(self):
        self.generate_fixture_task_status_todo()
        self.generate_shot_suite()
        self.generate_assigned_task()
        self.generate_fixture_comment()
        self.person_id = str(self.person.id)
        self.get(f"data/persons/{self.person_id}")
        self.delete(f"data/persons/{self.person_id}?force=true")
        self.get(f"data/persons/{self.person_id}", 404)
