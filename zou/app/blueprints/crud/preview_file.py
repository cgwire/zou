from flasgger import swag_from
from flask import current_app
from flask_jwt_extended import jwt_required

from sqlalchemy.exc import IntegrityError, StatementError

from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task
from zou.app.models.project import Project
from zou.app.models.project_status import ProjectStatus
from zou.app.services import (
    permissions_service,
    user_service,
    tasks_service,
    persons_service,
    projects_service,
)
from zou.app.utils import permissions

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource
from zou.app.services import deletion_service


class PreviewFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, PreviewFile)

    @jwt_required()
    @swag_from("openapi/PreviewFilesResource_get.yml")
    def get(self):
        """
        Get preview files
        """
        return super().get()

    @jwt_required()
    @swag_from("openapi/PreviewFilesResource_post.yml")
    def post(self):
        """
        Create preview file
        """
        return super().post()

    def add_project_permission_filter(self, query):
        if not permissions.has_admin_permissions():
            query = (
                query.join(Task)
                .join(Project)
                .join(
                    ProjectStatus,
                    Project.project_status_id == ProjectStatus.id,
                )
                .filter(projects_service.build_open_project_filter())
            )
            if permissions.has_vendor_permissions():
                query = query.filter(persons_service.build_assignee_filter())
            else:
                query = query.filter(
                    user_service.build_related_projects_filter()
                )

        return query

    def check_read_permissions(self, options=None):
        return True


class PreviewFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, PreviewFile)

    def check_read_permissions(self, preview_file):
        """
        If it's a vendor, check if the user is working on the task.
        If it's an artist, check if preview file belongs to user projects.
        """
        task = tasks_service.get_task(preview_file["task_id"])
        permissions_service.resolve_project_role(task["project_id"])
        if permissions.has_vendor_permissions():
            permissions_service.check_working_on_task(preview_file["task_id"])
        else:
            permissions_service.check_project_access(task["project_id"])
        return True

    @jwt_required()
    @swag_from("openapi/PreviewFileResource_get.yml")
    def get(self, instance_id):
        """
        Get preview file
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from("openapi/PreviewFileResource_put.yml")
    def put(self, instance_id):
        """
        Update preview file
        """
        return super().put(instance_id)

    def check_update_permissions(self, preview_file, data):
        task = tasks_service.get_task(preview_file["task_id"])
        permissions_service.check_project_access(task["project_id"])
        if not permissions.has_manager_permissions():
            try:
                permissions_service.check_working_on_task(
                    preview_file["task_id"]
                )
            except permissions.PermissionDenied:
                # Supervisors validate the previews of their department.
                permissions_service.check_supervisor_project_task_type_access(
                    task["project_id"], task["task_type_id"]
                )
        return True

    def pre_update(self, instance_dict, data):
        """
        Check revision uniqueness before updating a preview file.
        Only applies to main previews (position 1).
        When updating a main preview's revision, all extra previews
        with the same revision are updated too.
        """
        if "revision" in data and instance_dict.get("position") == 1:
            new_revision = data["revision"]
            current_revision = instance_dict.get("revision")
            if new_revision != current_revision:
                tasks_service.check_revision_is_unique_for_task(
                    instance_dict["task_id"],
                    new_revision,
                    exclude_preview_id=instance_dict["id"],
                )
                # Update all extra previews with the same revision
                PreviewFile.query.filter_by(
                    task_id=instance_dict["task_id"],
                    revision=current_revision,
                ).filter(PreviewFile.id != instance_dict["id"]).update(
                    {"revision": new_revision}
                )
        return instance_dict

    def check_delete_permissions(self, preview_file):
        task = tasks_service.get_task(preview_file["task_id"])
        permissions_service.check_manager_project_access(task["project_id"])
        return True

    @jwt_required()
    @swag_from("openapi/PreviewFileResource_delete.yml")
    def delete(self, instance_id):
        """
        Delete preview file
        """
        instance = self.get_model_or_404(instance_id)

        try:
            instance_dict = instance.serialize()
            self.check_delete_permissions(instance_dict)
            self.pre_delete(instance_dict)
            deletion_service.remove_preview_file(
                instance, force=self.get_force()
            )
            self.emit_delete_event(instance_dict)
            self.post_delete(instance_dict)

        except IntegrityError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        return "", 204
