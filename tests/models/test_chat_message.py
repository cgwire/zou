from tests.base import ApiDBTestCase
from zou.app.models.chat import Chat
from zou.app.models.chat_message import ChatMessage
from zou.app.utils import fields


class ChatMessageTestCase(ApiDBTestCase):
    def setUp(self):
        super(ChatMessageTestCase, self).setUp()
        self.person_id = str(self.user["id"])
        self.chat = Chat.create(
            object_id=fields.gen_uuid(),
            object_type="entity",
        )
        self.chat_id = str(self.chat.id)
        self.generate_data(
            ChatMessage, 3, chat_id=self.chat_id, person_id=self.person_id
        )

    def test_get_chat_messages(self):
        chat_messages = self.get("data/chat-messages")
        self.assertEqual(len(chat_messages), 3)

    def test_get_chat_message(self):
        chat_message = self.get_first("data/chat-messages")
        chat_message_again = self.get(
            "data/chat-messages/%s" % chat_message["id"]
        )
        self.assertEqual(chat_message["id"], chat_message_again["id"])
        self.get_404("data/chat-messages/%s" % fields.gen_uuid())

    def test_create_chat_message(self):
        data = {
            "chat_id": self.chat_id,
            "person_id": self.person_id,
            "text": "Hello world",
        }
        chat_message = self.post("data/chat-messages", data)
        self.assertIsNotNone(chat_message["id"])
        chat_messages = self.get("data/chat-messages")
        self.assertEqual(len(chat_messages), 4)

    def test_update_chat_message(self):
        chat_message = self.get_first("data/chat-messages")
        data = {"text": "Updated message"}
        self.put(
            "data/chat-messages/%s" % chat_message["id"], data
        )
        chat_message_again = self.get(
            "data/chat-messages/%s" % chat_message["id"]
        )
        self.assertEqual(data["text"], chat_message_again["text"])
        self.put_404(
            "data/chat-messages/%s" % fields.gen_uuid(), data
        )

    def test_delete_chat_message(self):
        chat_messages = self.get("data/chat-messages")
        self.assertEqual(len(chat_messages), 3)
        chat_message = chat_messages[0]
        self.delete(
            "data/chat-messages/%s" % chat_message["id"]
        )
        chat_messages = self.get("data/chat-messages")
        self.assertEqual(len(chat_messages), 2)
        self.delete_404(
            "data/chat-messages/%s" % fields.gen_uuid()
        )
