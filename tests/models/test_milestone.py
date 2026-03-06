from tests.base import ApiDBTestCase
from zou.app.utils import fields


class MilestoneTestCase(ApiDBTestCase):
    def setUp(self):
        super(MilestoneTestCase, self).setUp()
        self.generate_base_context()
        self.project_id = str(self.project.id)
        self.task_type_id = str(self.task_type.id)
        for i in range(3):
            self.post(
                "data/milestones",
                {
                    "name": "MS%d" % i,
                    "date": "2024-0%d-15" % (i + 1),
                    "project_id": self.project_id,
                    "task_type_id": self.task_type_id,
                },
            )

    def test_get_milestones(self):
        milestones = self.get("data/milestones")
        self.assertEqual(len(milestones), 3)

    def test_get_milestone(self):
        milestone = self.get_first("data/milestones")
        milestone_again = self.get(
            "data/milestones/%s" % milestone["id"]
        )
        self.assertEqual(milestone, milestone_again)
        self.get_404("data/milestones/%s" % fields.gen_uuid())

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
        self.put("data/milestones/%s" % milestone["id"], data)
        milestone_again = self.get(
            "data/milestones/%s" % milestone["id"]
        )
        self.assertEqual(data["name"], milestone_again["name"])
        self.put_404("data/milestones/%s" % fields.gen_uuid(), data)

    def test_delete_milestone(self):
        milestones = self.get("data/milestones")
        self.assertEqual(len(milestones), 3)
        milestone = milestones[0]
        self.delete("data/milestones/%s" % milestone["id"])
        milestones = self.get("data/milestones")
        self.assertEqual(len(milestones), 2)
        self.delete_404("data/milestones/%s" % fields.gen_uuid())
