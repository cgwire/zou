from tests.base import ApiDBTestCase
from mixer.backend.flask import mixer
from zou.app.utils import date_helpers


class DateTestCase(ApiDBTestCase):
    def setUp(self):
        super(DateTestCase, self).setUp()
        mixer.init_app(self.flask_app)
        self.now = date_helpers.get_utc_now_datetime()
        self.generate_fixture_person()

    def test_create_date(self):
        self.assertIsNotNone(self.person.created_at)
        self.assertGreater(self.person.created_at, self.now)

    def test_update_date(self):
        self.person.last_name = "Doe"
        self.person.save()
        self.assertIsNotNone(self.person.updated_at)
        self.assertGreater(self.person.updated_at, self.person.created_at)
