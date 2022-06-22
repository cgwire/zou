from flask_jwt_extended import jwt_required
from flask import current_app

from sqlalchemy.exc import StatementError

from zou.app.models.comment import Comment
from zou.app.models.attachment_file import AttachmentFile

from zou.app.services import (
    comments_service,
    deletion_service,
    notifications_service,
    persons_service,
    projects_service,
    tasks_service,
    user_service,
)
from zou.app.utils import events, permissions

from .base import BaseModelResource, BaseModelsResource

from zou.app.services.exception import CommentNotFoundException


class CommentsResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, Comment)


class CommentResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, Comment)

    @jwt_required
    def get(self, instance_id):
        """
        Retrieve a model corresponding at given ID and return it as a JSON
        object.
        """
        try:
            instance = tasks_service.get_comment_with_relations(instance_id)
            self.check_read_permissions(instance)
            result = self.clean_get_result(instance)

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except ValueError:
            raise CommentNotFoundException

        return result, 200

    def clean_get_result(self, result):
        if permissions.has_client_permissions():
            person = persons_service.get_person(result["person_id"])
            if person["role"] != "client":
                result["text"] = ""
                result["attachment_files"] = []
                result["checklist"] = []
        attachment_files = []
        if (
            "attachment_files" in result
            and len(result["attachment_files"]) > 0
        ):
            for attachment_file_id in result["attachment_files"]:
                attachment_file = AttachmentFile.get(attachment_file_id)
                attachment_files.append(attachment_file.present())
            result["attachment_files"] = attachment_files
        return result

    def pre_update(self, instance_dict, data):
        self.task_status_change = False
        if instance_dict["task_status_id"] != data.get("task_status_id", None):
            self.task_status_change = True
            self.previous_task_status_id = instance_dict["task_status_id"]
        return data

    def post_update(self, instance_dict):
        comment = comments_service.reset_mentions(instance_dict)
        if self.task_status_change:
            task_id = comment["object_id"]
            task = tasks_service.reset_task_data(task_id)
            events.emit(
                "task:status-changed",
                {
                    "task_id": task_id,
                    "new_task_status_id": comment["task_status_id"],
                    "previous_task_status_id": self.previous_task_status_id,
                    "person_id": comment["person_id"],
                },
                project_id=task["project_id"],
            )

        tasks_service.clear_comment_cache(comment["id"])
        notifications_service.reset_notifications_for_mentions(comment)
        return comment

    def check_read_permissions(self, instance):
        return user_service.check_comment_access(instance["id"])

    def check_update_permissions(self, instance, data):
        if permissions.has_admin_permissions():
            return True
        else:
            comment = self.get_model_or_404(instance["id"])
            current_user = persons_service.get_current_user()
            return current_user["id"] == str(comment.person_id)

    def pre_delete(self, comment):
        task = tasks_service.get_task(comment["object_id"])
        self.previous_task_status_id = task["task_status_id"]
        return comment

    def post_delete(self, comment):
        task = tasks_service.get_task(comment["object_id"])
        self.new_task_status_id = task["task_status_id"]
        if self.previous_task_status_id != self.new_task_status_id:
            events.emit(
                "task:status-changed",
                {
                    "task_id": task["id"],
                    "new_task_status_id": self.new_task_status_id,
                    "previous_task_status_id": self.previous_task_status_id,
                    "person_id": comment["person_id"],
                },
                project_id=task["project_id"],
            )
        return comment

    @jwt_required
    def delete(self, instance_id):
        """
        Delete a comment corresponding at given ID.
        """
        comment = tasks_service.get_comment(instance_id)
        task = tasks_service.get_task(comment["object_id"])
        if permissions.has_manager_permissions():
            user_service.check_project_access(task["project_id"])
        else:
            user_service.check_person_access(comment["person_id"])
        self.pre_delete(comment)
        deletion_service.remove_comment(comment["id"])
        tasks_service.reset_task_data(comment["object_id"])
        tasks_service.clear_comment_cache(comment["id"])
        self.post_delete(comment)
        return "", 204
