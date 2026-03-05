from tests.base import ApiDBTestCase

from zou.app.models.entity_link import EntityLink
from zou.app.models.time_spent import TimeSpent
from zou.app.services import comments_service, tasks_service


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
        self.generate_fixture_task_status_wip()
        comments_service.new_comment(
            str(self.task.id),
            str(self.task_status.id),
            str(self.user["id"]),
            "Test comment",
        )
        result = self.get(f"/data/entities/{self.asset.id}/news")
        self.assertEqual(len(result["data"]), 1)

    def test_get_entity_preview_files(self):
        result = self.get(
            f"/data/entities/{self.asset.id}/preview-files"
        )
        self.assertIsInstance(result, dict)

    def test_get_entity_preview_files_with_data(self):
        self.generate_fixture_preview_file()
        result = self.get(
            f"/data/entities/{self.asset.id}/preview-files"
        )
        self.assertTrue(len(result) > 0)

    def test_get_entity_time_spents(self):
        result = self.get(
            f"/data/entities/{self.asset.id}/time-spents"
        )
        self.assertEqual(len(result), 0)

    def test_get_entity_time_spents_with_data(self):
        TimeSpent.create(
            person_id=self.person.id,
            task_id=self.task.id,
            date="2024-01-15",
            duration=120,
        )
        result = self.get(
            f"/data/entities/{self.asset.id}/time-spents"
        )
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
        EntityLink.create(
            entity_in_id=self.asset.id,
            entity_out_id=self.shot.id,
            nb_occurences=1,
        )
        result = self.get(
            f"/data/entities/{self.asset.id}/entities-linked/with-tasks"
        )
        self.assertTrue(len(result) > 0)
