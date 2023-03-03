from zou.app.utils.api import create_blueprint_for_api

from .resources import (
    AckCommentResource,
    AddAttachmentToCommentResource,
    AttachmentResource,
    CommentTaskResource,
    CommentManyTasksResource,
    DownloadAttachmentResource,
    ProjectAttachmentFiles,
    TaskAttachmentFiles,
    ReplyCommentResource,
    DeleteReplyCommentResource,
)


routes = [
    (
        "/data/tasks/<uuid:task_id>/comments/<uuid:comment_id>/ack",
        AckCommentResource,
    ),
    (
        "/data/tasks/<uuid:task_id>/comments/<uuid:comment_id>/reply",
        ReplyCommentResource,
    ),
    (
        "/data/tasks/<uuid:task_id>/comments/<uuid:comment_id>/attachments/<uuid:attachment_id>",
        AttachmentResource,
    ),
    (
        "/data/tasks/<uuid:task_id>/comments/<uuid:comment_id>/reply/<uuid:reply_id>",
        DeleteReplyCommentResource,
    ),
    (
        "/data/attachment-files/<uuid:attachment_file_id>/file/<string:file_name>",
        DownloadAttachmentResource,
    ),
    (
        "/actions/tasks/<uuid:task_id>/comments/<uuid:comment_id>/add-attachment",
        AddAttachmentToCommentResource,
    ),
    (
        "/data/projects/<uuid:project_id>/attachment-files",
        ProjectAttachmentFiles,
    ),
    ("/data/tasks/<uuid:task_id>/attachment-files", TaskAttachmentFiles),
    ("/actions/tasks/<uuid:task_id>/comment", CommentTaskResource),
    (
        "/actions/projects/<uuid:project_id>/tasks/comment-many",
        CommentManyTasksResource,
    ),
]

blueprint = create_blueprint_for_api("comments", routes)
