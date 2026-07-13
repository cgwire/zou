from tests.base import ApiDBTestCase

from zou.app.models.entity import Entity


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

    def test_get_schedule_sequence_items_for_episode(self):
        episode_2 = self.generate_fixture_episode(name="E02")
        sequence_2 = self.generate_fixture_sequence(
            name="S02", episode_id=episode_2.id
        )
        sequence_2_id = str(sequence_2.id)
        base_path = f"/data/projects/{self.project_id}/schedule-items/{self.task_type_id}/sequences"

        # Without episode filter, both sequences are returned.
        items = self.get(base_path)
        object_ids = {item["object_id"] for item in items}
        self.assertEqual(object_ids, {self.sequence_id, sequence_2_id})

        # Filtered on an episode, only its sequence is returned.
        items = self.get(f"{base_path}?episode_id={self.episode_id}")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], self.sequence_id)

    def test_get_schedule_episode_items(self):
        path = f"/data/projects/{self.project_id}/schedule-items/{self.task_type_id}/episodes"
        items = self.get(path)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], self.episode_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)

    def test_get_schedule_episode_items_for_episode(self):
        episode_2 = self.generate_fixture_episode(name="E02")
        episode_2_id = str(episode_2.id)
        base_path = f"/data/projects/{self.project_id}/schedule-items/{self.task_type_id}/episodes"

        # Without episode filter, both episodes are returned.
        items = self.get(base_path)
        object_ids = {item["object_id"] for item in items}
        self.assertEqual(object_ids, {self.episode_id, episode_2_id})

        # Filtered on an episode, only that episode is returned.
        items = self.get(f"{base_path}?episode_id={self.episode_id}")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], self.episode_id)

    def test_get_schedule_edit_items(self):
        edit = self.generate_fixture_edit()
        edit_id = str(edit.id)
        path = f"/data/projects/{self.project_id}/schedule-items/{self.task_type_id}/edits"
        items = self.get(path)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], edit_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)

    def test_get_schedule_edit_items_for_episode(self):
        edit_1 = self.generate_fixture_edit(
            name="Edit E01", parent_id=self.episode.id
        )
        edit_1_id = str(edit_1.id)
        episode_2 = self.generate_fixture_episode(name="E02")
        edit_2 = self.generate_fixture_edit(
            name="Edit E02", parent_id=episode_2.id
        )
        edit_2_id = str(edit_2.id)
        base_path = f"/data/projects/{self.project_id}/schedule-items/{self.task_type_id}/edits"

        # Without episode filter, both edits are returned.
        items = self.get(base_path)
        object_ids = {item["object_id"] for item in items}
        self.assertEqual(object_ids, {edit_1_id, edit_2_id})

        # Filtered on an episode, only its edit is returned.
        items = self.get(f"{base_path}?episode_id={self.episode_id}")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], edit_1_id)

    def test_get_schedule_asset_type_items(self):
        path = f"/data/projects/{self.project_id}/schedule-items/{self.task_type_id}/asset-types"
        items = self.get(path)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["object_id"], self.asset_type_id)
        self.assertEqual(items[0]["task_type_id"], self.task_type_id)
        self.assertEqual(items[0]["project_id"], self.project_id)

    def test_get_schedule_asset_type_items_for_episode(self):
        self.generate_fixture_asset_types()
        episode_1 = self.episode
        episode_2 = self.generate_fixture_episode(name="E02")
        episode_2_id = str(episode_2.id)
        asset_type_character_id = str(self.asset_type_character.id)

        Entity.create(
            name="Tree E01",
            project_id=self.project.id,
            entity_type_id=self.asset_type.id,
            source_id=episode_1.id,
        )
        Entity.create(
            name="Rabbit E02",
            project_id=self.project.id,
            entity_type_id=self.asset_type_character.id,
            source_id=episode_2.id,
        )
        base_path = f"/data/projects/{self.project_id}/schedule-items/{self.task_type_id}/asset-types"

        # Filtered on the first episode, only its asset type is returned.
        items = self.get(f"{base_path}?episode_id={self.episode_id}")
        object_ids = {item["object_id"] for item in items}
        self.assertEqual(object_ids, {self.asset_type_id})

        # Filtered on the second episode, only its asset type is returned.
        items = self.get(f"{base_path}?episode_id={episode_2_id}")
        object_ids = {item["object_id"] for item in items}
        self.assertEqual(object_ids, {asset_type_character_id})
