from tests.base import ApiDBTestCase

from zou.app.models.chat import Chat
from zou.app.models.chat_message import ChatMessage

from zou.app.services import chats_service


class ChatsServiceTestCase(ApiDBTestCase):

    def setUp(self):
        super(ChatsServiceTestCase, self).setUp()

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_person()

    def test_get_chat_raw(self):
        chat = chats_service.get_chat_raw(self.asset.id)
        self.assertIsNotNone(chat)
        self.assertEqual(chat.object_id, self.asset.id)

        # Calling again returns the same chat (no duplicate)
        chat2 = chats_service.get_chat_raw(self.asset.id)
        self.assertEqual(chat.id, chat2.id)

    def test_get_chat(self):
        chat = chats_service.get_chat(self.asset.id)
        self.assertIsNotNone(chat["id"])
        self.assertEqual(chat["object_id"], str(self.asset.id))

    def test_get_chat_by_id(self):
        chat = chats_service.get_chat_raw(self.asset.id)
        result = chats_service.get_chat_by_id(chat.id)
        self.assertEqual(result["id"], str(chat.id))

    def test_join_chat(self):
        chat = chats_service.join_chat(
            self.asset.id, str(self.person.id)
        )
        self.assertIsNotNone(chat)
        chat_raw = Chat.get(chat["id"])
        self.assertIn(self.person, chat_raw.participants)

    def test_leave_chat(self):
        chats_service.join_chat(self.asset.id, str(self.person.id))
        chat = chats_service.leave_chat(
            self.asset.id, str(self.person.id)
        )
        chat_raw = Chat.get(chat["id"])
        self.assertNotIn(self.person, chat_raw.participants)

    def test_leave_chat_not_participant(self):
        # Leaving a chat you never joined should not raise
        chat = chats_service.leave_chat(
            self.asset.id, str(self.person.id)
        )
        self.assertIsNotNone(chat)

    def test_create_chat_message(self):
        chat = chats_service.get_chat_raw(self.asset.id)
        message = chats_service.create_chat_message(
            chat.id, str(self.person.id), "Hello world"
        )
        self.assertEqual(message["text"], "Hello world")
        self.assertEqual(message["chat_id"], str(chat.id))
        self.assertEqual(message["person_id"], str(self.person.id))

    def test_get_chat_messages(self):
        chat = chats_service.get_chat_raw(self.asset.id)
        chats_service.create_chat_message(
            chat.id, str(self.person.id), "First"
        )
        chats_service.create_chat_message(
            chat.id, str(self.person.id), "Second"
        )
        messages = chats_service.get_chat_messages(chat.id)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["text"], "First")
        self.assertEqual(messages[1]["text"], "Second")

    def test_get_chat_messages_for_entity(self):
        chat = chats_service.get_chat_raw(self.asset.id)
        chats_service.create_chat_message(
            chat.id, str(self.person.id), "Hello"
        )
        messages = chats_service.get_chat_messages_for_entity(
            self.asset.id
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["text"], "Hello")

    def test_delete_chat_message(self):
        chat = chats_service.get_chat_raw(self.asset.id)
        message = chats_service.create_chat_message(
            chat.id, str(self.person.id), "To delete"
        )
        result = chats_service.delete_chat_message(message["id"])
        self.assertEqual(result["id"], message["id"])
        messages = chats_service.get_chat_messages(chat.id)
        self.assertEqual(len(messages), 0)

    def test_get_chat_message_raw(self):
        chat = chats_service.get_chat_raw(self.asset.id)
        message = chats_service.create_chat_message(
            chat.id, str(self.person.id), "Test"
        )
        raw = chats_service.get_chat_message_raw(message["id"])
        self.assertEqual(str(raw.id), message["id"])
        self.assertEqual(raw.text, "Test")
