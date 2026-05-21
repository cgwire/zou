from tests.base import ApiDBTestCase


class ProjectScheduleRouteTestCase(ApiDBTestCase):
    def setUp(self):
        super(ProjectScheduleRouteTestCase, self).setUp()

        self.generate_shot_suite()
        self.generate_assigned_task()
        self.generate_fixture_shot_task()
        self.project_id = str(self.project.id)
        self.task_type_id = str(self.task_type.id)
        self.task_type_animation_id = str(self.task_type_animation.id)
        self.sequence_id = str(self.sequence.id)
        self.episode_id = str(self.episode.id)
        self.asset_type_id = str(self.asset_type.id)

    def test_get_schedule_items(self):
        path = f"/data/projects/{self.project_id}/schedule-items/task-types"
        items = self.get(path)
        self.assertEqual(len(items), 2)
        task_type_ids = [item["task_type_id"] for item in items]
        self.assertTrue(str(self.task_type_id) in task_type_ids)
        self.assertTrue(str(self.task_type_animation_id) in task_type_ids)

    def test_get_schedule_sequence_items(self):
        path = f"/data/projects/{self.project_id}/schedule-items/{self.task_type_id}/sequences"
        items = self.get(path)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], self.sequence_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)

    def test_get_schedule_episode_items(self):
        path = f"/data/projects/{self.project_id}/schedule-items/{self.task_type_id}/episodes"
        items = self.get(path)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], self.episode_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)

    def test_get_schedule_asset_type_items(self):
        path = f"/data/projects/{self.project_id}/schedule-items/{self.task_type_id}/asset-types"
        items = self.get(path)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], self.asset_type_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)
