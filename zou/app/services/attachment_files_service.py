import random
import string
from flask import current_app

from zou.app.models.attachment_file import AttachmentFile
from zou.app.models.comment import Comment
from zou.app.models.task import Task
from zou.app.services import base_service, files_service
from zou.app.exceptions import AttachmentFileNotFoundException
from zou.app.utils import cache, fs, fields
from zou.app.stores import file_store
from zou.app import config


def get_attachment_file_raw(attachment_file_id):
    """
    Return attachment file matching given id as an active record.
    """
    return base_service.get_instance(
        AttachmentFile, attachment_file_id, AttachmentFileNotFoundException
    )


@cache.memoize_function(120)
def get_attachment_file(attachment_file_id):
    """
    Return attachment file model matching given id.
    """
    attachment_file = get_attachment_file_raw(attachment_file_id)
    return attachment_file.serialize()


def clear_attachment_file_cache(attachment_file_id):
    """
    Drop the memoized serialization of given attachment file.
    """
    cache.cache.delete_memoized(get_attachment_file, attachment_file_id)


def get_attachment_file_path(attachment_file):
    """
    Get attachement file path when stored locally.
    """
    return fs.get_file_path_and_file(
        config,
        file_store.get_local_file_path,
        file_store.open_file,
        "attachments",
        attachment_file["id"],
        attachment_file["extension"],
        file_size=attachment_file["size"],
    )


def create_attachment(comment, uploaded_file, randomize=False, reply_id=None):
    """
    Store an uploaded file and tie the matching attachment entry to given
    comment. With randomize, the file name gets a random suffix, which is
    how a name collision on the same comment is resolved.
    """
    tmp_folder = current_app.config["TMP_DIR"]
    filename = uploaded_file.filename
    mimetype = uploaded_file.mimetype
    extension = fs.get_file_extension(filename)
    if randomize:
        letters = string.ascii_lowercase
        random_str = "".join(random.choice(letters) for i in range(8))
        filename = f"{filename[:len(filename) - len(extension) - 1]}"
        filename += f"-{random_str}.{extension}"

    if reply_id is not None:
        is_reply_present = any(
            reply["id"] == reply_id for reply in comment.get("replies", [])
        )
        if not is_reply_present:
            reply_id = None

    attachment_file = AttachmentFile.create(
        name=filename,
        size=0,
        extension=extension,
        mimetype=mimetype,
        reply_id=reply_id,
        comment_id=comment["id"],
    )
    attachment_file_id = str(attachment_file.id)

    # On storage failure, drop the database entry to avoid a ghost
    # attachment pointing to a missing object; the temporary file is
    # removed in every case.
    tmp_file_path = fs.save_file(tmp_folder, attachment_file_id, uploaded_file)
    try:
        size = fs.get_file_size(tmp_file_path)
        attachment_file.update({"size": size})
        file_store.add_file("attachments", attachment_file_id, tmp_file_path)
        return attachment_file.present()
    except Exception:
        try:
            attachment_file.delete()
        except Exception:
            current_app.logger.error(
                f"Failed to delete attachment file {attachment_file_id} "
                f"after a storage failure",
                exc_info=1,
            )
        raise
    finally:
        fs.rm_file(tmp_file_path)


def _attachment_files_query():
    """
    Base query joining the attachment files to the task they comment on.
    """
    return AttachmentFile.query.join(Comment).join(
        Task, Task.id == Comment.object_id
    )


def get_all_attachment_files_for_project(project_id):
    """
    Return all attachment files listed into given project. It is mainly needed
    for synchronisation purposes.
    """
    attachment_files = _attachment_files_query().filter(
        Task.project_id == project_id
    )
    return fields.serialize_models(attachment_files)


def get_all_attachment_files_for_task(task_id):
    """
    Return all attachment files listed into given task.
    """
    attachment_files = _attachment_files_query().filter(Task.id == task_id)
    return fields.serialize_models(attachment_files)


def build_attachment_map_for_comments(comment_ids):
    """
    Return the attachment files of each comment.
    """
    attachment_file_map = {}
    attachment_files = AttachmentFile.query.filter(
        AttachmentFile.comment_id.in_(comment_ids)
    ).all()
    for attachment_file in attachment_files:
        comment_id = str(attachment_file.comment_id)
        attachment_file_id = str(attachment_file.id)
        if comment_id not in attachment_file_map:
            attachment_file_map[str(comment_id)] = []
        attachment_file_map[str(comment_id)].append(
            {
                "id": attachment_file_id,
                "name": attachment_file.name,
                "extension": attachment_file.extension,
                "reply_id": attachment_file.reply_id,
                "size": attachment_file.size,
            }
        )
    return attachment_file_map


def remove_attachment_file(attachment_file):
    """
    Remove all files related to given attachment file, then remove the
    attachment file entry from the database.
    """

    files_service.remove_quietly(
        file_store.remove_file, "attachments", attachment_file.id
    )
    attachment_dict = attachment_file.serialize()
    attachment_file.delete()
    clear_attachment_file_cache(attachment_dict["id"])
    return attachment_dict


def remove_attachment_file_by_id(attachment_file_id):
    """
    Remove all files related to given attachment file, then remove the
    attachment file entry from the database.
    """
    attachment_file = AttachmentFile.get(attachment_file_id)
    if attachment_file is None:
        raise AttachmentFileNotFoundException
    return remove_attachment_file(attachment_file)
