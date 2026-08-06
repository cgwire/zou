import pytest

from tests.base import ApiDBTestCase

from zou.app.services import assets_service, deletion_service, entities_service

from zou.app.services.exception import (
    PreviewFileNotFoundException,
    EntityNotFoundException,
)


class ToReviewHandler(object):
    def __init__(self, open_status_id, to_review_status_id):
        self.is_event_fired = False
        self.open_status_id = open_status_id
        self.to_review_status_id = to_review_status_id

    def handle_event(self, data):
        self.is_event_fired = True
        self.data = data


class EntitiesServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        self.generate_fixture_working_file()
        self.generate_fixture_preview_file()

    def test_get_entity_type(self):
        entity_type = entities_service.get_entity_type(self.asset_type.id)
        self.assertEqual(entity_type, self.asset_type.serialize())

    def test_get_entity_type_by_name(self):
        entity_type = entities_service.get_entity_type_by_name(
            self.asset_type.name
        )
        self.assertEqual(entity_type, self.asset_type.serialize())

    def test_get_entity_raw(self):
        entity = entities_service.get_entity_raw(self.asset.id)
        self.assertEqual(entity.id, self.asset.id)

    def test_get_entity(self):
        entity = entities_service.get_entity(self.asset.id)
        self.assertEqual(entity, self.asset.serialize())

    def test_update_entity_preview(self):
        entities_service.update_entity_preview(
            str(self.asset.id), str(self.preview_file.id)
        )
        asset = assets_service.get_asset(self.asset.id)
        self.assertEqual(asset["preview_file_id"], str(self.preview_file.id))

        with pytest.raises(EntityNotFoundException):
            entities_service.update_entity_preview(
                str(self.preview_file.id), str(self.preview_file.id)
            )

        with pytest.raises(PreviewFileNotFoundException):
            entities_service.update_entity_preview(
                str(self.asset.id), str(self.asset.id)
            )

        self.asset.preview_file_id = None

    def test_get_entities_and_tasks(self):
        self.generate_fixture_sequence_task()
        sequences = entities_service.get_entities_and_tasks()
        self.assertEqual(len(sequences), 3)
        self.assertEqual(len(sequences[0]["tasks"]), 1)

    def assert_the_tasks_of_the_entity_are_listed(self, entity_id):
        """
        The listing carries every task of that entity and nothing else,
        whatever kind of entity it is.
        """
        entity = entities_service.get_entity(str(entity_id))

        tasks = entities_service.get_entity_tasks(entity)

        self.assertGreater(len(tasks), 0)
        for task in tasks:
            self.assertEqual(task["entity_id"], str(entity_id))
            self.assertIn("task_type_name", task)
            self.assertIn("id", task)

    def test_get_entity_tasks_shot(self):
        self.assert_the_tasks_of_the_entity_are_listed(self.shot.id)

    def test_get_entity_tasks_asset(self):
        self.assert_the_tasks_of_the_entity_are_listed(self.asset.id)

    def test_get_entity_tasks_no_tasks(self):
        """
        Test get_entity_tasks when entity has no tasks
        """
        shot_entity = entities_service.get_entity(str(self.shot.id))
        deletion_service.remove_task(str(self.shot_task.id), force=True)
        tasks = entities_service.get_entity_tasks(shot_entity)
        self.assertIsInstance(tasks, list)
        self.assertEqual(tasks, [])

    def test_get_entities_for_project(self):
        """
        The entities of one production, of one type, ordered by name.
        """
        self.generate_fixture_project_standard()
        # Named to sort first while created last, and one asset of the same
        # name in another production, which must not show up.
        self.generate_fixture_asset("Anvil")
        self.generate_fixture_asset(
            "Anvil", project_id=self.project_standard.id
        )

        assets = entities_service.get_entities_for_project(
            str(self.project.id), str(self.asset_type.id), obj_type="Asset"
        )

        self.assertEqual(
            [asset["name"] for asset in assets], ["Anvil", "Tree"]
        )
        self.assertEqual(assets[0]["type"], "Asset")
