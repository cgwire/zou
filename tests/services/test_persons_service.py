from tests.base import ApiDBTestCase

from zou.app.services import persons_service, tasks_service
from zou.app.services.exception import PersonNotFoundException
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

    def test_get_person_by_username(self):
        person = persons_service.get_person_by_email_username(
            "john.doe@gmail.com"
        )
        self.assertEqual(person["first_name"], "John")
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_by_email_username,
            "ema.doe@yahoo.com",
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

    def test_add_destktop_login_logs(self):
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
