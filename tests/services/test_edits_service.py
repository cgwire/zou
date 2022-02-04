import pytest

from tests.base import ApiDBTestCase

from zou.app.services import edits_service, shots_service
from zou.app.services.exception import EditNotFoundException


class EditUtilsTestCase(ApiDBTestCase):
    def setUp(self):
        super(EditUtilsTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_episode()
        self.generate_fixture_edit(parent_id=self.episode.id)
        self.generate_fixture_asset()

    def test_get_edit_type(self):
        edit_type = edits_service.get_edit_type()
        self.assertEqual(edit_type["name"], "Edit")

    def test_get_edits(self):
        edits = edits_service.get_edits()
        self.edit_dict = self.edit.serialize(obj_type="Edit")
        self.edit_dict["project_name"] = self.project.name
        self.assertDictEqual(edits[0], self.edit_dict)

    def test_get_edits_and_tasks(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_edit_task()
        self.generate_fixture_edit_task(name="Secondary")
        self.generate_fixture_edit("P02")

        edits = edits_service.get_edits_and_tasks()
        edits = sorted(edits, key=lambda s: s["name"])
        self.assertEqual(len(edits), 2)
        self.assertEqual(len(edits[0]["tasks"]), 2)
        self.assertEqual(len(edits[1]["tasks"]), 0)
        self.assertEqual(edits[0]["episode_id"], str(self.episode.id))
        self.assertEqual(
            edits[0]["tasks"][0]["assignees"][0], str(self.person.id)
        )
        self.assertEqual(
            edits[0]["tasks"][0]["task_status_id"],
            str(self.edit_task.task_status_id),
        )
        self.assertEqual(
            edits[0]["tasks"][0]["task_type_id"],
            str(self.edit_task.task_type_id),
        )

    def test_get_edit(self):
        self.assertEqual(
            str(self.edit.id), edits_service.get_edit(self.edit.id)["id"]
        )

    def test_get_full_edit(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()
        self.generate_fixture_edit_task()

        edit = edits_service.get_full_edit(self.edit.id)
        self.assertEqual(edit["id"], str(self.edit.id))
        self.assertEqual(edit["episode_id"], str(self.episode.id))
        self.assertEqual(edit["episode_name"], self.episode.name)
        self.assertEqual(len(edit["tasks"]), 1)

    def test_get_episode(self):
        self.assertEqual(
            str(self.episode.id),
            shots_service.get_episode(self.episode.id)["id"],
        )

    def test_is_edit(self):
        self.assertTrue(edits_service.is_edit(self.edit.serialize()))
        self.assertFalse(edits_service.is_edit(self.asset.serialize()))

    def test_get_episode_from_edit(self):
        episode = shots_service.get_episode(self.edit.parent_id)
        self.assertEqual(episode["name"], "E01")

    def test_create_edit(self):
        edit_name = "Editor's Cut"
        parent_id = str(self.episode.id)
        edit = edits_service.create_edit(
            self.project.id, edit_name, parent_id=parent_id
        )
        self.assertEqual(edit["name"], edit_name)
        self.assertEqual(edit["parent_id"], parent_id)

    def test_remove_edit(self):
        edit_id = str(self.edit.id)
        self.assertIsNotNone(edit_id)
        edits_service.get_edit(edit_id)

        edits_service.remove_edit(edit_id)
        with pytest.raises(EditNotFoundException):
            edits_service.get_edit(edit_id)
