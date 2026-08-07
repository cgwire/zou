import pytest

from tests.base import ApiDBTestCase

from zou.app.models.entity import EntityVersion
from zou.app.models.schedule_item import ScheduleItem
from zou.app.services import edits_service
from zou.app.services.exception import (
    EditNotFoundException,
    WrongIdFormatException,
    WrongParameterException,
)


class EditUtilsTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()

        self.generate_fixture_project()
        self.generate_fixture_episode()
        self.generate_fixture_edit(parent_id=self.episode.id)
        self.generate_fixture_asset()

    def the_chain_a_task_needs(self):
        self.generate_fixture_person()
        self.generate_fixture_assigner()
        self.generate_fixture_department()
        self.generate_fixture_task_status()
        self.generate_fixture_task_type()

    def test_get_edit_type(self):
        edit_type = edits_service.get_edit_type()
        self.assertEqual(edit_type["name"], "Edit")

    def test_get_edits(self):
        edit_dict = self.edit.serialize(obj_type="Edit")
        edit_dict["project_name"] = self.project.name

        self.assertDictEqual(edits_service.get_edits()[0], edit_dict)

    def test_get_edits_refuses_a_malformed_id(self):
        # The uuid guard sits in query.cast_value, before the statement is
        # even built.
        with pytest.raises(WrongParameterException):
            edits_service.get_edits({"id": "not-an-id"})

    def test_get_edits_refuses_a_value_the_driver_turns_down(self):
        # Any other column reaches the database as a cast, so the refusal
        # only comes once the query runs.
        with pytest.raises(WrongIdFormatException):
            edits_service.get_edits({"nb_entities_out": "abc"})

    def test_get_edits_and_tasks(self):
        self.the_chain_a_task_needs()
        self.generate_fixture_edit_task()
        self.generate_fixture_edit_task(name="Secondary")
        self.generate_fixture_edit("P02")

        edits = edits_service.get_edits_and_tasks()
        edits = sorted(edits, key=lambda s: s["name"])
        self.assertEqual(len(edits), 2)
        self.assertEqual(len(edits[0]["tasks"]), 2)
        self.assertEqual(edits[1]["tasks"], [])
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

    def test_get_edits_and_tasks_for_one_episode(self):
        first_episode = self.episode
        elsewhere = self.generate_fixture_episode("E02")
        self.generate_fixture_edit("Next", parent_id=elsewhere.id)

        edits = edits_service.get_edits_and_tasks(
            {"episode_id": str(first_episode.id)}
        )

        self.assertEqual([edit["name"] for edit in edits], ["Edit"])

    def test_get_edit(self):
        self.assertEqual(
            str(self.edit.id), edits_service.get_edit(self.edit.id)["id"]
        )

    def test_get_full_edit(self):
        self.the_chain_a_task_needs()
        self.generate_fixture_edit_task()

        edit = edits_service.get_full_edit(self.edit.id)
        self.assertEqual(edit["id"], str(self.edit.id))
        self.assertEqual(edit["episode_id"], str(self.episode.id))
        self.assertEqual(edit["episode_name"], self.episode.name)
        self.assertEqual(len(edit["tasks"]), 1)

    def test_is_edit(self):
        self.assertTrue(edits_service.is_edit(self.edit.serialize()))
        self.assertFalse(edits_service.is_edit(self.asset.serialize()))

    def test_create_edit(self):
        edit_name = "Editor's Cut"
        parent_id = str(self.episode.id)
        edit = edits_service.create_edit(
            self.project.id, edit_name, parent_id=parent_id
        )
        self.assertEqual(edit["name"], edit_name)
        self.assertEqual(edit["parent_id"], parent_id)

    def test_create_edit_without_episode(self):
        # The client sends an empty value rather than no value at all when
        # the edit belongs to no episode.
        edit = edits_service.create_edit(
            self.project.id, "Standalone", parent_id=""
        )

        self.assertIsNone(edit["parent_id"])

    def test_create_edit_twice_returns_the_first_one(self):
        first = edits_service.create_edit(self.project.id, "Editor's Cut")
        again = edits_service.create_edit(self.project.id, "Editor's Cut")

        self.assertEqual(first["id"], again["id"])

    def test_get_edits_for_episode(self):
        """
        The edits hanging under one episode. An edit of the next episode is
        not one of them.
        """
        here, first_episode = self.edit, self.episode
        elsewhere = self.generate_fixture_episode("E02")
        self.generate_fixture_edit("Next", parent_id=elsewhere.id)

        edits = edits_service.get_edits_for_episode(str(first_episode.id))

        self.assertEqual([edit["id"] for edit in edits], [str(here.id)])

    def test_get_edits_for_project(self):
        here = self.edit
        elsewhere = self.generate_fixture_project_standard()
        other_edit = self.generate_fixture_edit("Elsewhere")
        other_edit.update({"project_id": elsewhere.id})

        edits = edits_service.get_edits_for_project(str(self.project.id))

        self.assertEqual([edit["id"] for edit in edits], [str(here.id)])

    def test_update_edit(self):
        result = edits_service.update_edit(
            str(self.edit.id), {"description": "Recut"}
        )

        self.assertEqual(result["description"], "Recut")
        self.assertEqual(
            edits_service.get_edit(self.edit.id)["description"], "Recut"
        )

    def test_get_edit_versions(self):
        """
        Metadata changes are versioned, newest first.
        """
        self.assertEqual(edits_service.get_edit_versions(self.edit.id), [])
        for name in ["First", "Second"]:
            EntityVersion.create(entity_id=self.edit.id, name=name, data={})

        versions = edits_service.get_edit_versions(self.edit.id)

        self.assertEqual(
            [version["name"] for version in versions], ["Second", "First"]
        )

    def test_remove_edit_with_a_task_cancels_it(self):
        # An edit someone has worked on is canceled rather than deleted.
        self.the_chain_a_task_needs()
        self.generate_fixture_edit_task()

        edits_service.remove_edit(str(self.edit.id))

        self.assertTrue(edits_service.get_edit(self.edit.id)["canceled"])

    def test_remove_edit_with_a_task_can_be_forced(self):
        self.the_chain_a_task_needs()
        self.generate_fixture_edit_task()

        edits_service.remove_edit(str(self.edit.id), force=True)

        with pytest.raises(EditNotFoundException):
            edits_service.get_edit(self.edit.id)

    def test_remove_edit(self):
        edit_id = str(self.edit.id)
        self.assertIsNotNone(edit_id)
        edits_service.get_edit(edit_id)

        edits_service.remove_edit(edit_id)
        with pytest.raises(EditNotFoundException):
            edits_service.get_edit(edit_id)

    def test_remove_edit_deletes_schedule_items(self):
        self.generate_fixture_task_type()
        edit_id = str(self.edit.id)
        schedule_item = ScheduleItem.create(
            project_id=self.project.id,
            task_type_id=self.task_type.id,
            object_id=self.edit.id,
        )
        schedule_item_id = schedule_item.id

        edits_service.remove_edit(edit_id)
        self.assertIsNone(ScheduleItem.get(schedule_item_id))
