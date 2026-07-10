from tests.base import ApiDBTestCase

from zou.app.models.time_spent import TimeSpent
from zou.app.models.entity import EntityConceptLink
from zou.app.services import (
    comments_service,
    news_service,
    tasks_service,
)


class EntityRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(EntityRoutesTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()

    def test_get_entity_news(self):
        result = self.get(f"/data/entities/{self.asset.id}/news")
        self.assertEqual(len(result["data"]), 0)

    def test_get_entity_news_with_comment(self):
        comment = comments_service.new_comment(
            str(self.task.id),
            str(self.task_status.id),
            str(self.user["id"]),
            "Test comment",
        )
        task_dict = self.task.serialize()
        news_service.create_news_for_task_and_comment(task_dict, comment)
        result = self.get(f"/data/entities/{self.asset.id}/news")
        self.assertEqual(len(result["data"]), 1)

    def test_get_entity_preview_files(self):
        result = self.get(f"/data/entities/{self.asset.id}/preview-files")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 0)

    def test_get_entity_preview_files_with_data(self):
        self.generate_fixture_preview_file()
        result = self.get(f"/data/entities/{self.asset.id}/preview-files")
        self.assertTrue(len(result) > 0)

    def test_get_entity_time_spents(self):
        result = self.get(f"/data/entities/{self.asset.id}/time-spents")
        self.assertEqual(len(result), 0)

    def test_get_entity_time_spents_with_data(self):
        TimeSpent.create(
            person_id=self.person.id,
            task_id=self.task.id,
            date="2024-01-15",
            duration=120,
        )
        result = self.get(f"/data/entities/{self.asset.id}/time-spents")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["duration"], 120)

    def test_get_entities_linked_with_tasks(self):
        result = self.get(
            f"/data/entities/{self.asset.id}/entities-linked/with-tasks"
        )
        self.assertEqual(len(result), 0)

    def test_get_entities_linked_with_tasks_with_link(self):
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_shot_task()
        EntityConceptLink.create(
            entity_in_id=self.shot.id,
            entity_out_id=self.asset.id,
        )
        result = self.get(
            f"/data/entities/{self.asset.id}/entities-linked/with-tasks"
        )
        self.assertTrue(len(result) > 0)

    def test_delete_entities(self):
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        asset_id = str(self.asset.id)
        shot_id = str(self.shot.id)
        path = f"/actions/projects/{self.project.id}/delete-entities"
        result = self.post(path, [asset_id, shot_id], 200)
        self.assertEqual(result, [asset_id, shot_id])
        # The asset has a task: it is canceled, not removed.
        asset = self.get(f"/data/assets/{asset_id}")
        self.assertTrue(asset["canceled"])
        # The shot has no task: it is removed for real.
        self.get(f"/data/shots/{shot_id}", 404)

    def test_delete_entities_removes_canceled_asset(self):
        self.asset.update({"canceled": True})
        asset_id = str(self.asset.id)
        path = f"/actions/projects/{self.project.id}/delete-entities"
        self.post(path, [asset_id], 200)
        self.get(f"/data/assets/{asset_id}", 404)

    def test_delete_entities_skips_unsupported_entity_type(self):
        self.generate_fixture_sequence()
        sequence_id = str(self.sequence.id)
        path = f"/actions/projects/{self.project.id}/delete-entities"
        result = self.post(path, [sequence_id], 200)
        # A sequence is not a deletable type: it is skipped, not deleted.
        self.assertEqual(result, [])
        self.get(f"/data/entities/{sequence_id}")

    def test_delete_entities_skips_entity_from_other_project(self):
        asset_id = str(self.asset.id)
        other_project = self.generate_fixture_project(name="Other Project")
        path = f"/actions/projects/{other_project.id}/delete-entities"
        result = self.post(path, [asset_id], 200)
        # The asset belongs to another project: it is skipped, not deleted.
        self.assertEqual(result, [])
        self.get(f"/data/assets/{asset_id}")

    def test_delete_entities_as_artist_is_forbidden(self):
        self.generate_fixture_user_cg_artist()
        self.log_in_cg_artist()
        path = f"/actions/projects/{self.project.id}/delete-entities"
        self.post(path, [str(self.asset.id)], 403)
