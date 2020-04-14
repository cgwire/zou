from zou.app.models.attachment_file import AttachmentFile
from zou.app.services import base_service
from zou.app.services.exception import (
    AttachmentFileNotFoundException,
)

from flask import current_app

from zou.app.utils import cache, fs
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
