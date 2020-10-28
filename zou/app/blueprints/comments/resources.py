import json

from flask import abort, request, send_file as flask_send_file
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required

from zou.app.utils import permissions

from zou.app.services import (
    comments_service,
    persons_service,
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
        user_service.check_entity_access(task["entity_id"])
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
        user_service.check_entity_access(task["entity_id"])
        return comments_service.acknowledge_comment(comment_id)


class CommentTaskResource(Resource):
    """
    Creates a new comment for given task. It requires a text, a task_status
    and a person as arguments. This way, comments keep history of status
    changes. When the comment is created, it updates the task status with
    given task status.
    """

    @jwt_required
    def post(self, task_id):
        (
            task_status_id,
            comment,
            person_id,
            created_at,
            checklist
        ) = self.get_arguments()

        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        files = request.files

        if not permissions.has_manager_permissions():
            person_id = None
            created_at = None
        comment = comments_service.create_comment(
            person_id,
            task_id,
            task_status_id,
            comment,
            checklist,
            files,
            created_at
        )
        return comment, 201

    def get_arguments(self):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "task_status_id", required=True, help="Task Status ID is missing"
        )
        parser.add_argument("comment", default="")
        parser.add_argument("person_id", default="")
        parser.add_argument("created_at", default="")
        if request.json is None:
            parser.add_argument("checklist", default="[]")
            args = parser.parse_args()
            checklist = args["checklist"]
            checklist = json.loads(checklist)
        else:
            parser.add_argument(
                "checklist",
                type=dict,
                action="append",
                default=[]
            )
            args = parser.parse_args()
            checklist = args["checklist"]

        return (
            args["task_status_id"],
            args["comment"],
            args["person_id"],
            args["created_at"],
            checklist
        )


class CommentManyTasksResource(Resource):
    """
    Create several comments at once. Each comment, requires a text, a task id,
    task_status and a person as arguments. This way, comments keep history of
    status changes. When the comment is created, it updates the task status with
    given task status.
    """

    @jwt_required
    def post(self, project_id):
        comments = request.json
        person_id = persons_service.get_current_user()["id"]
        try:
            user_service.check_manager_project_access(project_id)
        except permissions.PermissionDenied:
            comments = self.get_allowed_comments_only(comments, person_id)
        result = []
        for comment in comments:
            try:
                comment = comments_service.create_comment(
                    person_id,
                    comment["object_id"],
                    comment["task_status_id"],
                    comment["comment"],
                    [],
                    {},
                    None
                )
                result.append(comment)
            except KeyError:
                pass
        return result, 201

    def get_allowed_comments_only(self, comments, person_id):
        allowed_comments = []
        for comment in comments:
            try:
                task = tasks_service.get_task_with_relations(
                    comment["object_id"],
                )
                if person_id in task["assignees"]:
                    allowed_comments.append(comment)
            except permissions.PermissionDenied:
                pass
            except KeyError:
                pass
        return allowed_comments
