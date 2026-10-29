from tests.base import ApiDBTestCase
from zou.app.utils import fields


class MilestoneTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_base_context()
        self.project_id = str(self.project.id)
        self.task_type_id = str(self.task_type.id)
        for i in range(3):
            self.post(
                "data/milestones",
                {
                    "name": f"MS{i}",
                    "date": f"2024-0{i + 1}-15",
                    "project_id": self.project_id,
                    "task_type_id": self.task_type_id,
                },
            )

    def test_get_milestones(self):
        milestones = self.get("data/milestones")
        self.assertEqual(len(milestones), 3)

    def test_get_milestone(self):
        milestone = self.get_first("data/milestones")
        milestone_again = self.get(f"data/milestones/{milestone['id']}")
        self.assertEqual(milestone, milestone_again)
        self.get_404(f"data/milestones/{fields.gen_uuid()}")

    def test_create_milestone(self):
        data = {
            "name": "MS4",
            "date": "2024-12-31",
            "project_id": self.project_id,
            "task_type_id": self.task_type_id,
        }
        milestone = self.post("data/milestones", data)
        self.assertIsNotNone(milestone["id"])
        milestones = self.get("data/milestones")
        self.assertEqual(len(milestones), 4)

    def test_update_milestone(self):
        milestone = self.get_first("data/milestones")
        data = {"name": "Updated Milestone"}
        self.put(f"data/milestones/{milestone['id']}", data)
        milestone_again = self.get(f"data/milestones/{milestone['id']}")
        self.assertEqual(data["name"], milestone_again["name"])
        self.put_404(f"data/milestones/{fields.gen_uuid()}", data)

    def test_update_milestone_date_with_a_utc_designator(self):
        # PostgreSQL takes a Z after a date alone, Python's fromisoformat
        # does not: the date check has to keep up with PostgreSQL.
        milestone = self.get_first("data/milestones")
        self.put(f"data/milestones/{milestone['id']}", {"date": "2024-12-31Z"})
        milestone_again = self.get(f"data/milestones/{milestone['id']}")
        self.assertEqual(milestone_again["date"], "2024-12-31")

    def test_update_milestone_cannot_move_it_to_another_project(self):
        # The permission hook checks the project stored on the milestone, so
        # a body naming another one would push the row into a production the
        # caller was never checked against.
        self.generate_fixture_project_standard()
        other_project_id = str(self.project_standard.id)
        milestone = self.get_first("data/milestones")
        self.put(
            f"data/milestones/{milestone['id']}",
            {"name": "Moved", "project_id": other_project_id},
        )
        milestone_again = self.get(f"data/milestones/{milestone['id']}")
        self.assertEqual(milestone_again["name"], "Moved")
        self.assertEqual(milestone_again["project_id"], self.project_id)

    def test_delete_milestone(self):
        milestones = self.get("data/milestones")
        self.assertEqual(len(milestones), 3)
        milestone = milestones[0]
        self.delete(f"data/milestones/{milestone['id']}")
        milestones = self.get("data/milestones")
        self.assertEqual(len(milestones), 2)
        self.delete_404(f"data/milestones/{fields.gen_uuid()}")

    def test_create_milestone_with_type_and_color(self):
        milestone = self.post(
            "data/milestones",
            {
                "name": "Client review",
                "date": "2024-06-01",
                "project_id": self.project_id,
                "color": "#ff0000",
                "milestone_type": "review",
            },
        )
        self.assertEqual(milestone["color"], "#ff0000")
        self.assertEqual(milestone["milestone_type"], "review")
        milestone_again = self.get(f"data/milestones/{milestone['id']}")
        self.assertEqual(milestone_again["milestone_type"], "review")

    def test_create_milestone_defaults(self):
        milestone = self.post(
            "data/milestones",
            {
                "name": "Plain",
                "date": "2024-06-01",
                "project_id": self.project_id,
            },
        )
        self.assertIsNone(milestone["color"])
        self.assertEqual(milestone["milestone_type"], "other")

    def test_update_milestone_type_and_color(self):
        milestone = self.get_first("data/milestones")
        self.put(
            f"data/milestones/{milestone['id']}",
            {
                "color": "#00AA11",
                "milestone_type": "delivery",
            },
        )
        milestone_again = self.get(f"data/milestones/{milestone['id']}")
        self.assertEqual(milestone_again["color"], "#00AA11")
        self.assertEqual(milestone_again["milestone_type"], "delivery")
        self.put(f"data/milestones/{milestone['id']}", {"color": None})
        milestone_again = self.get(f"data/milestones/{milestone['id']}")
        self.assertIsNone(milestone_again["color"])

    def test_create_milestone_with_invalid_values(self):
        base = {
            "name": "Bad",
            "date": "2024-06-01",
            "project_id": self.project_id,
        }
        for invalid in [
            {"milestone_type": "party"},
            {"milestone_type": None},
            {"color": "red"},
            {"color": "#fff"},
            {"color": "#gggggg"},
            {"color": "#ff0000\n"},
            {"color": 123},
        ]:
            self.post("data/milestones", {**base, **invalid}, 400)
        self.assertEqual(len(self.get("data/milestones")), 3)

    def test_update_milestone_with_invalid_values(self):
        milestone = self.get_first("data/milestones")
        for invalid in [
            {"milestone_type": "party"},
            {"milestone_type": None},
            {"color": "#12345"},
        ]:
            self.put(f"data/milestones/{milestone['id']}", invalid, 400)
        milestone_again = self.get(f"data/milestones/{milestone['id']}")
        self.assertEqual(milestone_again["milestone_type"], "other")
        self.assertIsNone(milestone_again["color"])

    def test_milestones_on_same_date(self):
        for name, milestone_type in [
            ("Kickoff", "kickoff"),
            ("Due", "delivery"),
        ]:
            self.post(
                "data/milestones",
                {
                    "name": name,
                    "date": "2024-09-01",
                    "project_id": self.project_id,
                    "milestone_type": milestone_type,
                },
            )
        milestones = self.get(f"data/projects/{self.project_id}/milestones")
        same_day = [m for m in milestones if m["date"] == "2024-09-01"]
        self.assertEqual(
            sorted(m["milestone_type"] for m in same_day),
            ["delivery", "kickoff"],
        )
        self.assertEqual(
            set(same_day[0].keys()),
            {
                "id",
                "date",
                "name",
                "color",
                "milestone_type",
                "project_id",
                "task_type_id",
            },
        )
