import unittest

from unittest import mock

from zou.app.utils import chats


class SendToSlackTestCase(unittest.TestCase):
    def test_posts_message_to_user_channel(self):
        with mock.patch("slack_sdk.WebClient") as client_class:
            chats.send_to_slack("xoxb-token", "U123", "hello")
        client_class.assert_called_once_with(token="xoxb-token")
        client = client_class.return_value
        client.chat_postMessage.assert_called_once()
        kwargs = client.chat_postMessage.call_args.kwargs
        self.assertEqual(kwargs["channel"], "@U123")
        self.assertEqual(kwargs["blocks"][0]["text"]["text"], "hello")

    def test_missing_token_or_userid_does_not_post(self):
        with mock.patch("slack_sdk.WebClient") as client_class:
            chats.send_to_slack(None, "U123", "hello")
            chats.send_to_slack("xoxb-token", None, "hello")
        client_class.assert_not_called()


class SendToMattermostTestCase(unittest.TestCase):
    def test_posts_payload_on_webhook_url(self):
        webhook = "https://mattermost.example.com/hooks/abcdef123"
        with mock.patch("requests.post") as post:
            chats.send_to_mattermost(
                webhook,
                "john.doe",
                {"message": "New comment", "project_name": "Caminandes"},
            )
        post.assert_called_once()
        args, kwargs = post.call_args
        self.assertEqual(args[0], webhook)
        self.assertEqual(kwargs["json"]["text"], "New comment")
        self.assertEqual(kwargs["json"]["channel"], "@john.doe")
        self.assertEqual(kwargs["json"]["username"], "Kitsu - Caminandes")
        self.assertEqual(kwargs["timeout"], 30)

    def test_missing_webhook_or_userid_does_not_post(self):
        with mock.patch("requests.post") as post:
            chats.send_to_mattermost(None, "john.doe", {})
            chats.send_to_mattermost("https://hook", None, {})
        post.assert_not_called()
