from zou.app.models.attachment_file import AttachmentFile
from zou.app.services import (
    base_service,
    persons_service,
    tasks_service
)
from zou.app.services.exception import (
    AttachmentFileNotFoundException
)

from zou.app.utils import cache, events, fs, fields
from zou.app.stores import file_store
from zou.app import config


def get_attachment_file_raw(attachment_file_id):
    return base_service.get_instance(
        AttachmentFile,
        attachment_file_id,
        AttachmentFileNotFoundException
    )


@cache.memoize_function(120)
def get_attachment_file(attachment_file_id):
    """
    Return attachment file model matching given id.
    """
    attachment_file = get_attachment_file_raw(attachment_file_id)
    return attachment_file.serialize()


def get_attachment_file_path(attachment_file):
    return fs.get_file_path(
        config,
        file_store.get_local_file_path,
        file_store.open_file,
        "attachments",
        attachment_file["id"],
        attachment_file["extension"]
    )


def acknowledge_comment(comment_id):
    """
    Add current user to the list of people who acknowledged given comment.
    If he's already present, remove it.
    """
    comment = tasks_service.get_comment_raw(comment_id)
    current_user = persons_service.get_current_user_raw()
    current_user_id = str(current_user.id)

    acknowledgements = fields.serialize_orm_arrays(comment.acknowledgements)
    is_already_ack = current_user_id in acknowledgements

    if is_already_ack:
        _unack_comment(comment, current_user)
    else:
        _ack_comment(comment, current_user)
    comment.save()
    return comment.serialize(relations=True)


def _ack_comment(comment, user):
    user_id = str(user.id)
    comment.acknowledgements.append(user)
    _send_ack_event(comment, user_id, "acknowledge")


def _unack_comment(comment, user):
    user_id = str(user.id)
    comment.acknowledgements = [
        person
        for person in comment.acknowledgements
        if str(person.id) != user_id
    ]
    _send_ack_event(comment, user_id, "unacknowledge")


def _send_ack_event(comment, user_id, name="acknowledge"):
    events.emit("comment:%s" % name, {
        "comment_id": str(comment.id),
        "person_id": user_id
    }, persist=False)
