from tests.base import ApiDBTestCase

from zou.app.models.budget import Budget
from zou.app.models.budget_entry import BudgetEntry

from zou.app.utils import fields


class BudgetTestCase(ApiDBTestCase):

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_department()
        self.project_id = str(self.project.id)

    def new_budget(self, name="Quote", currency="EUR"):
        return self.post(
            "data/budgets",
            {
                "project_id": self.project_id,
                "name": name,
                "currency": currency,
            },
        )

    def test_crud_budget(self):
        budget = self.new_budget()
        self.assertIsNotNone(budget["id"])
        self.assertEqual(budget["project_id"], self.project_id)

        budgets = self.get("data/budgets")
        self.assertEqual(len(budgets), 1)
        self.assertEqual(
            self.get(f"data/budgets/{budget['id']}")["name"], "Quote"
        )
        self.get_404(f"data/budgets/{fields.gen_uuid()}")

        self.put(f"data/budgets/{budget['id']}", {"currency": "USD"})
        self.assertEqual(
            self.get(f"data/budgets/{budget['id']}")["currency"], "USD"
        )

        self.delete(f"data/budgets/{budget['id']}")
        self.get_404(f"data/budgets/{budget['id']}")

    def test_budget_routes_are_admin_only(self):
        """
        The generic routes are stricter than the per project ones, which a
        manager of the project may use. build_filters accepts any column, so
        a looser guard here would turn ?daily_salary=320 into a salary search
        over every production.
        """
        budget = self.new_budget()
        self.generate_fixture_user_manager()
        self.log_in_manager()

        self.get("data/budgets", 403)
        self.get(f"data/budgets/{budget['id']}", 403)
        self.get("data/budget-entries", 403)

    def test_budget_revision_is_protected(self):
        """
        revision identifies the quote, a PUT must not move it. It used to be
        declared as a class attribute, which BaseModelResource.__init__
        overwrites on the instance, so the declaration did nothing.
        """
        budget = self.new_budget()
        self.put(
            f"data/budgets/{budget['id']}", {"revision": 42, "name": "Quote 2"}
        )
        budget_again = self.get(f"data/budgets/{budget['id']}")
        self.assertEqual(budget_again["revision"], budget["revision"])
        self.assertEqual(budget_again["name"], "Quote 2")


class BudgetEntryTestCase(ApiDBTestCase):

    def setUp(self):
        super().setUp()
        self.generate_fixture_project()
        self.generate_fixture_department()
        self.budget = Budget.create(
            project_id=self.project.id, name="Quote", revision=1
        )
        self.budget_id = str(self.budget.id)
        self.department_id = str(self.department.id)

    def new_entry(self, daily_salary=320):
        return self.post(
            "data/budget-entries",
            {
                "budget_id": self.budget_id,
                "department_id": self.department_id,
                "start_date": "2026-01-01",
                "months_duration": 3,
                "daily_salary": daily_salary,
            },
        )

    def test_crud_budget_entry(self):
        entry = self.new_entry()
        self.assertEqual(entry["budget_id"], self.budget_id)

        self.assertEqual(len(self.get("data/budget-entries")), 1)
        self.get_404(f"data/budget-entries/{fields.gen_uuid()}")

        self.put(f"data/budget-entries/{entry['id']}", {"months_duration": 6})
        self.assertEqual(
            self.get(f"data/budget-entries/{entry['id']}")["months_duration"],
            6,
        )

        self.delete(f"data/budget-entries/{entry['id']}")
        self.get_404(f"data/budget-entries/{entry['id']}")

    def test_budget_id_is_protected(self):
        """
        A BudgetEntry has no project_id for the base class to protect, so
        budget_id is what ties it to a production: a PUT must not move the
        entry to another budget.
        """
        entry = self.new_entry()
        other_budget = Budget.create(
            project_id=self.project.id, name="Other", revision=1
        )
        self.put(
            f"data/budget-entries/{entry['id']}",
            {"budget_id": str(other_budget.id)},
        )
        self.assertEqual(
            BudgetEntry.get(entry["id"]).budget_id, self.budget.id
        )
