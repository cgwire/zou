from tests.base import ApiDBTestCase
from zou.app.models.chat import Chat
from zou.app.services import chats_service


class ChatsServiceTestCase(ApiDBTestCase):
    def setUp(self):
        super(ChatsServiceTestCase, self).setUp()
        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_person()

    def generate_fixture_chat_message(self):
        chats_service.join_chat(self.asset.id, self.person.id)
        chat = chats_service.get_chat_raw(self.asset.id)
        return chats_service.create_chat_message(
            chat.id, self.person.id, "Hello, World!"
        )

    def test_get_chat_raw(self):
        chats_service.join_chat(
            self.asset.id,
            self.person.id,
        )
        chat = chats_service.get_chat_raw(self.asset.id)
        self.assertIsInstance(chat, Chat)
        self.assertEqual(chat.object_id, self.asset.id)

    def test_get_chat(self):
        chat = chats_service.get_chat(self.asset.id)
        self.assertIsInstance(chat, dict)
        self.assertEqual(chat["object_id"], str(self.asset.id))

    def test_create_chat_message(self):
        chats_service.join_chat(self.asset.id, self.person.id)
        chat = chats_service.get_chat_raw(self.asset.id)
        chat_message = chats_service.create_chat_message(
            chat.id, self.person.id, "Hello, World!"
        )
        self.assertEqual(chat_message["chat_id"], str(chat.id))

    def test_get_chat_message_raw(self):
        chat_message = self.generate_fixture_chat_message()
        new_chat_message = chats_service.get_chat_message_raw(
            chat_message["id"]
        )
        self.assertEqual(str(new_chat_message.id), chat_message["id"])

    def test_get_chat_message(self):
        chat_message = self.generate_fixture_chat_message()
        new_chat_message = chats_service.get_chat_message(chat_message["id"])
        self.assertEqual(new_chat_message["id"], chat_message["id"])

    def test_get_chat_messages(self):
        self.generate_fixture_chat_message()
        self.generate_fixture_chat_message()
        chat = chats_service.get_chat_raw(self.asset.id)
        chat_messages = chats_service.get_chat_messages(chat.id)
        self.assertEqual(len(chat_messages), 2)

    def test_get_chat_messages_for_entity(self):
        self.generate_fixture_chat_message()
        self.generate_fixture_chat_message()
        chat_messages = chats_service.get_chat_messages_for_entity(
            self.asset.id
        )
        self.assertEqual(len(chat_messages), 2)

    def test_join_chat(self):
        chats_service.join_chat(self.asset.id, self.person.id)
        chat = chats_service.get_chat(self.asset.id)
        self.assertEqual(chat["participants"][0], str(self.person.id))

    def test_leave_chat(self):
        chats_service.join_chat(self.asset.id, self.person.id)
        chats_service.leave_chat(self.asset.id, self.person.id)
        chat = chats_service.get_chat(self.asset.id)
        self.assertEqual(len(chat["participants"]), 0)

    def test_delete_chat_message(self):
        chat_message = self.generate_fixture_chat_message()
        chats_service.delete_chat_message(chat_message["id"])
        self.assertRaises(
            Exception, chats_service.get_chat_message, chat_message["id"]
        )

    def test_get_chats_for_person(self):
        chat = chats_service.join_chat(self.asset.id, self.person.id)
        chats = chats_service.get_chats_for_person(self.person.id)
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]["id"], chat["id"])
