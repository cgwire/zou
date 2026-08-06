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
