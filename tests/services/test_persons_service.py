from tests.base import ApiDBTestCase

from zou.app.services import persons_service, tasks_service
from zou.app.services.exception import (
    PersonNotFoundException,
    WrongParameterException,
)
from zou.app.utils import auth, fields


class PersonServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_person()
        self.generate_fixture_department()
        self.person_id = str(self.person.id)
        self.person_email = self.person.email
        self.person_desktop_login = self.person.desktop_login

    def test_get_active_persons(self):
        # Created last and sorting first, so the order is the query's and
        # not the insertion one.
        self.generate_fixture_person(
            first_name="Alice",
            last_name="Zulu",
            desktop_login="alice.zulu",
            email="alice.zulu@gmail.com",
        )
        # A third John, so the last name is what breaks the tie.
        self.generate_fixture_person(
            first_name="John",
            last_name="Aaa",
            desktop_login="john.aaa",
            email="john.aaa@gmail.com",
        )
        # get_persons does not order, get_active_persons does.
        self.assertEqual(len(persons_service.get_persons()), 4)
        self.assertEqual(
            [
                person["full_name"]
                for person in persons_service.get_active_persons()
            ],
            ["Alice Zulu", "John Aaa", "John Did", "John Doe"],
        )

        # self.person_id, not self.person: the two fixtures above repointed
        # self.person at the last one they built.
        persons_service.update_person(self.person_id, {"active": False})
        self.assertEqual(
            [
                person["full_name"]
                for person in persons_service.get_active_persons()
            ],
            ["Alice Zulu", "John Aaa", "John Did"],
        )

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

    def test_get_person_by_empty_desktop_login(self):
        # create_person defaults desktop_login to "" and the column is not
        # unique, so an empty lookup used to return the first account
        # without a desktop login.
        persons_service.create_person(
            "no.login@gmail.com",
            auth.encrypt_password("passwordhash"),
            "No",
            "Login",
        )
        for empty in ["", None]:
            self.assertRaises(
                PersonNotFoundException,
                persons_service.get_person_by_desktop_login,
                empty,
            )
            self.assertRaises(
                PersonNotFoundException,
                persons_service.get_person_by_email_desktop_login,
                empty,
            )

    def test_lockout_state_is_not_published(self):
        # serialize_safe published how far each account was into its login
        # burst, and the field being filterable answered who is locked
        # right now. The unsafe serialization still carries it.
        person = persons_service.get_person(self.person_id)
        self.assertNotIn("login_failed_attemps", person)
        self.assertNotIn("last_login_failed", person)

        person = persons_service.get_person(self.person_id, unsafe=True)
        self.assertIn("login_failed_attemps", person)

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
        """
        Newest first. now() truncates to the second, so two calls in a row
        would carry the same date and prove nothing about the order.
        """
        self.assertEqual(
            persons_service.get_desktop_login_logs(self.person_id), []
        )
        persons_service.create_desktop_login_logs(
            self.person_id, "2021-06-14T09:00:00"
        )
        persons_service.create_desktop_login_logs(
            self.person_id, "2021-06-15T09:00:00"
        )

        logs = persons_service.get_desktop_login_logs(self.person_id)
        self.assertEqual(
            [log["date"] for log in logs],
            ["2021-06-15T09:00:00", "2021-06-14T09:00:00"],
        )
        self.assertEqual(logs[0]["person_id"], self.person_id)

    def test_is_user_limit_reached(self):
        from zou.app import config
        from zou.app.models.person import Person

        self.assertFalse(persons_service.is_user_limit_reached())

        config.USER_LIMIT = 2
        self.assertTrue(persons_service.is_user_limit_reached())

        config.USER_LIMIT = 3
        Person.create(
            first_name="Guest",
            last_name="Reviewer",
            email="guest-reviewer@guest.kitsu",
            role="client",
            is_guest=True,
        )
        self.assertFalse(persons_service.is_user_limit_reached())

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
        self.assertEqual(person["departments"], [])

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

    def test_active_persons_exclude_guests(self):
        from zou.app.models.person import Person

        Person.create(
            first_name="Guest",
            last_name="Reviewer",
            email="guest-reviewer@guest.kitsu",
            role="client",
            is_guest=True,
        )
        raw_persons = persons_service.get_all_raw_active_persons()
        self.assertGreater(len(raw_persons), 0)
        self.assertFalse(any(p.is_guest for p in raw_persons))
        persons = persons_service.get_active_persons()
        self.assertGreater(len(persons), 0)
        self.assertFalse(any(p.get("is_guest") for p in persons))

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
        persons_service.create_desktop_login_logs(self.person_id, "2021-03-15")
        logs = persons_service.get_presence_logs(2021, 3)
        self.assertGreater(len(logs), 0)
        self.assertEqual(logs[0][0], "2021")

    def test_is_admin(self):
        self.assertFalse(persons_service.is_admin({"role": "user"}))
        self.assertTrue(persons_service.is_admin({"role": "admin"}))

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
        """
        The latest time spent, read newest first.

        Only the time spents are covered: with a desktop login log in the
        picture the function either returns None (no time spent) or raises
        TypeError comparing its datetime to the time spent date. Reported,
        not pinned here.
        """
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_assigner()
        task_id = str(self.generate_fixture_task().id)
        tasks_service.create_or_update_time_spent(
            task_id, self.person_id, "2021-06-01", 600
        )

        result = persons_service.update_person_last_presence(self.person_id)
        self.assertEqual(result["last_presence"], "2021-06-01")

        # Written last, read first.
        tasks_service.create_or_update_time_spent(
            task_id, self.person_id, "2021-06-20", 600
        )
        result = persons_service.update_person_last_presence(self.person_id)
        self.assertEqual(result["last_presence"], "2021-06-20")

    def test_get_person_raw_cached(self):
        """
        The JWT identity loader goes through here on every request, so the
        record it hands back has to be attached to the running session.
        """
        person = persons_service.get_person_raw_cached(self.person_id)
        self.assertEqual(str(person.id), self.person_id)
        self.assertEqual(
            [department.id for department in person.departments], []
        )
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_raw_cached,
            fields.gen_uuid(),
        )

    def test_is_jti_revoked(self):
        """
        A bot or api token carries its jti on the person row: dropping it
        there is what revokes the token.
        """
        self.person.update({"jti": "a-token-id"})
        self.assertFalse(persons_service.is_jti_revoked("a-token-id"))
        self.assertTrue(persons_service.is_jti_revoked("another-token-id"))

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
