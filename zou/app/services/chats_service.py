import random
import string

from flask import current_app
from sqlalchemy.exc import IntegrityError

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.chat import Chat
from zou.app.models.chat_message import ChatMessage
from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus

from zou.app.utils import cache, events, fs, thumbnail

from zou.app.stores import file_store

from zou.app.services import names_service, persons_service


def clear_chat_message_cache(chat_message_id):
    cache.cache.delete_memoized(get_chat_message, chat_message_id)


def get_chat_raw(entity_id):
    """
    Return chat corresponding to given entity ID.
    """
    chat = Chat.get_by(object_id=entity_id)
    if chat is None:
        chat = Chat.create(object_id=entity_id)
    return chat


def get_chat(entity_id):
    """
    Return chat corresponding to given entity ID.
    """
    chat = get_chat_raw(entity_id)
    return chat.serialize(relations=True)


def get_chat_by_id(chat_id):
    """
    Return chat corresponding to given entity ID.
    """
    chat = Chat.get(chat_id)
    return chat.serialize(relations=True)


def get_chat_message_raw(chat_message_id):
    """
    Return chat message corresponding to given chat message ID.
    """
    return ChatMessage.get(chat_message_id)


@cache.memoize_function(1200)
def get_chat_message(chat_message_id):
    """
    Return chat message corresponding to given chat message ID.
    """
    message = get_chat_message_raw(chat_message_id)
    serialized_message = message.serialize()
    serialized_message["attachment_files"] = []
    for attachment_file in message.attachment_files:
        serialized_message["attachment_files"].append(
            {
                "id": attachment_file.id,
                "name": attachment_file.name,
                "extension": attachment_file.extension,
            }
        )
    return serialized_message


def join_chat(entity_id, person_id):
    """
    Join chat for given entity ID.
    """
    chat = get_chat_raw(entity_id)
    person = persons_service.get_person_raw(person_id)
    chat.participants.append(person)
    chat.save()
    events.emit(
        "chat:joined",
        data={"chat_id": chat.id, "person_id": person.id},
        persist=False,
    )
    return chat.serialize()


def leave_chat(entity_id, person_id):
    """
    Leave chat for given entity ID.
    """
    chat = get_chat_raw(entity_id)
    person = persons_service.get_person_raw(person_id)
    chat.participants.remove(person)
    chat.save()
    events.emit(
        "chat:left",
        data={"chat_id": chat.id, "person_id": person.id},
        persist=False,
    )
    return chat.serialize()


def get_chat_messages(chat_id):
    """
    Return chat messages for given chat ID.
    """
    result = []
    messages = (
        ChatMessage.query.filter(ChatMessage.chat_id == chat_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    for message in messages:
        serialized_message = message.serialize()
        serialized_message["attachment_files"] = []
        for attachment_file in message.attachment_files:
            serialized_message["attachment_files"].append(
                {
                    "id": attachment_file.id,
                    "name": attachment_file.name,
                    "extension": attachment_file.extension,
                }
            )
        result.append(serialized_message)
    return result


def get_chat_messages_for_entity(entity_id):
    """
    Return chat messages for given entity ID.
    """
    chat = get_chat_raw(entity_id)
    return get_chat_messages(chat.id)


def create_chat_message(chat_id, person_id, message, files=None):
    """
    Create a new chat message.
    """
    chat = Chat.get(chat_id)
    message = ChatMessage.create(
        chat_id=chat_id, person_id=person_id, text=message
    )
    chat.update({"last_message": message.created_at})
    serialized_message = message.serialize()
    if files:
        _add_attachments_to_message(serialized_message, files)
    events.emit(
        "chat:new-message",
        data={
            "chat_id": chat_id,
            "chat_message_id": serialized_message["id"],
            "last_message": serialized_message["created_at"],
        },
        persist=False,
    )
    return serialized_message


def delete_chat_message(chat_message_id):
    """
    Delete chat message.
    """
    message = get_chat_message_raw(chat_message_id)

    for attachment in message.attachment_files:
        attachment_file_id = str(attachment.id)
        file_store.remove_file("attachments", attachment_file_id)
        file_store.remove_picture("thumbnails", attachment_file_id)
        attachment.delete()

    message.delete()
    events.emit(
        "chat:deleted-message",
        data={
            "chat_id": str(message.chat_id),
            "chat_message_id": chat_message_id,
        },
        persist=False,
    )
    clear_chat_message_cache(chat_message_id)
    return message.serialize()


def build_participant_filter(person_id):
    """
    Query filter for returning chats for current user.
    """
    person = persons_service.get_person_raw(person_id)
    return Chat.participants.contains(person)


def get_chats_for_person(person_id):
    """
    Return chats for current user.
    """
    chats = (
        Chat.query.join(Entity, Chat.object_id == Entity.id)
        .join(Project, Entity.project_id == Project.id)
        .join(ProjectStatus, ProjectStatus.id == Project.project_status_id)
        .add_columns(Entity.project_id, Entity.preview_file_id)
        .filter(build_participant_filter(person_id))
        .filter(ProjectStatus.name == "Open")
        .all()
    )

    result = []
    for chat_model, project_id, preview_file_id in chats:
        chat = chat_model.present()
        chat["entity_name"], _, _ = names_service.get_full_entity_name(
            chat["object_id"]
        )
        chat["project_id"] = project_id
        chat["preview_file_id"] = preview_file_id
        result.append(chat)
    return result


def _add_attachments_to_message(message, files):
    """
    Create an attachment entry and for each given uploaded files and tie it
    to given message.
    """
    message["attachment_files"] = []
    for uploaded_file in files.values():
        try:
            attachment_file = _create_attachment(message, uploaded_file)
            message["attachment_files"].append(attachment_file)
        except IntegrityError:
            attachment_file = _create_attachment(
                message, uploaded_file, randomize=True
            )
            message["attachment_files"].append(attachment_file)
    return message


def _create_attachment(message, uploaded_file, randomize=False):
    tmp_folder = current_app.config["TMP_DIR"]

    # Prepare file name and create db entry
    filename = uploaded_file.filename
    mimetype = uploaded_file.mimetype
    extension = fs.get_file_extension(filename)
    if randomize:
        letters = string.ascii_lowercase
        random_str = "".join(random.choice(letters) for i in range(8))
        filename = f"{filename[:len(filename) - len(extension) - 1]}"
        filename += f"-{random_str}.{extension}"
    attachment_file = AttachmentFile.create(
        name=filename,
        size=0,
        extension=extension,
        mimetype=mimetype,
        chat_message_id=message["id"],
    )

    # Store attachment file
    attachment_file_id = str(attachment_file.id)
    tmp_file_path = fs.save_file(tmp_folder, attachment_file_id, uploaded_file)
    size = fs.get_file_size(tmp_file_path)
    attachment_file.update({"size": size})
    file_store.add_file("attachments", attachment_file_id, tmp_file_path)

    # Create thumbnail for pictures
    if "png" in mimetype or "jpg" in mimetype:
        image_path = tmp_file_path
        if "jpg" in mimetype:
            image_path = thumbnail.convert_jpg_to_png(tmp_file_path)
        thumbnail.resize(image_path, (150, 150), True)
        file_store.add_picture("thumbnails", attachment_file_id, image_path)
        fs.rm_file(image_path)
        fs.rm_file(tmp_file_path)
    return attachment_file.present()
