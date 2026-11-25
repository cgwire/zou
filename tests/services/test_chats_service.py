import datetime
import io
import os
from unittest.mock import patch

from werkzeug.datastructures import FileStorage

from tests.base import ApiDBTestCase
from zou.app import config
from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.chat import Chat
from zou.app.models.chat_message import ChatMessage
from zou.app.services import chats_service
from zou.app.stores import file_store


class ChatsServiceTestCase(ApiDBTestCase):

    def setUp(self):
        super().setUp()

        self.generate_fixture_asset()
        self.generate_fixture_person()

    def test_get_chat_raw(self):
        chat = chats_service.get_chat_raw(self.asset.id)
        self.assertIsNotNone(chat)
        self.assertEqual(chat.object_id, self.asset.id)

        # Calling again returns the same chat (no duplicate)
        chat2 = chats_service.get_chat_raw(self.asset.id)
        self.assertEqual(chat.id, chat2.id)

    def test_join_chat(self):
        chat = chats_service.join_chat(self.asset.id, str(self.person.id))
        self.assertIsNotNone(chat)
        chat_raw = Chat.get(chat["id"])
        self.assertIn(self.person, chat_raw.participants)

    def test_joining_twice_leaves_one_participant(self):
        # join_chat appends without looking first, so what keeps the list
        # clean is the collection underneath rather than the service.
        chats_service.join_chat(self.asset.id, str(self.person.id))

        chat = chats_service.join_chat(self.asset.id, str(self.person.id))

        self.assertEqual(
            [person.id for person in Chat.get(chat["id"]).participants],
            [self.person.id],
        )

    def test_leave_chat(self):
        chats_service.join_chat(self.asset.id, str(self.person.id))
        chat = chats_service.leave_chat(self.asset.id, str(self.person.id))
        chat_raw = Chat.get(chat["id"])
        self.assertNotIn(self.person, chat_raw.participants)

    def test_leave_chat_not_participant(self):
        # Leaving a chat you never joined should not raise
        chat = chats_service.leave_chat(self.asset.id, str(self.person.id))
        self.assertIsNotNone(chat)

    def test_get_chats_for_person(self):
        """
        The chats someone has joined, in productions that are open. A chat
        they never joined and one of a closed production stay out.
        """
        chat = chats_service.join_chat(self.asset.id, str(self.person.id))
        # A chat of the same production nobody joined.
        here = self.asset
        other_asset = self.generate_fixture_asset("Rock")
        chats_service.get_chat_raw(other_asset.id)
        # And one this person joined, in a production that is closed.
        self.generate_fixture_project_closed()
        closed_asset = self.generate_fixture_asset(
            "Cloud", project_id=self.project_closed.id
        )
        chats_service.join_chat(closed_asset.id, str(self.person.id))
        self.asset = here

        chats = chats_service.get_chats_for_person(self.person.id)

        self.assertEqual([held["id"] for held in chats], [chat["id"]])

    def test_get_chats_for_person_carries_the_entity_name(self):
        chats_service.join_chat(self.asset.id, str(self.person.id))

        chats = chats_service.get_chats_for_person(self.person.id)

        self.assertEqual(chats[0]["entity_name"], "Props / Tree")
        self.assertEqual(chats[0]["project_id"], self.asset.project_id)

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

        # Oldest first, whatever order the rows come back in.
        self.assertEqual(
            [message["text"] for message in messages], ["First", "Second"]
        )

    def test_get_chat_messages_follow_their_timestamp(self):
        """
        Ordered on created_at rather than on the order the rows went in, so
        a message backdated after the fact moves ahead of the other.
        """
        chat = chats_service.get_chat_raw(self.asset.id)
        first = chats_service.create_chat_message(
            chat.id, str(self.person.id), "First"
        )
        chats_service.create_chat_message(
            chat.id, str(self.person.id), "Second"
        )
        ChatMessage.get(first["id"]).update(
            {"created_at": datetime.datetime(2030, 1, 1)}
        )

        messages = chats_service.get_chat_messages(chat.id)

        self.assertEqual(
            [message["text"] for message in messages], ["Second", "First"]
        )

    def test_get_chat_messages_for_entity(self):
        chat = chats_service.get_chat_raw(self.asset.id)
        chats_service.create_chat_message(
            chat.id, str(self.person.id), "Hello"
        )
        messages = chats_service.get_chat_messages_for_entity(self.asset.id)
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
        self.assertEqual(messages, [])

    def a_pdf(self):
        return FileStorage(
            stream=io.BytesIO(b"%PDF-1.4 fake content"),
            filename="notes.pdf",
            content_type="application/pdf",
        )

    def a_message_with(self, uploaded_file):
        chat = chats_service.get_chat_raw(self.asset.id)
        return chats_service.create_chat_message(
            chat.id,
            str(self.person.id),
            "with attachment",
            {"file": uploaded_file},
        )

    def test_a_message_stores_its_files_and_drops_the_temp_copy(self):
        message = self.a_message_with(self.a_pdf())

        (attachment,) = message["attachment_files"]
        self.assertEqual(attachment["name"], "notes.pdf")
        self.assertTrue(
            file_store.exists_file("attachments", attachment["id"])
        )
        tmp_file_path = os.path.join(config.TMP_DIR, f"{attachment['id']}.pdf")
        self.assertFalse(os.path.exists(tmp_file_path))

    def test_a_jpeg_attachment_gets_a_thumbnail(self):
        with open("tests/fixtures/thumbnails/th01.jpg", "rb") as jpg:
            uploaded_file = FileStorage(
                stream=io.BytesIO(jpg.read()),
                filename="photo.jpg",
                content_type="image/jpeg",
            )

        message = self.a_message_with(uploaded_file)

        attachment_id = message["attachment_files"][0]["id"]
        self.assertTrue(file_store.exists_picture("thumbnails", attachment_id))

    def test_a_storage_failure_leaves_no_attachment_behind(self):
        os.makedirs(config.TMP_DIR, exist_ok=True)
        tmp_files_before = set(os.listdir(config.TMP_DIR))

        with patch(
            "zou.app.services.chats_service.file_store.add_file",
            side_effect=OSError("storage down"),
        ):
            with self.assertRaises(OSError):
                self.a_message_with(self.a_pdf())

        self.assertEqual(AttachmentFile.query.count(), 0)
        self.assertEqual(set(os.listdir(config.TMP_DIR)), tmp_files_before)

    def test_deleting_a_message_removes_its_attachments(self):
        message = self.a_message_with(self.a_pdf())
        attachment_id = message["attachment_files"][0]["id"]

        chats_service.delete_chat_message(message["id"])

        self.assertEqual(AttachmentFile.query.count(), 0)
        self.assertFalse(file_store.exists_file("attachments", attachment_id))
