from .base import BaseEditTestCase
from zou.app.services import edits_service
from zou.app.utils import events


class EditsTestCase(BaseEditTestCase):
    def handle_event(self, data):
        self.is_event_fired = True

    def test_get_edits(self):
        edits = self.get("data/edits/all")

        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["name"], self.edit_dict["name"])

    def test_get_edit(self):
        edit = self.get("data/edits/%s" % self.edit.id)

        self.assertEqual(edit["id"], str(self.edit.id))
        self.assertEqual(edit["type"], "Edit")
        self.assertEqual(edit["name"], "Edit")
        self.assertEqual(edit["project_name"], self.project_name)
        self.assertEqual(edit["parent_id"], self.episode_id)
        self.assertEqual(edit["episode_id"], self.episode_id)
        self.assertEqual(edit["episode_name"], self.episode_name)
        self.assertEqual(len(edit["tasks"]), 2)

    def test_get_edit_by_name(self):
        edits = self.get("data/edits/all?name=%s" % self.edit.name.lower())

        self.assertEqual(edits[0]["id"], str(self.edit.id))
        self.assertEqual(edits[0]["type"], "Edit")
        self.assertEqual(edits[0]["name"], "Edit")
        self.assertEqual(edits[0]["parent_id"], self.episode_id)

    def test_get_project_edits(self):
        edits = self.get("data/projects/%s/edits" % self.project.id)
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["type"], "Edit")
        self.assertEqual(edits[0]["name"], "Edit")
        self.assertEqual(edits[0]["parent_id"], self.episode_id)

    def test_create_edit(self):
        events.register("edit:new", "handle_event", self)
        new_edit_data = {
            "name": "Director's Cut",
            "description": "Test Edit description",
            "data": {"extra": "test extra"},
        }
        path = "data/projects/%s/edits" % (self.project.id,)

        edit = self.post(path, new_edit_data)

        edits = edits_service.get_edits()
        self.assertIsNotNone(edit.get("id", None))
        self.assertEqual(len(edits), 2)
        self.assertEqual(
            {edit["name"] for edit in edits},
            {self.edit_dict["name"], new_edit_data["name"]},
        )
        self.assertEqual(edit["name"], new_edit_data["name"])
        self.assertIsNone(edit["parent_id"])
        self.assertEqual(edit["type"], "Edit")
        self.assertEqual(edit["description"], new_edit_data["description"])
        self.assertDictEqual(edit["data"], new_edit_data["data"])

    def test_remove_edit(self):
        edit = self.generate_fixture_edit()
        edits = edits_service.get_edits()
        self.assertEqual(len(edits), 2)
        path = "data/edits/%s" % edit.id

        self.delete(path)

        edits = edits_service.get_edits()
        self.assertEqual(len(edits), 1)
        self.get(path, 404)

    def test_remove_edit_force(self):
        edit = self.generate_fixture_edit()
        self.assertEqual(len(edits_service.get_edits()), 2)
        path = "data/edits/%s?force=true" % edit.id

        self.delete(path)

        self.assertEqual(len(edits_service.get_edits()), 1)
        self.get(path, 404)

    def test_remove_edit_with_tasks(self):
        edits = edits_service.get_edits()
        self.assertEqual(len(edits), 1)
        path = "data/edits/%s" % self.edit_dict["id"]

        self.delete(path)

        edits = edits_service.get_edits()
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0]["canceled"], True)
        self.get(path, 200)

    def test_remove_edit_with_tasks_force(self):
        edits = edits_service.get_edits()
        self.assertEqual(len(edits), 1)
        path = "data/edits/%s?force=true" % self.edit_dict["id"]

        self.delete(path)

        edits = edits_service.get_edits()
        self.assertEqual(len(edits), 0)
        self.get(path, 404)
