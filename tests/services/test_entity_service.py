import pytest

from tests.base import ApiDBTestCase

from zou.app.services import entities_service, assets_service

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


class EntityServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(EntityServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_sequence()
        self.generate_fixture_shot()
        self.generate_fixture_department()
        self.generate_fixture_task_type()
        self.generate_fixture_task_status()
        self.generate_fixture_task_status_wip()
        self.generate_fixture_task_status_to_review()
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_task()
        self.generate_fixture_shot_task()
        self.generate_fixture_file_status()
        self.generate_fixture_software()
        self.generate_fixture_working_file()
        self.generate_fixture_output_type()
        self.generate_fixture_output_file()
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

    def test_get_entity_tasks_shot(self):
        """Test get_entity_tasks for shot entity"""
        # Generate fixture tasks for the shot
        self.generate_fixture_shot_task()
        
        # Get shot entity
        shot_entity = entities_service.get_entity(str(self.shot.id))
        
        # Get tasks for the shot entity
        tasks = entities_service.get_entity_tasks(shot_entity)
        
        # Verify tasks were returned
        self.assertIsInstance(tasks, list)
        self.assertGreater(len(tasks), 0)
        
        # Verify task structure
        task = tasks[0]
        self.assertIn("id", task)
        self.assertIn("task_type_name", task)
        self.assertIn("entity_id", task)
        self.assertEqual(task["entity_id"], str(self.shot.id))

    def test_get_entity_tasks_asset(self):
        """Test get_entity_tasks for asset entity"""
        # Generate fixture task for the asset
        self.generate_fixture_asset_task()
        
        # Get asset entity
        asset_entity = entities_service.get_entity(str(self.asset.id))
        
        # Get tasks for the asset entity
        tasks = entities_service.get_entity_tasks(asset_entity)
        
        # Verify tasks were returned
        self.assertIsInstance(tasks, list)
        self.assertGreater(len(tasks), 0)
        
        # Verify task structure
        task = tasks[0]
        self.assertIn("id", task)
        self.assertIn("task_type_name", task)
        self.assertIn("entity_id", task)
        self.assertEqual(task["entity_id"], str(self.asset.id))

    def test_get_entity_tasks_no_tasks(self):
        """Test get_entity_tasks when entity has no tasks"""
        # Get shot entity without creating any tasks
        shot_entity = entities_service.get_entity(str(self.shot.id))
        
        # Get tasks for the shot entity (should be empty)
        tasks = entities_service.get_entity_tasks(shot_entity)
        
        # Verify empty list is returned
        self.assertIsInstance(tasks, list)
        self.assertEqual(len(tasks), 0)
