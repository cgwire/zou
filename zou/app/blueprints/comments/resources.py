from flask import abort, send_file as flask_send_file
from flask_restful import Resource
from flask_jwt_extended import jwt_required

from zou.app.services import (
    comments_service,
    tasks_service,
    user_service
)


class DownloadAttachmentResource(Resource):
    @jwt_required
    def get(self, attachment_file_id):
        attachment_file = comments_service.get_attachment_file(
            attachment_file_id
        )
        comment = tasks_service.get_comment(attachment_file["comment_id"])
        task = tasks_service.get_task(comment["object_id"])
        user_service.check_project_access(task["project_id"])
        file_path = comments_service.get_attachment_file_path(attachment_file)
        try:
            return flask_send_file(
                file_path,
                conditional=True,
                mimetype=attachment_file["mimetype"],
                as_attachment=False,
                attachment_filename=attachment_file["name"],
            )
        except:
            abort(404)


class AckCommentResource(Resource):
    """
    Acknowledge given comment. If it's already acknowledged, remove
    acknowledgement.
    """

    @jwt_required
    def post(self, task_id, comment_id):
        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        return comments_service.acknowledge_comment(comment_id)
