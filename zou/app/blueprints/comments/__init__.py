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
    ("/data/tasks/<task_id>/comments/<comment_id>/ack", AckCommentResource),
    (
        "/data/tasks/<task_id>/comments/<comment_id>/reply",
        ReplyCommentResource,
    ),
    (
        "/data/tasks/<task_id>/comments/<comment_id>/attachments/<attachment_id>",
        AttachmentResource,
    ),
    (
        "/data/tasks/<task_id>/comments/<comment_id>/reply/<reply_id>",
        DeleteReplyCommentResource,
    ),
    (
        "/data/attachment-files/<attachment_file_id>/file/<file_name>",
        DownloadAttachmentResource,
    ),
    (
        "/actions/tasks/<task_id>/comments/<comment_id>/add-attachment",
        AddAttachmentToCommentResource,
    ),
    ("/data/projects/<project_id>/attachment-files", ProjectAttachmentFiles),
    ("/data/tasks/<task_id>/attachment-files", TaskAttachmentFiles),
    ("/actions/tasks/<task_id>/comment", CommentTaskResource),
    (
        "/actions/projects/<project_id>/tasks/comment-many",
        CommentManyTasksResource,
    ),
]

blueprint = create_blueprint_for_api("comments", routes)
