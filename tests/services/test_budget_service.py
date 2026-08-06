import datetime

from tests.base import ApiDBTestCase

from zou.app.models.budget import Budget
from zou.app.models.budget_entry import BudgetEntry
from zou.app.services.exception import (
    BudgetNotFoundException,
    BudgetEntryNotFoundException,
)

from zou.app.services import budget_service


class BudgetServiceTestCase(ApiDBTestCase):
    """
    Budgets of a production and the lines they are made of. A second
    production stands beside the first throughout, since every listing here
    is meant to be scoped to one.
    """

    def setUp(self):
        super().setUp()

        self.project_alt = self.generate_fixture_project("Project 2")
        self.project = self.generate_fixture_project()
        self.generate_fixture_department()
        self.generate_fixture_person()

    def a_budget(self, name="Test Budget", project=None):
        self.budget = Budget.create(
            project_id=(project or self.project).id, name=name, revision=1
        )
        return self.budget

    def an_entry(self, budget=None, **overrides):
        """
        One line of a budget, with the parts a case does not care about
        filled in.
        """
        fields = {
            "budget_id": (budget or self.a_budget()).id,
            "department_id": self.department.id,
            "start_date": datetime.date.today(),
            "months_duration": 12,
            "daily_salary": 500,
            "position": "artist",
            "seniority": "junior",
            **overrides,
        }
        return BudgetEntry.create(**fields)

    def test_get_budget_raw(self):
        budget = self.a_budget()

        self.assertEqual(
            budget_service.get_budget_raw(str(budget.id)).id, budget.id
        )
        with self.assertRaises(BudgetNotFoundException):
            budget_service.get_budget_raw("123")

    def test_get_budget(self):
        budget = self.a_budget()

        result = budget_service.get_budget(str(budget.id))

        self.assertEqual(result["id"], str(budget.id))
        self.assertEqual(result["name"], "Test Budget")

    def test_get_budgets_is_scoped_to_the_production(self):
        self.assertEqual(budget_service.get_budgets(str(self.project.id)), [])
        for name in ["Test Budget 1", "Test Budget 2"]:
            budget_service.create_budget(str(self.project.id), name, "USD")
        budget_service.create_budget(
            str(self.project_alt.id), "Test Budget 3", "USD"
        )

        result = budget_service.get_budgets(str(self.project.id))

        self.assertEqual(
            sorted(budget["name"] for budget in result),
            ["Test Budget 1", "Test Budget 2"],
        )

    def test_create_budget_numbers_the_revisions(self):
        """
        Each budget of a production takes the revision after the highest one
        already there, which is per production and not global.
        """
        first = budget_service.create_budget(
            str(self.project.id), "New Budget", "USD"
        )
        second = budget_service.create_budget(
            str(self.project.id), "Second Budget", "EUR"
        )
        third = budget_service.create_budget(
            str(self.project.id), "Third Budget", "EUR"
        )
        elsewhere = budget_service.create_budget(
            str(self.project_alt.id), "Alt Budget", "USD"
        )

        self.assertEqual(first["currency"], "USD")
        self.assertEqual(
            [budget["revision"] for budget in [first, second, third]],
            [1, 2, 3],
        )
        self.assertEqual(elsewhere["revision"], 1)

    def test_update_budget(self):
        budget = self.a_budget()

        budget_service.update_budget(
            str(budget.id), name="Updated Budget", currency="EUR"
        )

        updated = budget_service.get_budget(str(budget.id))
        self.assertEqual(updated["name"], "Updated Budget")
        self.assertEqual(updated["currency"], "EUR")

    def test_update_budget_leaves_out_what_it_is_not_given(self):
        budget = self.a_budget()
        budget_service.update_budget(str(budget.id), currency="EUR")

        budget_service.update_budget(str(budget.id), name="Renamed")

        updated = budget_service.get_budget(str(budget.id))
        self.assertEqual(updated["name"], "Renamed")
        self.assertEqual(updated["currency"], "EUR")

    def test_delete_budget_takes_its_entries_with_it(self):
        budget = self.a_budget()
        entry_id = str(self.an_entry(budget=budget).id)

        result = budget_service.delete_budget(str(budget.id))

        self.assertEqual(result["id"], str(budget.id))
        with self.assertRaises(BudgetNotFoundException):
            budget_service.get_budget_raw(str(budget.id))
        with self.assertRaises(BudgetEntryNotFoundException):
            budget_service.get_budget_entry_raw(entry_id)

    def test_get_budget_entries_is_scoped_to_the_budget(self):
        budget = self.a_budget()
        other_budget = self.a_budget("Other Budget")
        self.assertEqual(budget_service.get_budget_entries(str(budget.id)), [])
        entry = self.an_entry(budget=budget)
        self.an_entry(budget=other_budget)

        result = budget_service.get_budget_entries(str(budget.id))

        self.assertEqual([line["id"] for line in result], [str(entry.id)])

    def test_get_budget_entry_raw(self):
        entry = self.an_entry()

        self.assertEqual(
            budget_service.get_budget_entry_raw(str(entry.id)).id, entry.id
        )
        with self.assertRaises(BudgetEntryNotFoundException):
            budget_service.get_budget_entry_raw("123")

    def test_get_budget_entry(self):
        entry = self.an_entry()

        result = budget_service.get_budget_entry(str(entry.id))

        self.assertEqual(result["id"], str(entry.id))

    def test_create_budget_entry(self):
        budget = self.a_budget()

        result = budget_service.create_budget_entry(
            str(budget.id),
            str(self.department.id),
            datetime.date.today(),
            12,
            500,
            "artist",
            "junior",
            str(self.person.id),
        )

        entry = BudgetEntry.get(result["id"])
        self.assertEqual(entry.department_id, self.department.id)
        self.assertEqual(entry.person_id, self.person.id)
        self.assertEqual(entry.position, "artist")
        # Created with an empty exception map rather than a null one, so the
        # column is always a map for whoever reads it.
        self.assertEqual(entry.exceptions, {})

    def test_update_budget_entry(self):
        entry = self.an_entry()

        result = budget_service.update_budget_entry(
            str(entry.id), {"position": "lead", "daily_salary": 600}
        )

        entry = BudgetEntry.get(result["id"])
        self.assertEqual(entry.position, "lead")
        self.assertEqual(entry.daily_salary, 600)

    def test_update_budget_entry_cleans_the_exceptions(self):
        """
        The exception map holds the months whose salary departs from the
        line: a null map becomes empty, months at zero or null are dropped
        rather than stored, and what is kept is stored as an int.
        """
        entry = self.an_entry()
        cases = {
            "a month that departs": ({"3": "700"}, {"3": 700}),
            "a month at zero": ({"3": 700, "4": 0}, {"3": 700}),
            "a month at null": ({"3": 700, "4": None}, {"3": 700}),
            "no map at all": (None, {}),
        }
        for reason, (given, expected) in cases.items():
            with self.subTest(reason=reason):
                result = budget_service.update_budget_entry(
                    str(entry.id), {"exceptions": given}
                )
                self.assertEqual(result["exceptions"], expected)

    def test_update_budget_entry_leaves_the_exceptions_alone(self):
        # A payload that says nothing about them keeps what is there.
        entry = self.an_entry(exceptions={"3": 700})

        result = budget_service.update_budget_entry(
            str(entry.id), {"position": "lead"}
        )

        self.assertEqual(result["exceptions"], {"3": 700})

    def test_delete_budget_entry(self):
        entry = self.an_entry()

        budget_service.delete_budget_entry(str(entry.id))

        with self.assertRaises(BudgetEntryNotFoundException):
            budget_service.get_budget_entry_raw(str(entry.id))
