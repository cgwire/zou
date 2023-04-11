from tests.base import ApiDBTestCase

from zou.app.services import persons_service


class PersonDepartmentTestCase(ApiDBTestCase):
    def setUp(self):
        super(PersonDepartmentTestCase, self).setUp()
        self.person = self.generate_fixture_person().serialize()
        self.department = self.generate_fixture_department().serialize()
        self.path = "/actions/persons/%s/departments" % self.person["id"]

    def test_add_to_department(self):
        person = self.person
        department = self.department
        persons_service.add_to_department(department["id"], person["id"])
        self.post(self.path + "/add", {"department_id": department["id"]})
        person = persons_service.get_person(person["id"])
        self.assertEqual(person["departments"][0], department["id"])

    def test_remove_from_department(self):
        person = self.person
        department = self.department
        persons_service.add_to_department(department["id"], person["id"])
        self.delete(self.path + "/" + department["id"])
        person = persons_service.get_person(person["id"])
        self.assertEqual(len(person["departments"]), 0)
