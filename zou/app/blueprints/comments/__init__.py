from flask import Blueprint

from zou.app.utils.api import configure_api_from_blueprint

from .resources import (
    AckCommentResource,
    CommentTaskResource,
    CommentManyTasksResource,
    DownloadAttachmentResource,
    ProjectAttachmentFiles,
)


routes = [
    ("/data/tasks/<task_id>/comments/<comment_id>/ack", AckCommentResource),
    (
        "/data/attachment-files/<attachment_file_id>/file/<file_name>",
        DownloadAttachmentResource,
    ),
    ("/data/projects/<project_id>/attachment-files", ProjectAttachmentFiles),
    ("/actions/tasks/<task_id>/comment", CommentTaskResource),
    (
        "/actions/projects/<project_id>/tasks/comment-many",
        CommentManyTasksResource,
    ),
]

blueprint = Blueprint("comments", "comments")
api = configure_api_from_blueprint(blueprint, routes)
