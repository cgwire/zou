from tests.blueprints.source.shotgun.base import ShotgunTestCase
from zou.app import config
from zou.app.models.person import Person


class ImportShotgunPersonTestCase(ShotgunTestCase):
    def setUp(self):
        super().setUp()

    def test_remove_person(self):
        self.load_fixture("persons")
        person_id = Person.get_by(shotgun_id=2).id
        self.post("/import/shotgun/remove/person", {"id": 2}, 200)
        self.assertIsNone(Person.get(person_id))

    def test_remove_protected_person(self):
        self.load_fixture("persons")
        person = Person.get_by(shotgun_id=2)
        person_id = person.id
        self.addCleanup(
            setattr, config, "PROTECTED_ACCOUNTS", config.PROTECTED_ACCOUNTS
        )
        config.PROTECTED_ACCOUNTS = [person.email]
        self.post("/import/shotgun/remove/person", {"id": 2}, 403)
        self.assertIsNotNone(Person.get(person_id))

    def test_import_persons(self):
        self.persons = self.load_fixture("persons")
        self.assertEqual(len(self.persons), 2)

        self.persons = self.get("data/persons")
        self.assertEqual(len(self.persons), 3)
        person = next(p for p in self.persons if p["shotgun_id"] == 1)
        self.assertEqual(person["active"], True)

    def test_import_persons_twice(self):
        self.persons = self.load_fixture("persons")
        self.persons = self.load_fixture("persons")
        self.assertEqual(len(self.persons), 2)

        self.persons = self.get("data/persons")
        self.assertEqual(len(self.persons), 3)

    def test_import_person(self):
        sg_person = {
            "email": "james.doe@example.com",
            "firstname": "James",
            "lastname": "Doe",
            "login": "jamie",
            "id": 3,
            "sg_status_list": "dis",
            "type": "HumanUser",
        }

        api_path = "/import/shotgun/persons"
        self.persons = self.post(api_path, [sg_person], 200)
        self.assertEqual(len(self.persons), 1)

        self.persons = self.get("data/persons")
        self.assertEqual(len(self.persons), 2)

        person = self.persons[0]
        if person["first_name"] != "James":
            person = self.persons[1]
        self.assertEqual(person["first_name"], sg_person["firstname"])
        self.assertEqual(person["last_name"], sg_person["lastname"])
        self.assertEqual(person["shotgun_id"], sg_person["id"])
        self.assertEqual(person["desktop_login"], sg_person["login"])
        self.assertEqual(person["active"], False)
        self.assertEqual(person["role"], "user")

    def test_import_admin(self):
        sg_person = {
            "email": "james.doe@example.com",
            "firstname": "James",
            "lastname": "Doe",
            "login": "jamie",
            "id": 3,
            "sg_status_list": "dis",
            "type": "HumanUser",
            "permission_rule_set": {"name": "Admin"},
        }

        api_path = "/import/shotgun/persons"
        self.persons = self.post(api_path, [sg_person], 200)
        self.assertEqual(len(self.persons), 1)

        self.persons = self.get("data/persons")
        self.assertEqual(len(self.persons), 2)

        person = next(p for p in self.persons if p["shotgun_id"] == 3)
        self.assertEqual(person["role"], "admin")

    def test_import_person_matched_by_email(self):
        person = Person.create(
            first_name="James",
            last_name="Doe",
            email="james.doe@example.com",
        )
        sg_person = {
            "email": "james.doe@example.com",
            "firstname": "James",
            "lastname": "Doe",
            "login": "jamie",
            "id": 3,
            "type": "HumanUser",
        }
        self.post("/import/shotgun/persons", [sg_person], 200)
        self.assertEqual(Person.get(person.id).shotgun_id, 3)
        self.assertEqual(len(self.get("data/persons")), 2)
