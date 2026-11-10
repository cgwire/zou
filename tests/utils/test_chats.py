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


    def test_a_refusal_of_slack_is_a_warning(self):
        from slack_sdk.errors import SlackApiError

        error = SlackApiError("failed", {"error": "account_inactive"})
        with mock.patch("slack_sdk.WebClient") as client_class:
            client_class.return_value.chat_postMessage.side_effect = error
            with self.assertLogs(chats.logger, "WARNING") as logs:
                chats.send_to_slack("xoxb-token", "U123", "hello")
        self.assertEqual(
            [record.levelname for record in logs.records], ["WARNING"]
        )
        self.assertIn("account_inactive", logs.output[0])


class SendToDiscordTestCase(unittest.TestCase):
    def test_the_closing_task_ends_before_the_loop_closes(self):
        import asyncio

        import discord

        closed = []

        async def start(client, token):
            async def _close():
                await asyncio.sleep(0.01)
                closed.append(True)

            # What on_ready does through client.close(): start() returns
            # while the closing task is still pending.
            client._closing_task = asyncio.create_task(_close())

        with mock.patch.object(discord.Client, "start", start):
            chats.send_to_discord("token", "john", "hello")
        self.assertEqual(closed, [True])


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

    def test_error_log_does_not_carry_the_webhook_key(self):
        import requests

        webhook = "https://mattermost.example.com/hooks/abcdef123"
        error = requests.ConnectionError(
            "HTTPSConnectionPool(host='mattermost.example.com', port=443): "
            "Max retries exceeded with url: /hooks/abcdef123"
        )
        with mock.patch("requests.post", side_effect=error), self.assertLogs(
            chats.logger, "ERROR"
        ) as logs:
            chats.send_to_mattermost(
                webhook, "john.doe", {"message": "m", "project_name": "p"}
            )
        output = "\n".join(logs.output)
        self.assertIn("ConnectionError", output)
        self.assertNotIn("abcdef123", output)

    def test_missing_webhook_or_userid_does_not_post(self):
        with mock.patch("requests.post") as post:
            chats.send_to_mattermost(None, "john.doe", {})
            chats.send_to_mattermost("https://hook", None, {})
        post.assert_not_called()
