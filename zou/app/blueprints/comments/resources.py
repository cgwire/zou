from flask import current_app, request, send_file as flask_send_file
from flask.views import MethodView
from flask_jwt_extended import jwt_required

from zou.app import config
from zou.app.blueprints.comments.schemas import (
    BatchCommentItemSchema,
    CommentCreateSchema,
    CommentReplySchema,
    CopyClientCommentsSchema,
    MoveCommentSchema,
)
from zou.app.exceptions import (
    AttachmentFileNotFoundException,
    WrongParameterException,
)
from zou.app.mixin import ArgsMixin
from zou.app.services import (
    attachment_files_service,
    chats_service,
    comments_service,
    permissions_service,
    persons_service,
    task_types_service,
    tasks_service,
)
from zou.app.utils import date_helpers, permissions, validation
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi.yml")


class DownloadAttachmentResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["DownloadAttachmentResource_get"])
    def get(self, attachment_file_id, file_name):
        """
        Download attachment file
        """
        attachment_file = attachment_files_service.get_attachment_file(
            attachment_file_id
        )
        if attachment_file["comment_id"] is not None:
            comment = comments_service.get_comment(
                attachment_file["comment_id"]
            )
            permissions_service.check_task_access(comment["object_id"])
        elif attachment_file["chat_message_id"] is not None:
            message = chats_service.get_chat_message(
                attachment_file["chat_message_id"]
            )
            chat = chats_service.get_chat_by_id(message["chat_id"])
            permissions_service.check_chat_access(chat["object_id"])
        else:
            raise permissions.PermissionDenied()
        try:
            file_path = attachment_files_service.get_attachment_file_path(
                attachment_file
            )
            return flask_send_file(
                file_path,
                conditional=True,
                mimetype=attachment_file["mimetype"],
                # Serve safe raster images inline so they display in the
                # browser; force download for everything else. The mimetype
                # comes verbatim from the uploader, so serving e.g. HTML/SVG
                # inline would let an attacker run code in Kitsu's origin
                # (stored XSS).
                as_attachment=not comments_service.is_inline_safe_mimetype(
                    attachment_file["mimetype"]
                ),
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
            raise AttachmentFileNotFoundException


class AckCommentResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["AckCommentResource_post"])
    def post(self, task_id, comment_id):
        """
        Acknowledge comment
        """
        comments_service.get_task_comment(task_id, comment_id)
        permissions_service.check_task_access(task_id)
        return comments_service.acknowledge_comment(comment_id)


class CommentTaskResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["CommentTaskResource_post"])
    def post(self, task_id):
        """
        Create task comment
        """
        (
            task_status_id,
            comment,
            person_id,
            created_at,
            checklist,
            links,
            for_client,
        ) = self.get_arguments()

        try:
            permissions_service.check_task_action_access(task_id)
        except permissions.PermissionDenied:
            # Being mentioned pulls someone into the conversation, so let
            # them answer in it. Nothing else: the status has to stay as it
            # is, and previews keep going through the preview routes, which
            # still require the full task action access.
            permissions_service.check_task_mention_access(task_id)
            task = tasks_service.get_task(task_id)
            if (
                str(task_status_id).lower()
                != str(task["task_status_id"]).lower()
            ):
                raise
        project_id = tasks_service.get_task(task_id)["project_id"]
        permissions_service.resolve_project_role(project_id)
        permissions_service.check_task_status_access(
            task_status_id, project_id
        )
        files = request.files

        if not permissions.has_manager_permissions():
            person_id = None
            created_at = None
            for_client = False
        comment = comments_service.create_comment(
            person_id,
            task_id,
            task_status_id,
            comment,
            checklist,
            files,
            created_at,
            links,
            for_client=for_client,
        )
        return comment, 201

    def get_arguments(self):
        body = validation.validate_request_body(CommentCreateSchema)
        return (
            body.task_status_id,
            body.comment,
            body.person_id,
            body.created_at,
            body.checklist,
            body.links,
            body.for_client,
        )


class AttachmentResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["AttachmentResource_delete"])
    def delete(self, task_id, comment_id, attachment_file_id):
        """
        Delete comment attachment
        """
        user = persons_service.get_current_user()
        comment = comments_service.get_comment(comment_id)
        if comment["object_id"] != task_id:
            raise permissions.PermissionDenied()
        # The author branch below skips the project check, so the attachment
        # must be tied to the comment too: otherwise pointing at one's own
        # comment deletes any attachment whose id the caller knows.
        attachment_file = attachment_files_service.get_attachment_file(
            attachment_file_id
        )
        if str(attachment_file["comment_id"]) != str(comment_id):
            raise permissions.PermissionDenied()
        if comment["person_id"] != user["id"]:
            task = tasks_service.get_task(task_id)
            permissions_service.check_manager_project_access(
                task["project_id"]
            )

        attachment_files_service.remove_attachment_file_by_id(
            attachment_file_id
        )
        return "", 204


class AddAttachmentToCommentResource(MethodView):
    @jwt_required()
    @swag_from(SPECS["AddAttachmentToCommentResource_post"])
    def post(self, task_id, comment_id):
        """
        Add comment attachments
        """
        user = persons_service.get_current_user()
        comment = comments_service.get_comment(comment_id)
        if comment["object_id"] != task_id:
            raise permissions.PermissionDenied()
        if comment["person_id"] != user["id"]:
            task = tasks_service.get_task(task_id)
            permissions_service.check_manager_project_access(
                task["project_id"]
            )

        files = request.files
        comment, _ = comments_service.add_attachments_to_comment(
            comment, files, reply_id=None
        )
        return comment["attachment_files"], 201


class CommentManyTasksResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["CommentManyTasksResource_post"])
    def post(self, project_id):
        """
        Create multiple comments
        """
        comments = [
            item.model_dump(mode="json", exclude_none=True)
            for item in validation.validate_request_list(
                BatchCommentItemSchema
            )
        ]
        person = persons_service.get_current_user(relations=True)
        try:
            permissions_service.check_manager_project_access(project_id)
        except permissions.PermissionDenied:
            comments = self.get_allowed_comments_only(comments, person)
        result = []
        for comment in comments:
            if (
                "task_status_id" not in comment
                or "object_id" not in comment
                or "comment" not in comment
            ):
                continue
            task_project_id = tasks_service.get_task(comment["object_id"])[
                "project_id"
            ]
            permissions_service.resolve_project_role(task_project_id)
            permissions_service.check_task_status_access(
                comment["task_status_id"], task_project_id
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
        return result, 201

    def get_allowed_comments_only(self, comments, person):
        allowed_comments = []
        # The person is constant and the comments almost always share one
        # project: memoize the role lookups instead of querying per comment.
        role_cache = {}
        for comment in comments:
            try:
                task = tasks_service.get_task(
                    comment["object_id"], relations=True
                )
                project_id = task["project_id"]
                if project_id not in role_cache:
                    role_cache[project_id] = (
                        permissions_service.get_project_role(
                            person["id"], project_id
                        )
                    )
                if (
                    role_cache[project_id] == "supervisor"
                    and (
                        len(person["departments"]) == 0
                        or task_types_service.get_task_type(
                            task["task_type_id"]
                        )["department_id"]
                        in person["departments"]
                    )
                ) or person["id"] in task["assignees"]:
                    allowed_comments.append(comment)
            except permissions.PermissionDenied:
                pass
            except KeyError:
                pass
        return allowed_comments


def _is_client_thread(comment, task_id):
    """
    Tell whether the client sees the thread of given comment: flagged for
    them, or written by a client (the guests of a share link are clients).
    """
    if comment.get("for_client"):
        return True
    if not comment.get("person_id"):
        return False
    task = tasks_service.get_task(task_id)
    return (
        permissions_service.get_project_role(
            comment["person_id"], task["project_id"]
        )
        == "client"
    )


class ReplyCommentResource(MethodView, ArgsMixin):

    @jwt_required()
    @swag_from(SPECS["ReplyCommentResource_post"])
    def post(self, task_id, comment_id):
        """
        Reply to comment
        """
        comment = comments_service.get_comment(comment_id)
        if comment["object_id"] != task_id:
            raise permissions.PermissionDenied()
        # The author answers their own thread, as long as they are still on
        # the project.
        permissions_service.check_task_access(task_id)
        current_user = persons_service.get_current_user()
        if comment["person_id"] != current_user["id"]:
            try:
                permissions_service.check_task_action_access(task_id)
            except permissions.PermissionDenied:
                # A reply carries no status and no preview, so answering is
                # all a mention has to grant here.
                permissions_service.check_task_mention_access(task_id)
            if permissions.has_client_permissions():
                author = persons_service.get_person(comment["person_id"])
                task = tasks_service.get_task(task_id)
                if (
                    current_user["studio_id"] != author["studio_id"]
                    and permissions_service.get_project_role(
                        author["id"], task["project_id"]
                    )
                    == "client"
                ):
                    raise permissions.PermissionDenied()
        else:
            # The author goes through no access check: resolve their role
            # on the production for the rule below.
            permissions_service.resolve_project_role(
                tasks_service.get_task(task_id)["project_id"]
            )
        if (
            not permissions.has_manager_permissions()
            and not permissions.has_client_permissions()
            and _is_client_thread(comment, task_id)
        ):
            # The client sees who answers there, by name and avatar: the
            # production managers answer for the studio.
            raise permissions.PermissionDenied()

        body = validation.validate_request_body(CommentReplySchema)
        files = request.files
        return comments_service.reply_comment(
            comment_id, body.text, files=files
        )


class DeleteReplyCommentResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["DeleteReplyCommentResource_delete"])
    def delete(self, task_id, comment_id, reply_id):
        """
        Delete comment reply
        """
        comments_service.get_task_comment(task_id, comment_id)
        permissions_service.check_task_access(task_id)
        reply = comments_service.get_reply(comment_id, reply_id)
        current_user = persons_service.get_current_user()
        if reply["person_id"] != current_user["id"]:
            permissions.check_admin_permissions()
        return comments_service.delete_reply(comment_id, reply_id)


class ProjectAttachmentFiles(MethodView):

    @jwt_required()
    @swag_from(SPECS["ProjectAttachmentFiles_get"])
    def get(self, project_id):
        """
        Get project attachment files
        """
        permissions.check_admin_permissions()
        return attachment_files_service.get_all_attachment_files_for_project(
            project_id
        )


class TaskAttachmentFiles(MethodView):

    @jwt_required()
    @swag_from(SPECS["TaskAttachmentFiles_get"])
    def get(self, task_id):
        """
        Get task attachment files
        """
        permissions.check_admin_permissions()
        return attachment_files_service.get_all_attachment_files_for_task(
            task_id
        )


class MoveCommentResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["MoveCommentResource_post"])
    def post(self, task_id, comment_id):
        """
        Move a comment to another task of the same entity
        """
        permissions.check_manager_permissions()
        body = validation.validate_request_body(MoveCommentSchema)
        permissions_service.check_task_access(task_id)
        permissions_service.check_task_access(body.target_task_id)
        comment = comments_service.get_comment(comment_id)
        if str(comment["object_id"]) != str(task_id):
            raise WrongParameterException(
                "Comment does not belong to the given task."
            )
        return comments_service.move_comment_to_task(
            comment_id, body.target_task_id
        )


class CopyClientCommentsResource(MethodView):

    @jwt_required()
    @swag_from(SPECS["CopyClientCommentsResource_post"])
    def post(self, project_id):
        """
        Copy the last client comment of each given task
        """
        body = validation.validate_request_body(CopyClientCommentsSchema)
        permissions_service.check_manager_project_access(project_id)
        person = persons_service.get_current_user()
        return (
            comments_service.copy_last_client_comments(
                project_id,
                [str(task_id) for task_id in body.task_ids],
                person["id"],
                body.prefix,
            ),
            201,
        )
