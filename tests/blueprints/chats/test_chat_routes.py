import os

from tests.base import ApiDBTestCase

from zou.app.services import chats_service
from zou.app.stores import file_store
from zou.app.utils import thumbnail


class EventsRoutesTestCase(ApiDBTestCase):
    def setUp(self):
        super(EventsRoutesTestCase, self).setUp(expire_on_commit=False)

        self.generate_fixture_project_status()
        self.generate_fixture_project()
        self.generate_fixture_asset_type()
        self.generate_fixture_asset()
        self.generate_fixture_person()

    def generate_fixture_chat_message(self):
        chats_service.join_chat(self.asset.id, self.person.id)
        chat = chats_service.get_chat_raw(self.asset.id)
        return chats_service.create_chat_message(
            chat.id, self.user["id"], "Hello, World!"
        )

    def test_join_chat(self):
        self.post(f"/actions/user/chats/{self.asset.id}/join", {}, 200)
        chat = self.get(f"/data/entities/{self.asset.id}/chat")
        self.assertIn(str(self.user["id"]), chat["participants"])

    def test_leave_chat(self):
        self.post(f"/actions/user/chats/{self.asset.id}/join", {}, 200)
        self.delete(f"/actions/user/chats/{self.asset.id}/join")
        chat = self.get(f"/data/entities/{self.asset.id}/chat")
        self.assertNotIn(str(self.user["id"]), chat["participants"])

    def test_get_chats(self):
        self.generate_fixture_chat_message()
        self.post(f"/actions/user/chats/{self.asset.id}/join", {}, 200)
        chats = self.get(f"/data/user/chats")
        self.assertEqual(len(chats), 1)

    def test_get_chat(self):
        self.generate_fixture_chat_message()
        chat = self.get(f"/data/entities/{self.asset.id}/chat")
        db_chat = chats_service.get_chat(self.asset.id)
        self.assertEqual(chat["id"], db_chat["id"])

    def test_get_chat_messages(self):
        self.generate_fixture_chat_message()
        self.get(f"/data/entities/{self.asset.id}/chat")
        messages = self.get(f"/data/entities/{self.asset.id}/chat/messages")
        self.assertEqual(len(messages), 1)

    def test_post_chat_message(self):
        self.post(f"/actions/user/chats/{self.asset.id}/join", {}, 200)
        data = {"message": "Hello, World!"}
        self.post(f"/data/entities/{self.asset.id}/chat/messages", data)
        messages = self.get(f"/data/entities/{self.asset.id}/chat/messages")
        self.assertEqual(len(messages), 1)

    def test_get_chat_message(self):
        chat_message = self.generate_fixture_chat_message()
        message = self.get(
            f"/data/entities/{self.asset.id}/chat/messages/{chat_message['id']}"
        )
        self.assertEqual(message["id"], chat_message["id"])

    def test_post_chat_message_with_attachment(self):
        self.post(f"/actions/user/chats/{self.asset.id}/join", {}, 200)
        file_path_fixture = self.get_fixture_file_path(
            os.path.join("thumbnails", "th01.png"),
        )
        message = self.upload_file(
            f"/data/entities/{self.asset.id}/chat/messages",
            file_path_fixture,
            extra_fields={"message": "Hello, World!"},
        )
        chat_message = chats_service.get_chat_message(message["id"])
        self.assertEqual(message["text"], chat_message["text"])
        attachment_id = chat_message["attachment_files"][0]["id"]
        self.assertTrue(file_store.exists_file("attachments", attachment_id))
        self.assertTrue(file_store.exists_picture("thumbnails", attachment_id))
        size = thumbnail.get_dimensions(
            file_store.get_local_picture_path("thumbnails", attachment_id)
        )
        self.assertEqual(size, (150, 150))

    def test_delete_chat_message(self):
        chat_message = self.generate_fixture_chat_message()
        self.delete(
            f"/data/entities/{self.asset.id}/chat/messages/{chat_message['id']}"
        )
        self.assertRaises(
            Exception,
            chats_service.get_chat_message,
            chat_message["id"],
        )
