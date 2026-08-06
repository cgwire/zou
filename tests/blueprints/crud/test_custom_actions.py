# -*- coding: UTF-8 -*-
from tests.base import ApiDBTestCase
from zou.app.models.custom_action import CustomAction

from zou.app.utils import fields


class CustomActionTestCase(ApiDBTestCase):
    def setUp(self):
        super().setUp()
        self.generate_data(CustomAction, 3)

    def test_get_custom_actions(self):
        custom_actions = self.get("data/custom-actions")
        self.assertEqual(len(custom_actions), 3)
        self.assertEqual(custom_actions[0]["type"], "CustomAction")

    def test_get_custom_action(self):
        custom_action = self.get_first("data/custom-actions")
        custom_action_again = self.get(
            f"data/custom-actions/{custom_action['id']}"
        )
        self.assertEqual(custom_action, custom_action_again)
        self.get_404(f"data/custom-actions/{fields.gen_uuid()}")

    def test_create_custom_action(self):
        data = {
            "name": "run_render",
            "url": "http://198.168.1.123",
        }
        self.custom_action = self.post("data/custom-actions", data)
        self.assertIsNotNone(self.custom_action["id"])

        custom_actions = self.get("data/custom-actions")
        self.assertEqual(len(custom_actions), 4)

    def test_create_custom_action_with_no_data(self):
        data = {}
        self.custom_action = self.post("data/custom-actions", data, 400)

    def test_create_custom_action_with_wrong_data(self):
        data = {"wrong": "data"}
        self.custom_action = self.post("data/custom-actions", data, 400)

    def test_update_custom_action(self):
        custom_action = self.get_first("data/custom-actions")
        data = {
            "name": "run_render_2",
        }
        self.put(f"data/custom-actions/{custom_action['id']}", data)
        custom_action_again = self.get(
            f"data/custom-actions/{custom_action['id']}"
        )
        self.assertEqual(data["name"], custom_action_again["name"])
        self.put_404(f"data/custom-actions/{fields.gen_uuid()}", data)

    def test_delete_custom_action(self):
        custom_actions = self.get("data/custom-actions")
        self.assertEqual(len(custom_actions), 3)

        custom_action = custom_actions[1]
        self.delete(f"data/custom-actions/{custom_action['id']}")
        custom_actions = self.get("data/custom-actions")
        self.assertEqual(len(custom_actions), 2)

        self.delete_404(f"data/custom-actions/{fields.gen_uuid()}")
        custom_actions = self.get("data/custom-actions")
        self.assertEqual(len(custom_actions), 2)

    def test_context_sees_a_new_custom_action_at_once(self):
        """
        The custom action list is memoized for two minutes and reaches the
        clients through the user context. Every write route drops that cache,
        otherwise a studio adding an action would not see it for two minutes.
        """
        before = self.get("/data/user/context")["custom_actions"]
        self.assertEqual(len(before), 3)

        created = self.post(
            "data/custom-actions",
            {"name": "run_render", "url": "http://198.168.1.123"},
        )
        after = self.get("/data/user/context")["custom_actions"]
        self.assertEqual(len(after), 4)
        self.assertIn(created["id"], [action["id"] for action in after])

        self.delete(f"data/custom-actions/{created['id']}")
        names = self.get("/data/user/context")["custom_actions"]
        self.assertEqual(len(names), 3)
