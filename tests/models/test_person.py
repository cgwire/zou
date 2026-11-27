import unittest

from tests.base import ApiDBTestCase
from zou.app.models.person import (
    Person,
    normalize_country,
    normalize_locale,
)


class NormalizeCountryTestCase(unittest.TestCase):
    """
    Unit coverage for normalize_country, the single source of truth shared
    by the model validator, the API guard and the CSV import.
    """

    def test_valid_codes_are_trimmed_and_uppercased(self):
        for value, expected in [("fr", "FR"), ("FR", "FR"), (" us ", "US")]:
            self.assertEqual(normalize_country(value), (True, expected))

    def test_empty_values_mean_no_country(self):
        for value in [None, "", "   "]:
            self.assertEqual(normalize_country(value), (True, None))

    def test_malformed_values_are_rejected(self):
        for value in ["France", "FRA", "f", "f1", "éé", 123, ["FR"], 1.5]:
            self.assertEqual(normalize_country(value), (False, None))


class NormalizeLocaleTestCase(unittest.TestCase):
    """
    Unit coverage for normalize_locale, the single source of truth shared by
    the model validator and the API guard.
    """

    def test_valid_locales_are_trimmed_and_kept(self):
        for value, expected in [
            ("en_US", "en_US"),
            ("fr_FR", "fr_FR"),
            (" pt_BR ", "pt_BR"),
            ("fr", "fr"),
            ("en_us", "en_us"),  # Babel parses it back; casing is left as-is
        ]:
            self.assertEqual(normalize_locale(value), (True, expected))

    def test_empty_values_mean_no_locale(self):
        for value in [None, "", "   "]:
            self.assertEqual(normalize_locale(value), (True, None))

    def test_unparseable_values_are_rejected(self):
        for value in [
            "zz_ZZ",  # well-formed but unknown to Babel
            "notlocale",
            "en-US",  # wrong separator -> ValueError
            "fr_FR_x",  # malformed identifier -> ValueError
            "en_US_POSIX",  # valid Babel variant but too long for the column
            123,
            ["fr_FR"],
            1.5,
        ]:
            self.assertEqual(normalize_locale(value), (False, None))


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


class PersonModelTestCase(PersonFixtureTestCase):
    def test_repr(self):
        self.assertEqual(str(self.person), "<Person John Doe>")
        self.person.first_name = "Léon"
        self.assertEqual(str(self.person), "<Person Léon Doe>")

    def test_present(self):
        person = self.get_first("data/persons")
        person_model = Person.get(person["id"])
        person_dict = person_model.present_minimal()
        self.assertEqual(person_dict["departments"], [])
        person_dict = person_model.present_minimal(relations=True)
        self.assertEqual(person_dict["departments"], [])

    def test_country_validator_never_raises_on_direct_write(self):
        # Direct writes (SSO sign-in, imports, scripts) bypass the API guard,
        # so the model validator must silently discard bad input instead of
        # raising.
        person = Person.get_by(email="ema.doe@example.com")
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
        person = Person.get_by(email="ema.doe@example.com")
        person.update({"country": "FR"})
        self.assertNotIn("country", person.present_minimal())
        safe = person.serialize_safe()
        self.assertEqual(safe["country"], "FR")

    def test_locale_validator_never_raises_on_direct_write(self):
        # Direct writes (SSO sign-in, imports, scripts) bypass the API guard,
        # so the model validator must silently discard bad input instead of
        # persisting a value that would break later reads.
        person = Person.get_by(email="ema.doe@example.com")
        person.update({"locale": "zz_ZZ"})
        self.assertIsNone(person.locale)
        person.update({"locale": ["fr_FR"]})
        self.assertIsNone(person.locale)
        person.update({"locale": "en-US"})
        self.assertIsNone(person.locale)
        person.update({"locale": " fr_FR "})
        self.assertEqual(str(person.locale), "fr_FR")
