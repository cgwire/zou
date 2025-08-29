import orjson as json

from flask import abort, request, send_file as flask_send_file, current_app
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.utils import permissions, date_helpers

from zou.app.services import (
    chats_service,
    comments_service,
    deletion_service,
    entities_service,
    persons_service,
    tasks_service,
    user_service,
)
from zou.app import config


class DownloadAttachmentResource(Resource):
    @jwt_required()
    def get(self, attachment_file_id, file_name):
        """
        Download attachment file.
        ---
        tags:
        - Comments
        produces:
          - multipart/form-data
          - image/png
          - image/gif
          - image/jpeg
        parameters:
          - in: path
            name: attachment_file_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: file_name
            required: True
            type: string
            example: filename
        responses:
            200:
                description: Attachment file downloaded
                schema:
                    type: file
            404:
                description: Download failed
        """
        attachment_file = comments_service.get_attachment_file(
            attachment_file_id
        )
        if attachment_file["comment_id"] is not None:
            comment = tasks_service.get_comment(attachment_file["comment_id"])
            user_service.check_task_access(comment["object_id"])
        elif attachment_file["chat_message_id"] is not None:
            message = chats_service.get_chat_message(
                attachment_file["chat_message_id"]
            )
            chat = chats_service.get_chat_by_id(message["chat_id"])
            entity = entities_service.get_entity(chat["object_id"])
            user_service.check_project_access(entity["project_id"])
        else:
            raise permissions.PermissionDenied()
        try:
            file_path = comments_service.get_attachment_file_path(
                attachment_file
            )
            return flask_send_file(
                file_path,
                conditional=True,
                mimetype=attachment_file["mimetype"],
                as_attachment=False,
                download_name=attachment_file["name"],
                max_age=config.CLIENT_CACHE_MAX_AGE,
                last_modified=date_helpers.get_datetime_from_string(
                    attachment_file["updated_at"]
                ),
            )
        except Exception:
            if config.LOG_FILE_NOT_FOUND:
                current_app.logger.error(
                    f"Attachment file was not found for: {attachment_file_id}"
                )
            abort(404)


class AckCommentResource(Resource):
    """
    Acknowledge given comment. If it's already acknowledged, remove
    acknowledgement.
    """

    @jwt_required()
    def post(self, task_id, comment_id):
        """
        Acknowledge given comment.
        ---
        tags:
        - Comments
        description: If it's already acknowledged, remove acknowledgement.
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Comment acknowledged
        """
        user_service.check_task_access(task_id)
        return comments_service.acknowledge_comment(comment_id)


class CommentTaskResource(Resource):
    """
    Creates a new comment for given task. It requires a text, a task_status
    and a person as arguments. This way, comments keep history of status
    changes. When the comment is created, it updates the task status with
    given task status.
    """

    @jwt_required()
    def post(self, task_id):
        """
        Create a new comment for given task.
        ---
        tags:
        - Comments
        description: It requires a text, a task_status and a person as arguments.
                     This way, comments keep history of status changes.
                     When the comment is created, it updates the task status with given task status.
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: body
            name: Comment
            description: person ID, name, comment, revision and change status of task
            schema:
                type: object
                required:
                    - task_status_id
                properties:
                    task_status_id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25a4-ce75-4665-a070-57453082c25
                    comment:
                        type: string
                    person_id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25a4-ce75-4665-a070-57453082c25
                    created_at:
                        type: string
                        format: date-time
                        example: "2022-07-12T13:00:00"
                    checklist:
                        type: object
                        properties:
                            item 1:
                                type: string
        responses:
            201:
                description: New comment created
        """
        (
            task_status_id,
            comment,
            person_id,
            created_at,
            checklist,
            links,
        ) = self.get_arguments()

        user_service.check_task_action_access(task_id)
        user_service.check_task_status_access(task_status_id)
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
            created_at,
            links,
        )
        return comment, 201

    def get_arguments(self):
        parser = reqparse.RequestParser()
        if request.is_json:
            location = ["values", "json"]
            parser.add_argument(
                "checklist",
                type=dict,
                action="append",
                default=[],
                location=location,
            )
            parser.add_argument(
                "links",
                type=str,
                action="append",
                default=[],
                location=location,
            )
        else:
            location = "values"
            parser.add_argument("checklist", default="[]", location=location)
            parser.add_argument("links", default="[]", location=location)
        parser.add_argument(
            "task_status_id",
            required=True,
            help="Task Status ID is missing",
            location=location,
        )
        parser.add_argument("comment", default="", location=location)
        parser.add_argument("person_id", default="", location=location)
        parser.add_argument("created_at", default="", location=location)
        args = parser.parse_args()
        return (
            args["task_status_id"],
            args["comment"],
            args["person_id"],
            args["created_at"],
            (
                args["checklist"]
                if request.is_json
                else json.loads(args["checklist"])
            ),
            (args["links"] if request.is_json else json.loads(args["links"])),
        )


class AttachmentResource(Resource):
    @jwt_required()
    def delete(self, task_id, comment_id, attachment_id):
        """
        Delete attachment linked to a comment matching given ID.
        ---
        tags:
        - Comments
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: attachment_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Empty response
        """
        user = persons_service.get_current_user()
        comment = tasks_service.get_comment(comment_id)
        if comment["person_id"] != user["id"]:
            task = tasks_service.get_task(task_id)
            user_service.check_manager_project_access(task["project_id"])

        deletion_service.remove_attachment_file_by_id(attachment_id)
        return "", 204


class AddAttachmentToCommentResource(Resource):
    @jwt_required()
    def post(self, task_id, comment_id):
        """
        Add given files to the comment entry as attachments.
        ---
        tags:
        - Comments
        consumes:
          - image/png
          - image/gif
          - image/jpeg
          - multipart/form-data
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: reply_id
            type: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            required: True
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: files
            type: file
            required: True
        responses:
            201:
                description: Given files added to the comment entry as attachments
        """
        user = persons_service.get_current_user()
        comment = tasks_service.get_comment(comment_id)
        if comment["person_id"] != user["id"]:
            task = tasks_service.get_task(task_id)
            user_service.check_manager_project_access(task["project_id"])

        files = request.files
        comment = comments_service.add_attachments_to_comment(
            comment, files, reply_id=None
        )
        return comment["attachment_files"], 201


class CommentManyTasksResource(Resource):
    """
    Create several comments at once. Each comment requires a text, a task id,
    a task_status and a person as arguments. This way, comments keep history of
    status changes. When the comment is created, it updates the task status with
    given task status.
    """

    @jwt_required()
    def post(self, project_id):
        """
        Create several comments at once.
        ---
        tags:
        - Comments
        description: Each comment requires a text, a task id, a task_status and a person as arguments.
                     This way, comments keep history of status changes.
                     When the comment is created, it updates the task status with given task status.
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: body
            name: Comment
            description: person ID, name, comment, revision and change status of task
            schema:
                type: object
                required:
                    - task_status_id
                properties:
                    task_status_id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25a4-ce75-4665-a070-57453082c25
                    comment:
                        type: string
                    person_id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25a4-ce75-4665-a070-57453082c25
                    object_id:
                        type: string
                        format: uuid
                        example: a24a6ea4-ce75-4665-a070-57453082c25a4-ce75-4665-a070-57453082c25
                    created_at:
                        type: string
                        format: date-time
                        example: "2022-07-12T13:00:00"
                    checklist:
                        type: object
                        properties:
                            item 1:
                                type: string
        responses:
            201:
                description: Given files added to the comment entry as attachments
        """
        comments = request.json
        person = persons_service.get_current_user(relations=True)
        try:
            user_service.check_manager_project_access(project_id)
        except permissions.PermissionDenied:
            comments = self.get_allowed_comments_only(comments, person)
        result = []
        for comment in comments:
            try:
                user_service.check_task_status_access(
                    comment["task_status_id"]
                )
                comment = comments_service.create_comment(
                    person["id"],
                    comment["object_id"],
                    comment["task_status_id"],
                    comment["comment"],
                    [],
                    {},
                    None,
                    comment.get("links", []),
                )
                result.append(comment)
            except KeyError:
                pass
        return result, 201

    def get_allowed_comments_only(self, comments, person):
        allowed_comments = []
        for comment in comments:
            try:
                task = tasks_service.get_task(
                    comment["object_id"], relations=True
                )
                if (
                    person["role"] == "supervisor"
                    and (
                        len(person["departments"]) == 0
                        or tasks_service.get_task_type(task["task_type_id"])[
                            "department_id"
                        ]
                        in person["departments"]
                    )
                ) or person["id"] in task["assignees"]:
                    allowed_comments.append(comment)
            except permissions.PermissionDenied:
                pass
            except KeyError:
                pass
        return allowed_comments


class ReplyCommentResource(Resource, ArgsMixin):
    """
    Reply to given comment. Add comment to its replies list.
    """

    @jwt_required()
    def post(self, task_id, comment_id):
        """
        Reply to given comment.
        ---
        tags:
        - Comments
        description: Add comment to its replies list.
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: text
            type: string
            example: comment
        responses:
            200:
                description: Reply to given comment
        """
        comment = tasks_service.get_comment(comment_id)
        current_user = persons_service.get_current_user()
        if comment["person_id"] != current_user["id"]:
            if permissions.has_client_permissions():
                raise permissions.PermissionDenied()
            user_service.check_task_action_access(task_id)

        args = self.get_args(
            [
                ("text", "", False),
            ]
        )
        files = request.files
        return comments_service.reply_comment(
            comment_id,
            args["text"],
            files=files
        )


class DeleteReplyCommentResource(Resource):
    """
    Delete given comment reply.
    """

    @jwt_required()
    def delete(self, task_id, comment_id, reply_id):
        """
        Delete given comment reply.
        ---
        tags:
        - Comments
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: reply_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given comment reply deleted
        """
        reply = comments_service.get_reply(comment_id, reply_id)
        current_user = persons_service.get_current_user()
        if reply["person_id"] != current_user["id"]:
            permissions.check_admin_permissions()
        return comments_service.delete_reply(comment_id, reply_id)


class ProjectAttachmentFiles(Resource):
    @jwt_required()
    def get(self, project_id):
        """
        Return all attachment files related to given project.
        ---
        tags:
        - Comments
        parameters:
          - in: path
            name: project_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All attachment files related to given project
        """
        permissions.check_admin_permissions()
        return comments_service.get_all_attachment_files_for_project(
            project_id
        )


class TaskAttachmentFiles(Resource):
    """
    Return all attachment files related to given task.
    """

    @jwt_required()
    def get(self, task_id):
        """
        Return all attachment files related to given task.
        ---
        tags:
        - Comments
        parameters:
          - in: path
            name: task_id
            required: True
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All attachment files related to given task
        """
        permissions.check_admin_permissions()
        return comments_service.get_all_attachment_files_for_task(task_id)
