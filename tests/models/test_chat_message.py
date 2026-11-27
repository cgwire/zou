import unittest

from zou.app.models.chat_message import ChatMessage
from zou.app.utils import fields


class ChatMessageTestCase(unittest.TestCase):
    def test_repr_names_the_chat(self):
        chat_id = fields.gen_uuid()
        message = ChatMessage(chat_id=chat_id)
        self.assertEqual(repr(message), f"<Message of {chat_id}>")
