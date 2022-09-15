import json

from flask import abort, request, send_file as flask_send_file
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required

from zou.app.mixin import ArgsMixin
from zou.app.utils import permissions

from zou.app.services import (
    comments_service,
    deletion_service,
    persons_service,
    tasks_service,
    user_service,
)


class DownloadAttachmentResource(Resource):
    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: file_name
            required: True
            type: string
            x-example: filename
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
        except Exception:
            abort(404)


class AckCommentResource(Resource):
    """
    Acknowledge given comment. If it's already acknowledged, remove
    acknowledgement.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Comment acknowledged
        """
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
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
                        format: UUID
                        example: a24a6ea4-ce75-4665-a070-57453082c25a4-ce75-4665-a070-57453082c25
                    comment:
                        type: string
                    person_id:
                        type: string
                        format: UUID
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
            created_at,
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
                "checklist", type=dict, action="append", default=[]
            )
            args = parser.parse_args()
            checklist = args["checklist"]

        return (
            args["task_status_id"],
            args["comment"],
            args["person_id"],
            args["created_at"],
            checklist,
        )


class AttachmentResource(Resource):
    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: attachment_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Empty response
        """
        user = persons_service.get_current_user()
        comment = tasks_service.get_comment(comment_id)
        if comment["person_id"] != user["id"]:
            permissions.check_admin_permissions()

        deletion_service.remove_attachment_file_by_id(attachment_id)
        return "", 204


class AddAttachmentToCommentResource(Resource):
    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
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
            permissions.check_admin_permissions()

        files = request.files
        comment = comments_service.add_attachments_to_comment(comment, files)
        return comment["attachment_files"], 201


class CommentManyTasksResource(Resource):
    """
    Create several comments at once. Each comment requires a text, a task id,
    a task_status and a person as arguments. This way, comments keep history of
    status changes. When the comment is created, it updates the task status with
    given task status.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
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
                        format: UUID
                        example: a24a6ea4-ce75-4665-a070-57453082c25a4-ce75-4665-a070-57453082c25
                    comment:
                        type: string
                    person_id:
                        type: string
                        format: UUID
                        example: a24a6ea4-ce75-4665-a070-57453082c25a4-ce75-4665-a070-57453082c25
                    object_id:
                        type: string
                        format: UUID
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
                comment = comments_service.create_comment(
                    person["id"],
                    comment["object_id"],
                    comment["task_status_id"],
                    comment["comment"],
                    [],
                    {},
                    None,
                )
                result.append(comment)
            except KeyError:
                pass
        return result, 201

    def get_allowed_comments_only(self, comments, person):
        allowed_comments = []
        for comment in comments:
            try:
                task = tasks_service.get_task_with_relations(
                    comment["object_id"],
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

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: formData
            name: text
            type: string
            x-example: comment
        responses:
            200:
                description: Reply to given comment
        """
        args = self.get_args(
            [
                ("text", "", False),
            ]
        )
        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        return comments_service.reply_comment(comment_id, args["text"])


class DeleteReplyCommentResource(Resource):
    """
    Delete given comment reply.
    """

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: comment_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
          - in: path
            name: reply_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: Given comment reply deleted
        """
        task = tasks_service.get_task(task_id)
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        reply = comments_service.get_reply(comment_id, reply_id)
        current_user = persons_service.get_current_user()
        if reply["person_id"] != current_user["id"]:
            permissions.check_admin_permissions()
        return comments_service.delete_reply(comment_id, reply_id)


class ProjectAttachmentFiles(Resource):
    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
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

    @jwt_required
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
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            200:
                description: All attachment files related to given task
        """
        permissions.check_admin_permissions()
        return comments_service.get_all_attachment_files_for_task(task_id)
