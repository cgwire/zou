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
        Download attachment file
        ---
        description: Download a specific attachment file from a comment or chat
          message. Supports various file types including images and documents.
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
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the attachment file
          - in: path
            name: file_name
            required: true
            type: string
            example: "document.pdf"
            description: Name of the file to download
        responses:
          200:
            description: Attachment file successfully downloaded
            content:
              application/octet-stream:
                schema:
                  type: string
                  format: binary
                  description: File content
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

    @jwt_required()
    def post(self, task_id, comment_id):
        """
        Acknowledge comment
        ---
        description: Acknowledge a specific comment. If it's already
          acknowledged, remove the acknowledgement.
        tags:
          - Comments
        parameters:
          - in: path
            name: task_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the task
          - in: path
            name: comment_id
            required: true
            type: string
            format: uuid
            example: b35b7fb5-df86-5776-b181-68564193d36
            description: Unique identifier of the comment
        responses:
          200:
            description: Comment acknowledgement status successfully updated
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Comment unique identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    acknowledged:
                      type: boolean
                      description: Whether the comment is acknowledged
                      example: true
        """
        user_service.check_task_access(task_id)
        return comments_service.acknowledge_comment(comment_id)


class CommentTaskResource(Resource):

    @jwt_required()
    def post(self, task_id):
        """
        Create task comment
        ---
        description: Create a new comment for a specific task. It requires a
          text, a task_status and a person as arguments. This way, comments
          keep history of status changes. When the comment is created, it
          updates the task status with the given task status.
        tags:
          - Comments
        parameters:
          - in: path
            name: task_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the task
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: object
                required:
                  - task_status_id
                properties:
                  task_status_id:
                    type: string
                    format: uuid
                    description: Task status identifier
                    example: c46c8gc6-eg97-6887-c292-79675204e47
                  comment:
                    type: string
                    description: Comment text content
                    example: "This looks great! Ready for review."
                  person_id:
                    type: string
                    format: uuid
                    description: Person identifier (optional, defaults to current user)
                    example: d57d9hd7-fh08-7998-d403-80786315f58
                  created_at:
                    type: string
                    format: date-time
                    description: Creation timestamp (optional, defaults to current time)
                    example: "2023-01-01T12:00:00Z"
                  checklist:
                    type: object
                    description: Checklist items for the comment
                    example: {"item1": "Check lighting", "item2": "Verify textures"}
                  links:
                    type: array
                    items:
                      type: string
                    description: List of related links
                    example: ["https://example.com/reference1", "https://example.com/reference2"]
        responses:
          201:
            description: Comment successfully created
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Comment unique identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    task_id:
                      type: string
                      format: uuid
                      description: Task identifier
                      example: a24a6ea4-ce75-4665-a070-57453082c25
                    person_id:
                      type: string
                      format: uuid
                      description: Person identifier
                      example: d57d9hd7-fh08-7998-d403-80786315f58
                    comment:
                      type: string
                      description: Comment text content
                      example: "This looks great! Ready for review."
                    task_status_id:
                      type: string
                      format: uuid
                      description: Task status identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
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
        Delete comment attachment
        ---
        description: Delete a specific attachment file linked to a comment. Only
          the comment author or project managers can delete attachments.
        tags:
          - Comments
        parameters:
          - in: path
            name: task_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the task
          - in: path
            name: comment_id
            required: true
            type: string
            format: uuid
            example: b35b7fb5-df86-5776-b181-68564193d36
            description: Unique identifier of the comment
          - in: path
            name: attachment_id
            required: true
            type: string
            format: uuid
            example: c46c8gc6-eg97-6887-c292-79675204e47
            description: Unique identifier of the attachment
        responses:
          204:
            description: Attachment successfully deleted
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
        Add comment attachments
        ---
        description: Add one or more files as attachments to a specific comment.
          Supports various file types including images and documents.
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
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the task
          - in: path
            name: comment_id
            required: true
            type: string
            format: uuid
            example: b35b7fb5-df86-5776-b181-68564193d36
            description: Unique identifier of the comment
          - in: formData
            name: reply_id
            type: string
            format: uuid
            example: c46c8gc6-eg97-6887-c292-79675204e47
            description: Reply identifier (optional)
          - in: formData
            name: files
            type: file
            required: true
            description: Files to attach to the comment
        responses:
          201:
            description: Files successfully added as attachments
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Attachment file unique identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      name:
                        type: string
                        description: File name
                        example: "document.pdf"
                      mimetype:
                        type: string
                        description: File MIME type
                        example: "application/pdf"
                      size:
                        type: integer
                        description: File size in bytes
                        example: 1024000
                      comment_id:
                        type: string
                        format: uuid
                        description: Comment identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
        """
        user = persons_service.get_current_user()
        comment = tasks_service.get_comment(comment_id)
        if comment["person_id"] != user["id"]:
            task = tasks_service.get_task(task_id)
            user_service.check_manager_project_access(task["project_id"])

        files = request.files
        comment, _ = comments_service.add_attachments_to_comment(
            comment, files, reply_id=None
        )
        return comment["attachment_files"], 201


class CommentManyTasksResource(Resource):

    @jwt_required()
    def post(self, project_id):
        """
        Create multiple comments
        ---
        description: Create several comments at once for a specific project.
          Each comment requires a text, a task id, a task_status and a person as
          arguments. This way, comments keep history of status changes. When
          the comment is created, it updates the task status with the given
          task status.
        tags:
          - Comments
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
        requestBody:
          required: true
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  required:
                    - task_status_id
                    - object_id
                  properties:
                    task_status_id:
                      type: string
                      format: uuid
                      description: Task status identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    comment:
                      type: string
                      description: Comment text content
                      example: "This looks great! Ready for review."
                    person_id:
                      type: string
                      format: uuid
                      description: Person identifier (optional, defaults to current user)
                      example: d57d9hd7-fh08-7998-d403-80786315f58
                    object_id:
                      type: string
                      format: uuid
                      description: Task identifier
                      example: e68e0ie8-gi19-8009-e514-91897426g69
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp (optional, defaults to current time)
                      example: "2023-01-01T12:00:00Z"
                    checklist:
                      type: object
                      description: Checklist items for the comment
                      example: {"item1": "Check lighting", "item2": "Verify textures"}
                    links:
                      type: array
                      items:
                        type: string
                      description: List of related links
                      example: ["https://example.com/reference1", "https://example.com/reference2"]
        responses:
          201:
            description: Comments successfully created
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Comment unique identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      task_id:
                        type: string
                        format: uuid
                        description: Task identifier
                        example: e68e0ie8-gi19-8009-e514-91897426g69
                      person_id:
                        type: string
                        format: uuid
                        description: Person identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      comment:
                        type: string
                        description: Comment text content
                        example: "This looks great! Ready for review."
                      task_status_id:
                        type: string
                        format: uuid
                        description: Task status identifier
                        example: c46c8gc6-eg97-6887-c292-79675204e47
                      created_at:
                        type: string
                        format: date-time
                        description: Creation timestamp
                        example: "2023-01-01T12:00:00Z"
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

    @jwt_required()
    def post(self, task_id, comment_id):
        """
        Reply to comment
        ---
        description: Add a reply to a specific comment. The reply will be added
          to the comment's replies list.
        tags:
          - Comments
        parameters:
          - in: path
            name: task_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the task
          - in: path
            name: comment_id
            required: true
            type: string
            format: uuid
            example: b35b7fb5-df86-5776-b181-68564193d36
            description: Unique identifier of the comment
          - in: formData
            name: text
            type: string
            example: "Thanks for the feedback!"
            description: Reply text content
        responses:
          200:
            description: Reply successfully added to comment
            content:
              application/json:
                schema:
                  type: object
                  properties:
                    id:
                      type: string
                      format: uuid
                      description: Reply unique identifier
                      example: c46c8gc6-eg97-6887-c292-79675204e47
                    comment_id:
                      type: string
                      format: uuid
                      description: Parent comment identifier
                      example: b35b7fb5-df86-5776-b181-68564193d36
                    text:
                      type: string
                      description: Reply text content
                      example: "Thanks for the feedback!"
                    person_id:
                      type: string
                      format: uuid
                      description: Person identifier who made the reply
                      example: d57d9hd7-fh08-7998-d403-80786315f58
                    created_at:
                      type: string
                      format: date-time
                      description: Creation timestamp
                      example: "2023-01-01T12:00:00Z"
        """
        comment = tasks_service.get_comment(comment_id)
        current_user = persons_service.get_current_user()
        if comment["person_id"] != current_user["id"]:
            if permissions.has_client_permissions():
                author = persons_service.get_person(comment["person_id"])
                if (
                    current_user["studio_id"] != author["studio_id"]
                    and author["role"] == "client"
                ):
                    raise permissions.PermissionDenied()
            user_service.check_task_action_access(task_id)

        args = self.get_args(
            [
                ("text", "", False),
            ]
        )
        files = request.files
        return comments_service.reply_comment(
            comment_id, args["text"], files=files
        )


class DeleteReplyCommentResource(Resource):

    @jwt_required()
    def delete(self, task_id, comment_id, reply_id):
        """
        Delete comment reply
        ---
        description: Delete a specific reply from a comment.
         Only the reply author or administrators can delete replies.
        tags:
          - Comments
        parameters:
          - in: path
            name: task_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the task
          - in: path
            name: comment_id
            required: true
            type: string
            format: uuid
            example: b35b7fb5-df86-5776-b181-68564193d36
            description: Unique identifier of the comment
          - in: path
            name: reply_id
            required: true
            type: string
            format: uuid
            example: c46c8gc6-eg97-6887-c292-79675204e47
            description: Unique identifier of the reply
        responses:
          200:
            description: Reply successfully deleted
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
        Get project attachment files
        ---
        description: Retrieve all attachment files related to a specific
          project. Requires administrator permissions.
        tags:
          - Comments
        parameters:
          - in: path
            name: project_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the project
        responses:
          200:
            description: Project attachment files successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Attachment file unique identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      name:
                        type: string
                        description: File name
                        example: "document.pdf"
                      mimetype:
                        type: string
                        description: File MIME type
                        example: "application/pdf"
                      size:
                        type: integer
                        description: File size in bytes
                        example: 1024000
                      comment_id:
                        type: string
                        format: uuid
                        description: Comment identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      project_id:
                        type: string
                        format: uuid
                        description: Project identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
        """
        permissions.check_admin_permissions()
        return comments_service.get_all_attachment_files_for_project(
            project_id
        )


class TaskAttachmentFiles(Resource):

    @jwt_required()
    def get(self, task_id):
        """
        Get task attachment files
        ---
        description: Retrieve all attachment files related to a specific task.
          Requires administrator permissions.
        tags:
          - Comments
        parameters:
          - in: path
            name: task_id
            required: true
            type: string
            format: uuid
            example: a24a6ea4-ce75-4665-a070-57453082c25
            description: Unique identifier of the task
        responses:
          200:
            description: Task attachment files successfully retrieved
            content:
              application/json:
                schema:
                  type: array
                  items:
                    type: object
                    properties:
                      id:
                        type: string
                        format: uuid
                        description: Attachment file unique identifier
                        example: d57d9hd7-fh08-7998-d403-80786315f58
                      name:
                        type: string
                        description: File name
                        example: "document.pdf"
                      mimetype:
                        type: string
                        description: File MIME type
                        example: "application/pdf"
                      size:
                        type: integer
                        description: File size in bytes
                        example: 1024000
                      comment_id:
                        type: string
                        format: uuid
                        description: Comment identifier
                        example: b35b7fb5-df86-5776-b181-68564193d36
                      task_id:
                        type: string
                        format: uuid
                        description: Task identifier
                        example: a24a6ea4-ce75-4665-a070-57453082c25
                      reply_id:
                        type: string
                        format: uuid
                        description: Reply identifier if attached to a reply
                        example: c46c8gc6-eg97-6887-c292-79675204e47
        """
        permissions.check_admin_permissions()
        return comments_service.get_all_attachment_files_for_task(task_id)
