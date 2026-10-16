import pytest

from tests.base import ApiDBTestCase
from zou.app.exceptions import PersonNotFoundException
from zou.app.models.person import Person
from zou.app.services import persons_service


class PersonCacheInvalidationTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_fixture_person()

    def test_add_logs(self):
        person = persons_service.get_person_by_email("john.doe@example.com")
        person_raw = Person.get(person["id"])
        person_raw.update({"email": "jhon.doe.bis@example.com"})
        person = persons_service.get_person_by_email("john.doe@example.com")

        person = persons_service.update_person(
            person["id"], {"email": "john.doe2@example.com"}
        )
        with pytest.raises(PersonNotFoundException):
            persons_service.get_person_by_email("john.doe@example.com")
        person = persons_service.get_person_by_email("john.doe2@example.com")
