from tests.base import ApiDBTestCase

from zou.app.models.organisation import Organisation
from zou.app.services import persons_service
from zou.app.services.exception import (
    PersonNotFoundException,
    WrongParameterException,
)
from zou.app.utils import auth


class PersonServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(PersonServiceTestCase, self).setUp()

        self.generate_fixture_person()
        self.generate_fixture_department()
        self.person_id = str(self.person.id)
        self.person_email = self.person.email
        self.person_desktop_login = self.person.desktop_login

    def test_get_active_persons(self):
        self.assertEqual(len(persons_service.get_persons()), 2)
        persons_service.update_person(self.person.id, {"active": False})
        self.assertEqual(len(persons_service.get_active_persons()), 1)

    def test_get_person(self):
        self.assertRaises(
            PersonNotFoundException, persons_service.get_person, "wrong-id"
        )
        person = persons_service.get_person(self.person_id)
        self.assertEqual(self.person_id, person["id"])
        persons_service.delete_person(self.person_id)

        self.assertRaises(
            PersonNotFoundException, persons_service.get_person, self.person_id
        )

    def test_get_person_by_email(self):
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_by_email,
            "wrong-email",
        )
        person = persons_service.get_person_by_email(self.person_email)
        self.assertEqual(self.person_id, person["id"])
        persons_service.delete_person(person["id"])

        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_by_email,
            self.person_email,
        )

    def test_get_person_by_desktop_login(self):
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_by_desktop_login,
            "wrong-login",
        )
        person = persons_service.get_person_by_desktop_login(
            self.person_desktop_login
        )
        person = persons_service.get_person_by_email(person["email"])
        self.assertEqual(self.person_id, person["id"])
        persons_service.delete_person(person["id"])

        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_by_desktop_login,
            self.person_desktop_login,
        )

    def test_create_person(self):
        person = persons_service.create_person(
            "john.doe2@gmail.com",
            auth.encrypt_password("passwordhash"),
            "John",
            "Doe",
        )
        person = persons_service.get_person_by_email(person["email"])
        self.assertEqual(person["first_name"], "John")

        person = persons_service.create_person(
            " john.doe3@gmail.com \n",
            auth.encrypt_password("passwordhash"),
            "John",
            "Doe",
        )
        person = persons_service.get_person_by_email("john.doe3@gmail.com")
        self.assertEqual(person["first_name"], "John")

        person = persons_service.create_person(
            " john.doe4@gmail.com \n",
            auth.encrypt_password("passwordhash"),
            "John",
            "Doe",
            departments=[None],
        )
        person = persons_service.get_person_by_email("john.doe4@gmail.com")
        self.assertEqual(person["first_name"], "John")

    def test_add_desktop_login_logs(self):
        person = self.person.serialize()
        date_1 = self.now()
        logs = persons_service.get_desktop_login_logs(person["id"])
        self.assertEqual(len(logs), 0)
        persons_service.create_desktop_login_logs(person["id"], date_1)
        date_2 = self.now()
        persons_service.create_desktop_login_logs(person["id"], date_2)
        logs = persons_service.get_desktop_login_logs(person["id"])
        self.assertEqual(len(logs), 2)
        self.assertEqual(logs[0]["person_id"], person["id"])
        self.assertEqual(logs[0]["date"], date_2)

    def test_is_user_limit_reached(self):
        is_reached = persons_service.is_user_limit_reached()
        self.assertEqual(is_reached, False)
        from zou.app import config

        config.USER_LIMIT = 2
        is_reached = persons_service.is_user_limit_reached()
        self.assertEqual(is_reached, True)
        config.USER_LIMIT = 100

    def test_add_to_department(self):
        person = self.person.serialize()
        department = self.department.serialize()
        persons_service.add_to_department(department["id"], person["id"])
        person = persons_service.get_person(person["id"])
        self.assertEqual(person["departments"][0], department["id"])

    def test_remove_from_department(self):
        person = self.person.serialize()
        department = self.department.serialize()
        persons_service.add_to_department(department["id"], person["id"])
        persons_service.remove_from_department(department["id"], person["id"])
        person = persons_service.get_person(person["id"])
        self.assertEqual(len(person["departments"]), 0)

    def test_get_persons(self):
        persons = persons_service.get_persons()
        self.assertEqual(len(persons), 2)

    def test_get_persons_minimal(self):
        persons = persons_service.get_persons(minimal=True)
        self.assertEqual(len(persons), 2)
        self.assertIn("id", persons[0])
        self.assertNotIn("password", persons[0])

    def test_get_all_raw_active_persons(self):
        persons = persons_service.get_all_raw_active_persons()
        self.assertGreater(len(persons), 0)
        for person in persons:
            self.assertTrue(person.active)

    def test_get_person_raw(self):
        person = persons_service.get_person_raw(self.person_id)
        self.assertEqual(str(person.id), self.person_id)
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_raw,
            None,
        )
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_raw,
            "wrong-id",
        )

    def test_get_person_by_email_raw(self):
        person = persons_service.get_person_by_email_raw(self.person_email)
        self.assertEqual(str(person.id), self.person_id)
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_by_email_raw,
            "wrong@email.com",
        )

    def test_get_person_by_email_desktop_login(self):
        result = persons_service.get_person_by_email_desktop_login(
            self.person_email
        )
        self.assertEqual(result["id"], self.person_id)
        result = persons_service.get_person_by_email_desktop_login(
            self.person_desktop_login
        )
        self.assertEqual(result["id"], self.person_id)

    def test_get_persons_map(self):
        persons_map = persons_service.get_persons_map()
        self.assertIn(self.person_id, persons_map)
        self.assertEqual(persons_map[self.person_id]["id"], self.person_id)

    def test_update_password(self):
        new_password = auth.encrypt_password("newpassword")
        result = persons_service.update_password(
            self.person_email, new_password
        )
        self.assertEqual(result["id"], self.person_id)

    def test_update_person(self):
        result = persons_service.update_person(
            self.person_id, {"first_name": "Updated"}
        )
        self.assertEqual(result["first_name"], "Updated")

    def test_update_person_expiration_date_in_past(self):
        self.assertRaises(
            WrongParameterException,
            persons_service.update_person,
            self.person_id,
            {"expiration_date": "2020-01-01"},
        )

    def test_delete_person(self):
        person = persons_service.create_person(
            "todelete@test.com",
            auth.encrypt_password("pass"),
            "Delete",
            "Me",
        )
        result = persons_service.delete_person(person["id"])
        self.assertEqual(result["id"], person["id"])
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person,
            person["id"],
        )

    def test_get_presence_logs(self):
        persons_service.create_desktop_login_logs(
            self.person_id, "2021-03-15"
        )
        logs = persons_service.get_presence_logs(2021, 3)
        self.assertGreater(len(logs), 0)
        self.assertEqual(logs[0][0], "2021")

    def test_is_admin(self):
        self.assertFalse(
            persons_service.is_admin({"role": "user"})
        )
        self.assertTrue(
            persons_service.is_admin({"role": "admin"})
        )

    def test_get_organisation(self):
        org = persons_service.get_organisation()
        self.assertIsNotNone(org)
        self.assertIn("id", org)

    def test_update_organisation(self):
        org = persons_service.get_organisation()
        result = persons_service.update_organisation(
            org["id"], {"name": "NewOrg"}
        )
        self.assertEqual(result["name"], "NewOrg")

    def test_clear_avatar(self):
        result = persons_service.clear_avatar(self.person_id)
        self.assertFalse(result["has_avatar"])

    def test_update_person_last_presence(self):
        persons_service.create_desktop_login_logs(
            self.person_id, "2021-06-15"
        )
        result = persons_service.update_person_last_presence(self.person_id)
        self.assertIsNotNone(result)

    def test_get_person_by_ldap_uid(self):
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_by_ldap_uid,
            None,
        )
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_by_ldap_uid,
            "nonexistent-uid",
        )
