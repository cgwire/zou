import datetime
import json

from flask import abort, request, send_file as flask_send_file
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required

from zou.app.utils import events, permissions

from zou.app.services import (
    comments_service,
    notifications_service,
    news_service,
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
        task_status = tasks_service.get_task_status(task_status_id)

        if not permissions.has_manager_permissions():
            person_id = None
            created_at = None

        if person_id:
            person = persons_service.get_person(person_id)
        else:
            person = persons_service.get_current_user()

        comment = tasks_service.create_comment(
            object_id=task_id,
            object_type="Task",
            files=request.files,
            person_id=person["id"],
            task_status_id=task_status_id,
            text=comment,
            checklist=checklist,
            created_at=created_at
        )

        status_changed = task_status_id != task["task_status_id"]
        new_data = {
            "task_status_id": task_status_id,
            "last_comment_date": comment["created_at"],
        }
        if status_changed:
            if task_status["is_retake"]:
                retake_count = task["retake_count"]
                if retake_count is None or retake_count == "NoneType":
                    retake_count = 0
                new_data["retake_count"] = retake_count + 1

            if task_status["is_done"]:
                new_data["end_date"] = datetime.datetime.now()
            else:
                new_data["end_date"] = None

            if (
                task_status["short_name"] == "wip" and
                task["real_start_date"] is None
            ):
                new_data["real_start_date"] = datetime.datetime.now()

        tasks_service.update_task(task_id, new_data)
        if status_changed:
            events.emit("task:status-changed", {
                "task_id": task_id,
                "new_task_status_id": new_data["task_status_id"],
                "previous_task_status_id": task["task_status_id"]
            })

        task = tasks_service.get_task_with_relations(task_id)

        notifications_service.create_notifications_for_task_and_comment(
            task, comment, change=status_changed
        )
        news_service.create_news_for_task_and_comment(
            task, comment, change=status_changed
        )

        comment["task_status"] = task_status
        comment["person"] = person
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
            parser.add_argument("checklist", type=dict, action="append", default=[])
            args = parser.parse_args()
            checklist = args["checklist"]

        return (
            args["task_status_id"],
            args["comment"],
            args["person_id"],
            args["created_at"],
            checklist
        )
