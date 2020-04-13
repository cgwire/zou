from flask import Blueprint

from zou.app.utils.api import configure_api_from_blueprint

from .resources import (
    DownloadAttachmentResource,
)


routes = [
    (
        "/data/attachment-files/<attachment_file_id>/file",
        DownloadAttachmentResource
    ),
]

blueprint = Blueprint("comments", "comments")
api = configure_api_from_blueprint(blueprint, routes)
