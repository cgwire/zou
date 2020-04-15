from flask import Blueprint

from zou.app.utils.api import configure_api_from_blueprint

from .resources import (
    AckCommentResource,
    DownloadAttachmentResource,
)


routes = [
    ("/data/tasks/<task_id>/comments/<comment_id>/ack", AckCommentResource),
    (
        "/data/attachment-files/<attachment_file_id>/file",
        DownloadAttachmentResource
    ),
]

blueprint = Blueprint("comments", "comments")
api = configure_api_from_blueprint(blueprint, routes)
