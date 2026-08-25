from tests.base import ApiDBTestCase

from zou.app import config
from zou.app.models.person import Person
from zou.app.services import persons_service, tasks_service
from zou.app.services.exception import (
    PersonInProtectedAccounts,
    PersonNotFoundException,
    WrongParameterException,
)
from zou.app.utils import auth, fields


class PersonsTestCase(ApiDBTestCase):
    """
    The admin the base class logs in as, plus one studio member.
    Holds no test of its own.
    """

    def setUp(self):
        super().setUp()

        self.generate_fixture_person()
        self.generate_fixture_department()
        self.person_id = str(self.person.id)
        self.person_email = self.person.email
        self.person_desktop_login = self.person.desktop_login

    def a_guest(self):
        """
        A person created by the shared playlist flow: not part of the
        studio, and left out of every team listing.
        """
        return Person.create(
            first_name="Guest",
            last_name="Reviewer",
            email="guest-reviewer@guest.kitsu",
            role="client",
            is_guest=True,
        )


class PersonReadTestCase(PersonsTestCase):
    """
    Reading one person. The default serialization is the safe one, since
    these dicts end up in payloads any team member can read.
    """

    def test_get_person(self):
        person = persons_service.get_person(self.person_id)
        self.assertEqual(person["id"], self.person_id)

    def test_get_person_of_an_unparsable_id(self):
        """
        The id reaches the service straight from the path, so a value the
        driver cannot read as a uuid answers a 404 rather than a 500.
        """
        self.assertRaises(
            PersonNotFoundException, persons_service.get_person, "wrong-id"
        )
        self.assertRaises(
            PersonNotFoundException, persons_service.get_person_raw, None
        )

    def test_get_person_of_a_deleted_person(self):
        persons_service.get_person(self.person_id)
        persons_service.delete_person(self.person_id)
        self.assertRaises(
            PersonNotFoundException, persons_service.get_person, self.person_id
        )

    def test_get_person_hides_the_credentials(self):
        """
        Everything that authenticates a person is stripped unless the
        caller asks for the unsafe form, which only the account owner's
        own routes do.
        """
        self.person.update({"totp_secret": "a-secret", "jti": "a-token-id"})

        safe = persons_service.get_person(self.person_id)
        for field in ("password", "totp_secret", "jti", "otp_recovery_codes"):
            self.assertNotIn(field, safe)

        unsafe = persons_service.get_person(self.person_id, unsafe=True)
        self.assertEqual(unsafe["totp_secret"], "a-secret")

    def test_get_person_by_email(self):
        person = persons_service.get_person_by_email(self.person_email)
        self.assertEqual(person["id"], self.person_id)
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_by_email,
            "wrong-email",
        )

    def test_get_person_by_email_of_a_bot(self):
        """
        A bot authenticates on its token, never on an email and password,
        so it is not reachable by email.
        """
        bot = persons_service.create_person(
            "bot@example.com", None, "Bot", "One", is_bot=True
        )
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_by_email,
            bot["email"],
        )

    def test_get_person_by_desktop_login(self):
        person = persons_service.get_person_by_desktop_login(
            self.person_desktop_login
        )
        self.assertEqual(person["id"], self.person_id)
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_by_desktop_login,
            "wrong-login",
        )

    def test_get_person_by_email_desktop_login(self):
        """
        The desktop client sends whichever of the two the artist typed.
        """
        for credential in (self.person_email, self.person_desktop_login):
            with self.subTest(credential=credential):
                self.assertEqual(
                    persons_service.get_person_by_email_desktop_login(
                        credential
                    )["id"],
                    self.person_id,
                )

    def test_get_person_by_ldap_uid(self):
        self.person.update({"ldap_uid": "jdoe"})
        self.assertEqual(
            persons_service.get_person_by_ldap_uid("jdoe")["id"],
            self.person_id,
        )
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

    def test_get_person_raw_cached(self):
        """
        The JWT identity loader goes through here on every request, so the
        record it hands back has to be attached to the running session,
        and to carry the departments the permission checks read.
        """
        persons_service.add_to_department(
            str(self.department.id), self.person_id
        )
        person = persons_service.get_person_raw_cached(self.person_id)
        self.assertEqual(str(person.id), self.person_id)
        self.assertEqual(
            [str(department.id) for department in person.departments],
            [str(self.department.id)],
        )
        self.assertRaises(
            PersonNotFoundException,
            persons_service.get_person_raw_cached,
            fields.gen_uuid(),
        )

    def test_get_persons_by_ids(self):
        self.assertEqual(persons_service.get_persons_by_ids([]), [])
        persons = persons_service.get_persons_by_ids([self.person_id])
        self.assertEqual(
            [person["id"] for person in persons], [self.person_id]
        )
        self.assertNotIn("password", persons[0])

    def test_get_short_person(self):
        """
        The author embedded in every comment and news entry. It carries a
        guest too, which the team listings leave out.
        """
        guest = self.a_guest()
        short = persons_service.get_short_person(str(guest.id))
        self.assertEqual(
            short,
            {
                "id": str(guest.id),
                "first_name": "Guest",
                "last_name": "Reviewer",
                "full_name": "Guest Reviewer",
                "has_avatar": False,
                "role": "client",
            },
        )

    def test_get_short_person_is_cached(self):
        """
        Comment feeds read the same authors over and over: the short dict
        stays cached until the person caches are dropped.
        """
        short = persons_service.get_short_person(self.person_id)
        person = Person.get(self.person_id)
        person.update({"first_name": "Updated"})
        cached = persons_service.get_short_person(self.person_id)
        self.assertEqual(cached["first_name"], short["first_name"])
        persons_service.clear_person_cache()
        fresh = persons_service.get_short_person(self.person_id)
        self.assertEqual(fresh["first_name"], "Updated")

    def test_get_short_persons_map(self):
        self.assertEqual(persons_service.get_short_persons_map([]), {})
        short_map = persons_service.get_short_persons_map([self.person_id])
        self.assertEqual(list(short_map), [self.person_id])
        self.assertNotIn("password", short_map[self.person_id])

    def test_get_persons_map(self):
        persons_map = persons_service.get_persons_map()
        self.assertEqual(persons_map[self.person_id]["id"], self.person_id)
        self.assertNotIn("password", persons_map[self.person_id])

    def test_is_admin(self):
        self.assertFalse(persons_service.is_admin({"role": "user"}))
        self.assertTrue(persons_service.is_admin({"role": "admin"}))

    def test_is_jti_revoked(self):
        """
        A bot or api token carries its jti on the person row: dropping it
        there is what revokes the token.
        """
        self.person.update({"jti": "a-token-id"})
        self.assertFalse(persons_service.is_jti_revoked("a-token-id"))
        self.assertTrue(persons_service.is_jti_revoked("another-token-id"))


class PersonListTestCase(PersonsTestCase):
    """
    Listing the studio. Guests come from the shared playlist flow and are
    not team members, so they stay out unless asked for.
    """

    def test_get_persons(self):
        persons = persons_service.get_persons()
        self.assertEqual(
            sorted(person["full_name"] for person in persons),
            ["John Did", "John Doe"],
        )
        self.assertNotIn("password", persons[0])

    def test_get_persons_minimal(self):
        persons = persons_service.get_persons(minimal=True)
        self.assertEqual(len(persons), 2)
        self.assertNotIn("password", persons[0])
        # The minimal form is a hand built dict rather than a trimmed
        # serialization: it carries what a person chip shows and no more.
        self.assertNotIn("email", persons[0])
        self.assertIn("full_name", persons[0])

    def test_get_persons_leaves_out_the_guests(self):
        guest = self.a_guest()
        self.assertNotIn(
            str(guest.id),
            [person["id"] for person in persons_service.get_persons()],
        )
        self.assertIn(
            str(guest.id),
            [
                person["id"]
                for person in persons_service.get_persons(include_guests=True)
            ],
        )

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

    def test_active_persons_leave_out_the_guests(self):
        guest_id = str(self.a_guest().id)
        self.assertNotIn(
            guest_id,
            [
                str(person.id)
                for person in persons_service.get_all_raw_active_persons()
            ],
        )
        self.assertNotIn(
            guest_id,
            [person["id"] for person in persons_service.get_active_persons()],
        )

    def test_get_all_raw_active_persons(self):
        persons_service.update_person(self.person_id, {"active": False})
        self.assertNotIn(
            self.person_id,
            [
                str(person.id)
                for person in persons_service.get_all_raw_active_persons()
            ],
        )

    def test_is_user_limit_reached(self):
        # The limit is process wide: put it back whatever this test does.
        self.addCleanup(setattr, config, "USER_LIMIT", config.USER_LIMIT)

        self.assertFalse(persons_service.is_user_limit_reached())
        config.USER_LIMIT = 2
        self.assertTrue(persons_service.is_user_limit_reached())

    def test_the_user_limit_counts_neither_guests_nor_bots(self):
        """
        A studio pays for its team. A guest reviewer and a bot are not
        seats.
        """
        self.addCleanup(setattr, config, "USER_LIMIT", config.USER_LIMIT)
        config.USER_LIMIT = 3

        self.a_guest()
        persons_service.create_person(
            "bot@example.com", None, "Bot", "One", is_bot=True
        )
        self.assertFalse(persons_service.is_user_limit_reached())

        persons_service.create_person(
            "third@example.com", None, "Third", "Member"
        )
        self.assertTrue(persons_service.is_user_limit_reached())

    def test_an_inactive_person_does_not_hold_a_seat(self):
        self.addCleanup(setattr, config, "USER_LIMIT", config.USER_LIMIT)
        config.USER_LIMIT = 2

        self.assertTrue(persons_service.is_user_limit_reached())
        persons_service.update_person(self.person_id, {"active": False})
        self.assertFalse(persons_service.is_user_limit_reached())


class PersonWriteTestCase(PersonsTestCase):
    """
    Creating and changing a person, and what each write has to announce
    and drop.
    """

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
        self.assertEqual(
            persons_service.get_person_by_email(person["email"])["id"],
            person["id"],
        )

    def test_create_person_trims_the_email(self):
        """
        A pasted address carries the spaces and the newline that came with
        it, and the email is the login.
        """
        persons_service.create_person(
            " john.doe3@gmail.com \n",
            auth.encrypt_password("passwordhash"),
            "John",
            "Doe",
        )
        person = persons_service.get_person_by_email("john.doe3@gmail.com")
        self.assertEqual(person["first_name"], "John")

    def test_create_person_with_an_empty_department(self):
        person = persons_service.create_person(
            "john.doe4@gmail.com",
            auth.encrypt_password("passwordhash"),
            "John",
            "Doe",
            departments=[None],
        )
        self.assertEqual(person["departments"], [])

    def test_create_person_expiring_in_the_past(self):
        self.assertRaises(
            WrongParameterException,
            persons_service.create_person,
            "expired@example.com",
            None,
            "Ex",
            "Pired",
            expiration_date="2020-01-01",
        )

    def test_create_person_with_an_unreadable_expiration_date(self):
        self.assertRaises(
            WrongParameterException,
            persons_service.create_person,
            "expired@example.com",
            None,
            "Ex",
            "Pired",
            expiration_date="not-a-date",
        )

    def test_create_bot(self):
        """
        A bot is handed its access token at creation, and the token id is
        stored on the row so that dropping it revokes the token.
        """
        bot = persons_service.create_person(
            "bot@example.com", None, "Bot", "One", is_bot=True
        )
        self.assertIn("access_token", bot)
        self.assertIsNotNone(Person.get(bot["id"]).jti)

    def test_a_new_person_shows_up_in_the_memoized_listing(self):
        persons_service.get_persons()
        persons_service.create_person("new@example.com", None, "New", "Member")
        self.assertIn(
            "new@example.com",
            [person["email"] for person in persons_service.get_persons()],
        )

    def test_update_person(self):
        persons_service.get_person(self.person_id)
        result = persons_service.update_person(
            self.person_id, {"first_name": "Updated"}
        )
        self.assertEqual(result["first_name"], "Updated")
        # Read back through the memoized path, which the update has to drop.
        self.assertEqual(
            persons_service.get_person(self.person_id)["first_name"],
            "Updated",
        )

    def test_update_person_expiration_date_in_past(self):
        self.assertRaises(
            WrongParameterException,
            persons_service.update_person,
            self.person_id,
            {"expiration_date": "2020-01-01"},
        )

    def test_update_person_with_an_unreadable_expiration_date(self):
        self.assertRaises(
            WrongParameterException,
            persons_service.update_person,
            self.person_id,
            {"expiration_date": "not-a-date"},
        )

    def test_update_person_expiration_date_rotates_the_token(self):
        """
        The expiration date is baked into the token, so setting one hands
        back a fresh token and stores its id.
        """
        result = persons_service.update_person(
            self.person_id, {"expiration_date": "2100-01-01"}
        )
        self.assertIn("access_token", result)
        self.assertIsNotNone(Person.get(self.person_id).jti)

    def test_a_protected_account_cannot_be_disabled_nor_demoted(self):
        """
        The accounts listed in the configuration are how a studio gets
        back in: nothing can take their role or their access away.
        """
        self.addCleanup(
            setattr,
            config,
            "PROTECTED_ACCOUNTS",
            config.PROTECTED_ACCOUNTS,
        )
        config.PROTECTED_ACCOUNTS = [self.person_email]

        for data in ({"active": False}, {"role": "user"}):
            with self.subTest(data=data):
                self.assertRaises(
                    PersonInProtectedAccounts,
                    persons_service.update_person,
                    self.person_id,
                    data,
                )
        # Anything else about them stays editable.
        persons_service.update_person(self.person_id, {"phone": "0123"})

    def test_the_protected_accounts_guard_can_be_bypassed(self):
        """
        The guard is about what a request may do. The LDAP synchronisation
        deactivates whoever left the directory, and it speaks for the
        studio rather than for a user.
        """
        self.addCleanup(
            setattr,
            config,
            "PROTECTED_ACCOUNTS",
            config.PROTECTED_ACCOUNTS,
        )
        config.PROTECTED_ACCOUNTS = [self.person_email]

        persons_service.update_person(
            self.person_id, {"active": False}, bypass_protected_accounts=True
        )

        self.assertFalse(persons_service.get_person(self.person_id)["active"])

    def test_a_protected_bot_is_not_a_protected_account(self):
        """
        The list holds the addresses a studio gets back in with. A bot
        carrying one of them is still only a bot.
        """
        self.addCleanup(
            setattr,
            config,
            "PROTECTED_ACCOUNTS",
            config.PROTECTED_ACCOUNTS,
        )
        bot = persons_service.create_person(
            "bot@example.com", None, "Bot", "One", is_bot=True
        )
        config.PROTECTED_ACCOUNTS = ["bot@example.com"]

        persons_service.update_person(bot["id"], {"active": False})

        self.assertFalse(persons_service.get_person(bot["id"])["active"])

    def test_update_password(self):
        new_password = auth.encrypt_password("newpassword")
        persons_service.update_password(self.person_email, new_password)
        self.assertEqual(Person.get(self.person_id).password, new_password)

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

    def test_add_to_department(self):
        department_id = str(self.department.id)
        persons_service.get_person(self.person_id)
        persons_service.add_to_department(department_id, self.person_id)
        self.assertEqual(
            persons_service.get_person(self.person_id)["departments"],
            [department_id],
        )

    def test_remove_from_department(self):
        department_id = str(self.department.id)
        persons_service.add_to_department(department_id, self.person_id)
        persons_service.remove_from_department(department_id, self.person_id)
        self.assertEqual(
            persons_service.get_person(self.person_id)["departments"], []
        )

    def test_clear_avatar(self):
        self.person.update({"has_avatar": True})
        persons_service.clear_person_cache()
        persons_service.get_person(self.person_id)

        events = self.capture_events("person:update")
        result = persons_service.clear_avatar(self.person_id)

        self.assertFalse(result["has_avatar"])
        self.assertFalse(
            persons_service.get_person(self.person_id)["has_avatar"]
        )
        # Setting an avatar goes through update_person and is announced;
        # dropping one deletes the file, so the other clients have to hear
        # about it too.
        self.assertEqual(len(events), 1)


class PresenceTestCase(PersonsTestCase):
    """
    What tells a studio someone was around: a desktop login and hours
    logged on a task.
    """

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

    def test_desktop_login_logs_are_read_per_person(self):
        persons_service.create_desktop_login_logs(
            self.person_id, "2021-06-14T09:00:00"
        )
        self.assertEqual(
            persons_service.get_desktop_login_logs(self.user["id"]), []
        )

    def test_update_person_last_presence(self):
        """
        The latest of the two things that count as a presence: a time spent
        and a desktop login. They are stored in different types, a date for
        one and a datetime for the other, and either can be missing.
        """
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_assigner()
        task_id = str(self.generate_fixture_task().id)

        def log_in(date):
            persons_service.create_desktop_login_logs(self.person_id, date)

        def work(date):
            tasks_service.create_or_update_time_spent(
                task_id, self.person_id, date, 600
            )

        cases = [
            ("a time spent alone", work, "2021-06-01", "2021-06-01"),
            ("a later one", work, "2021-06-20", "2021-06-20"),
            ("a login after it", log_in, "2021-06-25", "2021-06-25"),
            # Each case keeps what the ones before it added, so an older
            # login is read against the login of the case above.
            ("an older login", log_in, "2021-06-10", "2021-06-25"),
            ("a time spent after the login", work, "2021-07-01", "2021-07-01"),
        ]
        for reason, add, date, expected in cases:
            with self.subTest(reason=reason):
                add(date)
                result = persons_service.update_person_last_presence(
                    self.person_id
                )
                self.assertEqual(result["last_presence"], expected)

    def test_update_person_last_presence_on_a_login_alone(self):
        # A person who only ever opens the desktop application has no time
        # spent to fall back on.
        persons_service.create_desktop_login_logs(self.person_id, "2021-06-01")

        result = persons_service.update_person_last_presence(self.person_id)

        self.assertEqual(result["last_presence"], "2021-06-01")

    def test_update_person_last_presence_on_nothing_at_all(self):
        result = persons_service.update_person_last_presence(self.person_id)
        self.assertIsNone(result["last_presence"])

    def test_get_presence_logs(self):
        """
        One row per active person, one column per day of the month, and an
        X on the days they logged in. The first cell of the header is the
        year, since the sheet is read as a calendar.
        """
        persons_service.create_desktop_login_logs(self.person_id, "2021-03-15")
        persons_service.create_desktop_login_logs(self.person_id, "2021-03-17")
        # Outside the month, so it must not mark any of its days.
        persons_service.create_desktop_login_logs(self.person_id, "2021-04-02")

        headers, *rows = persons_service.get_presence_logs(2021, 3)

        self.assertEqual(headers[0], "2021")
        self.assertEqual(headers[1:], [str(day) for day in range(1, 32)])
        by_name = {row[0]: row for row in rows}
        self.assertEqual(sorted(by_name), ["John Did", "John Doe"])
        marked = [
            headers[index]
            for index, cell in enumerate(by_name["John Doe"])
            if cell == "X"
        ]
        self.assertEqual(marked, ["15", "17"])
        self.assertEqual(by_name["John Did"].count("X"), 0)

    def test_get_presence_logs_of_a_short_month(self):
        headers, *_ = persons_service.get_presence_logs(2021, 2)
        self.assertEqual(headers[-1], "28")

    def test_get_presence_logs_of_december(self):
        """
        The end of the sheet rolls over into the next year.
        """
        persons_service.create_desktop_login_logs(self.person_id, "2021-12-05")
        persons_service.create_desktop_login_logs(self.person_id, "2022-01-05")

        _, *rows = persons_service.get_presence_logs(2021, 12)

        by_name = {row[0]: row for row in rows}
        self.assertEqual(by_name["John Doe"].count("X"), 1)


class OrganisationTestCase(PersonsTestCase):
    """
    The single organisation row of the instance.
    """

    def test_get_organisation(self):
        organisation = persons_service.get_organisation()
        self.assertIn("id", organisation)

    def test_get_organisation_creates_it_once(self):
        """
        A fresh instance has no organisation row: the first reading makes
        it, and every later one finds it.
        """
        self.assertEqual(
            persons_service.get_organisation()["id"],
            persons_service.get_organisation()["id"],
        )

    def test_update_organisation(self):
        organisation = persons_service.get_organisation()
        result = persons_service.update_organisation(
            organisation["id"], {"name": "NewOrg"}
        )
        self.assertEqual(result["name"], "NewOrg")
        # Read back through the memoized path, which the update has to drop.
        self.assertEqual(persons_service.get_organisation()["name"], "NewOrg")
