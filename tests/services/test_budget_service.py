import datetime

from tests.base import ApiDBTestCase

from zou.app.models.budget import Budget
from zou.app.models.budget_entry import BudgetEntry
from zou.app.services.exception import (
    BudgetNotFoundException, BudgetEntryNotFoundException
)

from zou.app.services import budget_service


class BudgetServiceTestCase(ApiDBTestCase):

    def setUp(self):
        super(BudgetServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.project_alt = self.generate_fixture_project("Project 2")
        self.project = self.generate_fixture_project()
        self.generate_fixture_department()
        self.generate_fixture_person()


    def generate_fixture_budget(self):
        self.budget = Budget.create(
            project_id=self.project.id,
            name="Test Budget",
            revision=1
        )
        return self.budget

    def test_get_budget_raw(self):
        with self.assertRaises(BudgetNotFoundException):
            budget_service.get_budget_raw("123")


        budget = Budget.create(
            project_id=self.project.id,
            name="Test Budget",
            revision=1
        )
        result = budget_service.get_budget_raw(str(budget.id))
        self.assertEqual(result.id, budget.id)

    def test_get_budget(self):
        budget = Budget.create(
            project_id=self.project.id,
            name="Test Budget",
            revision=1
        )
        result = budget_service.get_budget(str(budget.id))
        self.assertEqual(result["id"], str(budget.id))
        self.assertEqual(result["name"], "Test Budget")

    def test_get_budgets(self):
        result = budget_service.get_budgets(str(self.project.id))
        self.assertEqual(len(result), 0)

        budget_service.create_budget(
            str(self.project.id),
            "Test Budget 1",
            "USD"
        )
        budget_service.create_budget(
            str(self.project.id),
            "Test Budget 2",
            "USD"
        )
        budget_service.create_budget(
            str(self.project_alt.id),
            "Test Budget 3",
            "USD"
        )
        result = budget_service.get_budgets(str(self.project.id))
        self.assertEqual(len(result), 2)

    def test_create_budget(self):
        result = budget_service.create_budget(
            str(self.project.id),
            "New Budget",
            "USD"
        )
        self.assertEqual(result["name"], "New Budget")
        self.assertEqual(result["currency"], "USD")
        self.assertEqual(result["revision"], 1)

        result = budget_service.create_budget(
            str(self.project.id),
            "Second Budget",
            "EUR"
        )
        budget = Budget.get(result["id"])
        self.assertEqual(budget.revision, 2)

    def test_update_budget(self):
        budget_dict = Budget.create(
            project_id=self.project.id,
            name="Test Budget",
            revision=1
        )
        budget_service.update_budget(
            str(budget_dict.id),
            name="Updated Budget",
            currency="EUR"
        )
        budget = budget_service.get_budget(str(budget_dict.id))
        self.assertEqual(budget["name"], "Updated Budget")
        self.assertEqual(budget["currency"], "EUR")

    def test_delete_budget(self):
        budget = Budget.create(
            project_id=self.project.id,
            name="Test Budget",
            revision=1
        )
        budget_entry = BudgetEntry.create(
            budget_id=budget.id,
            department_id=self.department.id,
            start_date=datetime.date.today(),
            months_duration=12,
            daily_salary=500,
        )
        budget_entry_id = str(budget_entry.id)
        result = budget_service.delete_budget(str(budget.id))
        self.assertEqual(result["id"], str(budget.id))

        with self.assertRaises(BudgetNotFoundException):
            budget_service.get_budget_raw(str(budget.id))

        with self.assertRaises(BudgetEntryNotFoundException):
            budget_service.get_budget_entry_raw(budget_entry_id)

    def test_get_budget_entries(self):
        self.generate_fixture_budget()
        result = budget_service.get_budget_entries(str(self.budget.id))
        self.assertEqual(len(result), 0)

    def test_get_budget_entry_raw(self):
        self.generate_fixture_budget()

        budget_entry = BudgetEntry.create(
            budget_id=self.budget.id,
            department_id=self.department.id,
            start_date=datetime.date.today(),
            months_duration=12,
            daily_salary=500,
        )
        with self.assertRaises(BudgetEntryNotFoundException):
            budget_service.get_budget_entry_raw("123")

        budget_entry_test = budget_service.get_budget_entry_raw(
            str(budget_entry.id)
        )
        self.assertEqual(str(budget_entry_test.id), str(budget_entry.id))

    def test_get_budget_entry(self):
        self.generate_fixture_budget()
        budget_entry = BudgetEntry.create(
            budget_id=self.budget.id,
            department_id=self.department.id,
            start_date=datetime.date.today(),
            months_duration=12,
            daily_salary=500,
            position="artist",
            seniority="junior"
        )
        result = budget_service.get_budget_entry(str(budget_entry.id))
        self.assertEqual(result["id"], str(budget_entry.id))

    def test_create_budget_entry(self):
        self.generate_fixture_budget()
        result = budget_service.create_budget_entry(
            str(self.budget.id),
            str(self.department.id),
            datetime.date.today(),
            12,
            500,
            "artist",
            "junior",
            str(self.person.id)
        )
        budget_entry = BudgetEntry.get(result["id"])
        self.assertEqual(budget_entry.department_id, self.department.id)
        self.assertEqual(budget_entry.person_id, self.person.id)
        self.assertEqual(budget_entry.position, "artist")

    def test_update_budget_entry(self):
        self.generate_fixture_budget()
        budget_entry = BudgetEntry.create(
            budget_id=self.budget.id,
            department_id=self.department.id,
            start_date=datetime.date.today(),
            months_duration=12,
            daily_salary=500,
            position="artist",
            seniority="junior"
        )
        result = budget_service.update_budget_entry(
            str(budget_entry.id),
            {"position": "lead", "daily_salary": 600}
        )
        budget_entry = BudgetEntry.get(result["id"])
        self.assertEqual(budget_entry.position, "lead")
        self.assertEqual(budget_entry.daily_salary, 600)

    def test_delete_budget_entry(self):
        self.generate_fixture_budget()
        budget_entry = BudgetEntry.create(
            budget_id=self.budget.id,
            department_id=self.department.id,
            start_date=datetime.date.today(),
            months_duration=12,
            daily_salary=500,
            position="artist",
            seniority="junior"
        )
        budget_service.delete_budget_entry(str(budget_entry.id))
        with self.assertRaises(BudgetEntryNotFoundException):
            budget_service.get_budget_entry_raw(str(budget_entry.id))