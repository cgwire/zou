# -*- coding: UTF-8 -*-
import datetime
from operator import itemgetter
from unittest import mock
from urllib.parse import quote

import pyotp
import pytest

from tests.base import ApiDBTestCase
from tests.fake_dns import NO_MX_DOMAIN
from zou.app import config
from zou.app.models.department import Department
from zou.app.models.person import SENSITIVE_FIELDS, Person
from zou.app.services import persons_service
from zou.app.utils import fields


class PersonFixtureTestCase(ApiDBTestCase):
    """
    Three people, one of them carrying non ascii names. Holds no test of
    its own.
    """

    def setUp(self):
        super().setUp()
        self.generate_fixture_person(
            first_name="Ema",
            last_name="Doe",
            desktop_login="ema.doe",
            email="ema.doe@example.com",
        )
        self.generate_fixture_person(
            first_name="Jérémy",
            last_name="Utêfœuit",
            desktop_login="jeremy.utf8",
            email="jeremy.utf8@example.com",
        )
        self.generate_fixture_person()


class PersonTestCase(PersonFixtureTestCase):
    def test_get_persons(self):
        persons = self.get("data/persons")
        self.assertEqual(len(persons), 4)
        self.assertEqual(persons[0]["type"], "Person")

    def test_updated_at_in_present_minimal(self):
        """
        Kitsu versions the avatar URL with updated_at. Without it, a
        non-manager kept the previous picture of a person for as long as
        the browser cache held it, up to a week.
        """
        person = Person.get_by(email="ema.doe@example.com")
        Person.query.filter(Person.id == person.id).update(
            {"updated_at": datetime.datetime(2021, 1, 1, 12, 0)}
        )
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()

        last_edit = "2021-01-01T12:00:00"
        self.assertEqual(
            self.get(f"data/persons/{person.id}")["updated_at"], last_edit
        )
        context = {
            entry["id"]: entry
            for entry in self.get("data/user/context")["persons"]
        }
        self.assertEqual(context[str(person.id)]["updated_at"], last_edit)

    def test_get_person(self):
        person = self.get_first("data/persons")
        person_again = self.get(f"data/persons/{person['id']}?relations=false")
        self.assertEqual(person, person_again)
        person_with_relations = self.get(
            f"data/persons/{person['id']}?relations=true"
        )
        self.assertIn("departments", person_with_relations)
        self.get_404(f"data/persons/{fields.gen_uuid()}")

    def test_create_person(self):
        data = {
            "first_name": "John2",
            "last_name": "Doe",
            "email": "john3.doe@example.com",
        }
        self.person = self.post("data/persons", data)
        self.assertIsNotNone(self.person["id"])

        persons = self.get("data/persons")
        self.assertEqual(len(persons), 5)

    def test_create_too_much_person(self):
        from zou.app import config

        self.addCleanup(setattr, config, "USER_LIMIT", config.USER_LIMIT)
        config.USER_LIMIT = 4
        data = {
            "first_name": "John3",
            "last_name": "Doe",
            "email": "john3.doe@example.com",
        }
        resp = self.post("data/persons", data, 400)
        self.assertEqual(resp["data"]["limit"], 4)

    def test_create_person_non_admin_at_user_limit(self):
        from zou.app import config

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        self.addCleanup(setattr, config, "USER_LIMIT", config.USER_LIMIT)
        config.USER_LIMIT = 1
        data = {
            "first_name": "John3",
            "last_name": "Doe",
            "email": "john3.doe@example.com",
        }
        resp = self.post("data/persons", data, 403)
        self.assertNotIn("data", resp)

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
            "email": "john2.doe@example.com",
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
            "email": "ema.doe@example.com",
        }
        response = self.post("data/persons", data, 400)
        self.assertIn("Email already in use", response["message"])

    @mock.patch.object(config, "MAIL_CHECK_DELIVERABILITY", True)
    def test_create_person_with_email_domain_without_mx(self):
        data = {
            "first_name": "John",
            "last_name": "NoMx",
            "email": f"john.nomx@{NO_MX_DOMAIN}",
        }
        response = self.post("data/persons", data, 400)
        self.assertIn("does not accept email", response["message"])
        self.assertIsNone(Person.get_by(email=data["email"]))

    def test_create_bot_can_share_email_with_person(self):
        data = {
            "first_name": "Bot",
            "last_name": "Bot",
            "email": "ema.doe@example.com",
            "is_bot": True,
        }
        person = self.post("data/persons", data)
        self.assertIsNotNone(person["id"])

    def test_update_bot_can_keep_email_shared_with_person(self):
        data = {
            "first_name": "Bot",
            "last_name": "Bot",
            "email": "ema.doe@example.com",
            "is_bot": True,
        }
        bot = self.post("data/persons", data)

        self.put(
            f"data/persons/{bot['id']}",
            {"first_name": "Renamed Bot", "email": bot["email"]},
        )
        bot_again = self.get(f"data/persons/{bot['id']}")
        self.assertEqual(bot_again["first_name"], "Renamed Bot")
        self.assertEqual(bot_again["email"], "ema.doe@example.com")

    def test_update_expired_person_keeps_its_own_expiration_date(self):
        import datetime

        yesterday = datetime.date.today() - datetime.timedelta(days=2)
        bot = Person.create(
            first_name="Expired",
            last_name="Bot",
            email="expired.bot@example.com",
            is_bot=True,
            expiration_date=yesterday,
        )
        bot_id = str(bot.id)

        # Re-submitting the already-expired date (e.g. to disable the bot)
        # must work: it is unchanged, not a new past date.
        self.put(
            f"data/persons/{bot_id}",
            {"expiration_date": yesterday.isoformat(), "active": False},
        )
        bot_again = self.get(f"data/persons/{bot_id}")
        self.assertFalse(bot_again["active"])

        # Moving the expiration to a different past date is still rejected.
        other_past = (yesterday - datetime.timedelta(days=1)).isoformat()
        self.put(
            f"data/persons/{bot_id}",
            {"expiration_date": other_past},
            400,
        )

        # Renewing to a future date still works and issues a fresh token.
        future = (
            datetime.date.today() + datetime.timedelta(days=30)
        ).isoformat()
        renewed = self.put(
            f"data/persons/{bot_id}", {"expiration_date": future}
        )
        self.assertIn("access_token", renewed)

    def test_update_person_issues_a_token_for_bots_only(self):
        """
        The update hands a token to bots only. For a person, whatever the
        role, it was a permanent one issued without their password.
        """
        artist_id = self.generate_fixture_user_cg_artist()["id"]
        bot = self.post(
            "data/persons",
            {
                "first_name": "Bot",
                "last_name": "Bot",
                "email": "bot@example.com",
                "is_bot": True,
            },
        )
        for person_id in (self.user["id"], artist_id):
            updated = self.put(
                f"data/persons/{person_id}", {"expiration_date": None}
            )
            self.assertNotIn("access_token", updated)
            self.assertIsNone(Person.get(person_id).jti)
        # Kitsu sends null from the Bots page when no date is set.
        renewed = self.put(
            f"data/persons/{bot['id']}", {"expiration_date": None}
        )
        self.assertIn("access_token", renewed)

        self.log_in_cg_artist()
        updated = self.put(
            f"data/persons/{artist_id}", {"expiration_date": None}
        )
        self.assertNotIn("access_token", updated)
        self.assertIsNone(Person.get(artist_id).jti)

    def test_update_person(self):
        person = self.get_first("data/persons")
        data = {
            "first_name": "Johnny",
        }
        self.put(f"data/persons/{person['id']}", data)
        person_again = self.get(f"data/persons/{person['id']}")
        self.assertEqual(data["first_name"], person_again["first_name"])
        self.put_404(f"data/persons/{fields.gen_uuid()}", data)

    def test_update_person_leaves_the_two_factor_settings(self):
        """
        The 2FA settings change through the auth routes only: the person
        update ignores them, for the person themselves and for an admin.
        """
        artist_id = self.generate_fixture_user_cg_artist()["id"]
        # Logged in first: with TOTP on, the login would ask for a code.
        self.log_in_cg_artist()
        settings = {
            "totp_enabled": True,
            "totp_secret": "JBSWY3DPEHPK3PXP",
            "preferred_two_factor_authentication": "totp",
            "otp_recovery_codes": [b"$2b$12$notarealrecoverycodehash"],
        }
        Person.get(artist_id).update(settings)
        data = {
            "first_name": "Jane",
            "totp_enabled": False,
            "totp_secret": "KRSXG5CTMVRXEZLU",
            "email_otp_enabled": True,
            "email_otp_secret": "KRSXG5CTMVRXEZLU",
            "fido_enabled": True,
            "fido_credentials": [{"device_name": "other-key"}],
            "otp_recovery_codes": [],
            "preferred_two_factor_authentication": "fido",
        }

        def check_settings_kept():
            person = Person.get(artist_id)
            self.assertEqual(person.first_name, "Jane")
            self.assertTrue(person.totp_enabled)
            self.assertEqual(person.totp_secret, settings["totp_secret"])
            self.assertFalse(person.email_otp_enabled)
            self.assertIsNone(person.email_otp_secret)
            self.assertFalse(person.fido_enabled)
            self.assertIsNone(person.fido_credentials)
            self.assertEqual(
                person.otp_recovery_codes, settings["otp_recovery_codes"]
            )
            self.assertEqual(
                person.preferred_two_factor_authentication, "totp"
            )

        self.put(f"data/persons/{artist_id}", data)
        check_settings_kept()

        self.log_in_admin()
        self.put(f"data/persons/{artist_id}", data)
        check_settings_kept()

    def test_person_display_preferences_round_trip(self):
        person = self.get_first("data/persons")
        self.put(
            f"data/persons/{person['id']}",
            {"use_12_hour_clock": True, "display_date_format": "DD/MM/YYYY"},
        )
        person_again = self.get(f"data/persons/{person['id']}")
        self.assertTrue(person_again["use_12_hour_clock"])
        self.assertEqual(person_again["display_date_format"], "DD/MM/YYYY")

        self.put(f"data/persons/{person['id']}", {"display_date_format": None})
        person_again = self.get(f"data/persons/{person['id']}")
        self.assertIsNone(person_again["display_date_format"])

    def test_person_invalid_display_date_format(self):
        person = self.get_first("data/persons")
        self.put(
            f"data/persons/{person['id']}",
            {"display_date_format": "DD-MM-YYYY"},
            400,
        )
        self.post(
            "data/persons",
            {
                "first_name": "Bad",
                "last_name": "Format",
                "email": "bad.format@example.com",
                "display_date_format": "MM-DD",
            },
            400,
        )

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

        self.addCleanup(setattr, config, "USER_LIMIT", config.USER_LIMIT)
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


class PersonCountryTestCase(PersonFixtureTestCase):
    """
    The country a person carries, stored as an upper case two letter
    code. The model rules are in tests/models/test_person.py.
    """

    def test_person_country_round_trip(self):
        data = {
            "first_name": "Country",
            "last_name": "Tester",
            "email": "country.tester@example.com",
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

        # Whitespace is trimmed and the value upper-cased on update.
        self.put(f"data/persons/{person['id']}", {"country": " us "})
        person_again = self.get(f"data/persons/{person['id']}")
        self.assertEqual(person_again["country"], "US")

    def test_create_person_without_country(self):
        data = {
            "first_name": "NoCountry",
            "last_name": "Doe",
            "email": "no.country@example.com",
        }
        person = self.post("data/persons", data)
        self.assertIsNone(person["country"])

    def test_create_person_with_invalid_country(self):
        data = {
            "first_name": "Bad",
            "last_name": "Country",
            "email": "bad.country@example.com",
            "country": "France",
        }
        self.post("data/persons", data, 400)

    def test_update_person_with_invalid_country(self):
        # A non-string body gets a clean 400, never a 500.
        person = self.get_first("data/persons")
        self.put(f"data/persons/{person['id']}", {"country": 123}, 400)


class PersonLocaleTestCase(PersonFixtureTestCase):
    """
    The locale a person carries, same contract as the country.
    """

    def test_person_locale_round_trip(self):
        data = {
            "first_name": "Locale",
            "last_name": "Tester",
            "email": "locale.tester@example.com",
            "locale": "fr_FR",
        }
        person = self.post("data/persons", data)
        self.assertEqual(person["locale"], "fr_FR")

        # The stored value survives every read path (single GET, relations,
        # list) instead of breaking serialization.
        person_again = self.get(f"data/persons/{person['id']}")
        self.assertEqual(person_again["locale"], "fr_FR")
        person_with_relations = self.get(
            f"data/persons/{person['id']}?relations=true"
        )
        self.assertEqual(person_with_relations["locale"], "fr_FR")
        listed = next(
            p for p in self.get("data/persons") if p["id"] == person["id"]
        )
        self.assertEqual(listed["locale"], "fr_FR")

        # Whitespace is trimmed on update.
        self.put(f"data/persons/{person['id']}", {"locale": " ja_JP "})
        person_again = self.get(f"data/persons/{person['id']}")
        self.assertEqual(person_again["locale"], "ja_JP")

    def test_create_person_with_invalid_locale(self):
        data = {
            "first_name": "Bad",
            "last_name": "Locale",
            "email": "bad.locale@example.com",
            "locale": "zz_ZZ",
        }
        self.post("data/persons", data, 400)

    def test_update_person_with_invalid_locale(self):
        # A wrong separator makes Babel raise: a clean 400, never a 500.
        person = self.get_first("data/persons")
        self.put(f"data/persons/{person['id']}", {"locale": "en-US"}, 400)


class PersonColumnExposureTestCase(PersonFixtureTestCase):
    """
    What the routes let a caller read and filter on. Filters run
    before serialization, so a column hidden from the response is
    still queryable unless the filter list refuses it too.
    """

    def test_write_routes_never_return_secrets(self):
        person = self.get_first("data/persons")
        Person.get(person["id"]).update(
            {
                "password": b"$2b$12$notarealbcrypthashbutlongenough",
                "totp_secret": "JBSWY3DPEHPK3PXP",
                "email_otp_secret": "KRSXG5CTMVRXEZLU",
                "otp_recovery_codes": [b"$2b$12$notarealrecoverycodehash"],
            }
        )

        updated = self.put(
            f"data/persons/{person['id']}", {"last_name": "Doe"}
        )
        for field in SENSITIVE_FIELDS:
            self.assertNotIn(field, updated)

        created = self.post(
            "data/persons",
            {
                "first_name": "No",
                "last_name": "Secret",
                "email": "no.secret@example.com",
            },
        )
        for field in SENSITIVE_FIELDS:
            self.assertNotIn(field, created)

        self.generate_fixture_department()
        joined = self.post(
            f"actions/persons/{person['id']}/departments/add",
            {"department_id": str(self.department.id)},
        )
        for field in SENSITIVE_FIELDS:
            self.assertNotIn(field, joined)

    def test_hidden_columns_are_not_filterable(self):
        # Filters run before serialization, so a column absent from
        # present_minimal stays answerable by equality unless the filter
        # keys are narrowed too: ?daily_salary=320 would walk the payroll.
        # A refused filter must be an error, never a wider result set.
        person = Person.get_by(email="ema.doe@example.com")
        person.update({"daily_salary": 320, "phone": "0600000000"})
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()

        for query in ["daily_salary=320", "phone=0600000000"]:
            self.get(f"data/persons?{query}", 400)

    def test_email_stays_filterable_for_non_admins(self):
        # gazu.person.get_person_by_email() reads the first row of this
        # route, so dropping the filter handed out an arbitrary person
        # instead of no match.
        person = Person.get_by(email="ema.doe@example.com")
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()

        persons = self.get("data/persons?email=ema.doe@example.com")
        self.assertEqual(len(persons), 1)
        self.assertEqual(persons[0]["id"], str(person.id))

        self.assertEqual(self.get("data/persons?email=nobody@example.com"), [])

    def test_guest_flag_stays_filterable_for_non_admins(self):
        # Kitsu loads the studio people with ?is_guest=false: refusing the
        # filter left every non-admin with the people of the login context.
        person = Person.get_by(email="ema.doe@example.com")
        guest = Person.create(
            first_name="Guest",
            last_name="Doe",
            email="guest.doe@example.com",
            is_guest=True,
        )
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()

        ids = [
            entry["id"] for entry in self.get("data/persons?is_guest=false")
        ]
        self.assertIn(str(person.id), ids)
        self.assertNotIn(str(guest.id), ids)

        guests = self.get("data/persons?is_guest=true")
        self.assertEqual([entry["id"] for entry in guests], [str(guest.id)])

    def test_full_name_is_filterable(self):
        # full_name is a hybrid whose SQL expression is a concat_ws inside
        # a trim, two functions SQLAlchemy types as NullType: casting the
        # value to it raised a CompileError, and the route answered
        # gazu.person.get_person_by_full_name() with a 500.
        person = Person.get_by(email="ema.doe@example.com")
        path = f"data/persons?full_name={quote('Ema Doe')}"

        persons = self.get(path)
        self.assertEqual(len(persons), 1)
        self.assertEqual(persons[0]["id"], str(person.id))

        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        persons = self.get(path)
        self.assertEqual(len(persons), 1)
        self.assertEqual(persons[0]["id"], str(person.id))

    def test_visible_columns_stay_filterable(self):
        person = Person.get_by(email="ema.doe@example.com")
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        persons = self.get(f"data/persons?first_name={person.first_name}")
        self.assertEqual(len(persons), 1)
        self.assertEqual(persons[0]["id"], str(person.id))

    def test_admin_still_filters_on_the_safe_columns(self):
        person = Person.get_by(email="ema.doe@example.com")
        person.update({"daily_salary": 320})
        persons = self.get("data/persons?daily_salary=320")
        self.assertEqual(len(persons), 1)
        self.assertEqual(persons[0]["id"], str(person.id))

    def test_secrets_are_never_filterable(self):
        person = Person.get_by(email="ema.doe@example.com")
        person.update({"totp_secret": "SECRETSEED"})
        self.get("data/persons?totp_secret=SECRETSEED", 400)


class PersonProtectedAccountTestCase(ApiDBTestCase):
    """
    Updates of a protected account, by another person and by the account
    itself.
    """

    NEW_EMAIL = "new.address@example.com"

    def setUp(self):
        super().setUp()
        self.addCleanup(
            setattr, config, "PROTECTED_ACCOUNTS", config.PROTECTED_ACCOUNTS
        )
        person = self.generate_fixture_person()
        self.person_id = str(person.id)
        self.email = person.email
        self.path = f"data/persons/{self.person_id}"
        config.PROTECTED_ACCOUNTS = [self.email]

    def get_email(self):
        return Person.get(self.person_id).email

    def test_another_person_cannot_change_its_email(self):
        self.put(self.path, {"email": self.NEW_EMAIL}, 403)
        self.assertEqual(self.get_email(), self.email)

    def test_unchanged_email_passes(self):
        self.put(self.path, {"email": self.email, "phone": "0123"})
        self.assertEqual(Person.get(self.person_id).phone, "0123")

    def test_the_account_changes_its_own_email(self):
        self.log_in(self.email)
        data = {"email": self.NEW_EMAIL, "current_password": "mypassword"}
        self.put(self.path, data)
        self.assertEqual(self.get_email(), self.NEW_EMAIL)

    def test_another_person_cannot_change_its_bot_flag(self):
        self.put(self.path, {"is_bot": True}, 403)
        self.assertFalse(Person.get(self.person_id).is_bot)

    def test_unchanged_bot_flag_passes(self):
        self.put(self.path, {"is_bot": False, "phone": "0123"})
        self.assertEqual(Person.get(self.person_id).phone, "0123")

    def test_another_person_cannot_deactivate_it(self):
        for value in (False, 0, None):
            with self.subTest(active=value):
                self.put(self.path, {"active": value}, 403)
        self.assertTrue(Person.get(self.person_id).active)

    def test_active_true_passes(self):
        self.put(self.path, {"active": True, "phone": "0123"})
        self.assertEqual(Person.get(self.person_id).phone, "0123")


@pytest.mark.real_bcrypt
class PersonOwnEmailTestCase(ApiDBTestCase):
    """
    The password reset link follows the email: changing one's own address
    asks for the current password, and a second factor when one is on.
    """

    NEW_EMAIL = "new.address@example.com"

    def setUp(self):
        super().setUp()
        self.artist = self.generate_fixture_user_cg_artist()
        self.path = f"data/persons/{self.artist['id']}"
        self.log_in_cg_artist()

    def get_email(self):
        return Person.get(self.artist["id"]).email

    def test_without_password(self):
        self.put(self.path, {"email": self.NEW_EMAIL}, 400)
        self.assertEqual(self.get_email(), self.artist["email"])

    def test_with_wrong_password(self):
        data = {"email": self.NEW_EMAIL, "current_password": "wrong"}
        self.put(self.path, data, 400)
        self.assertEqual(self.get_email(), self.artist["email"])

    def test_with_right_password(self):
        data = {"email": self.NEW_EMAIL, "current_password": "mypassword"}
        self.put(self.path, data)
        self.assertEqual(self.get_email(), self.NEW_EMAIL)

    def test_unchanged_email_needs_no_password(self):
        # Kitsu and gazu send the address back on every save.
        data = {"email": self.artist["email"], "first_name": "Jane"}
        self.put(self.path, data)
        self.assertEqual(Person.get(self.artist["id"]).first_name, "Jane")

    def test_with_two_factor_enabled(self):
        secret = pyotp.random_base32()
        Person.get(self.artist["id"]).update(
            {
                "totp_enabled": True,
                "totp_secret": secret,
                "preferred_two_factor_authentication": "totp",
            }
        )
        persons_service.clear_person_cache()
        data = {"email": self.NEW_EMAIL, "current_password": "mypassword"}
        refused = self.put(self.path, data, 400)
        self.assertTrue(refused["data"]["wrong_OTP"])
        self.put(self.path, {**data, "recovery_code": "wrong"}, 400)
        self.assertEqual(self.get_email(), self.artist["email"])
        self.put(self.path, {**data, "totp": pyotp.TOTP(secret).now()})
        self.assertEqual(self.get_email(), self.NEW_EMAIL)

    def test_admin_on_someone_else_needs_no_password(self):
        self.log_in_admin()
        self.put(self.path, {"email": self.NEW_EMAIL})
        self.assertEqual(self.get_email(), self.NEW_EMAIL)
