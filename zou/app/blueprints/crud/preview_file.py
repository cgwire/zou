from flask import current_app
from flask_jwt_extended import jwt_required
from sqlalchemy.exc import IntegrityError, StatementError

from zou.app.blueprints.crud.base import (
    BaseModelResource,
    BaseModelsResource,
    build_db_error_message,
)
from zou.app.exceptions import WrongParameterException
from zou.app.models.preview_file import PreviewFile
from zou.app.services import (
    deletion_service,
    files_service,
    permissions_service,
    persons_service,
    tasks_service,
    user_service,
)
from zou.app.utils import fields, permissions
from zou.app.utils.openapi import load_specs, swag_from

SPECS = load_specs(__file__, "openapi/preview_file.yml")


class PreviewFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, PreviewFile)

    @jwt_required()
    @swag_from(SPECS["PreviewFilesResource_get"])
    def get(self):
        """
        Get preview files
        """
        return super().get()

    @jwt_required()
    @swag_from(SPECS["PreviewFilesResource_post"])
    def post(self):
        """
        Create preview file
        """
        return super().post()

    def apply_filters(self, query, options):
        # A preview file has no project_id column. Thus the generic filters
        # ignore the parameter and answer for all productions. Limit the rows
        # to that project through their task. Use a subquery, not a join,
        # because the permission filter already joins the task table.
        query = super().apply_filters(query, options)
        if "project_id" in options:
            if not fields.is_valid_id(options["project_id"]):
                raise WrongParameterException("Invalid project_id.")
            query = files_service.filter_preview_files_by_project(
                query, options["project_id"]
            )
        return query

    def add_project_permission_filter(self, query):
        if not permissions.has_admin_permissions():
            if permissions.has_vendor_permissions():
                access_filter = persons_service.build_assignee_filter()
            else:
                access_filter = user_service.build_related_projects_filter()
            query = files_service.filter_preview_files_by_open_projects(
                query, access_filter
            )
        return query

    def check_read_permissions(self, options=None):
        return True


class PreviewFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, PreviewFile)
        # The update check reads the project from the stored task.
        self.protected_fields.append("task_id")

    def check_read_permissions(self, preview_file):
        """
        Make sure that the preview file is in a project of the user. A vendor
        must also work on its task.
        """
        task = tasks_service.get_task(preview_file["task_id"])
        permissions_service.check_project_access(task["project_id"])
        if permissions.has_vendor_permissions():
            permissions_service.check_working_on_task(preview_file["task_id"])
        return True

    @jwt_required()
    @swag_from(SPECS["PreviewFileResource_get"])
    def get(self, instance_id):
        """
        Get preview file
        """
        return super().get(instance_id)

    @jwt_required()
    @swag_from(SPECS["PreviewFileResource_put"])
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
        Make sure that the revision is unique before the update of a preview
        file. This applies only to main previews (position 1). When the update
        changes the revision of a main preview, it also updates all the extra
        previews with the same revision.
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
                files_service.update_extra_preview_revisions_no_commit(
                    instance_dict["task_id"],
                    current_revision,
                    new_revision,
                    instance_dict["id"],
                )
        return instance_dict

    def check_delete_permissions(self, preview_file):
        task = tasks_service.get_task(preview_file["task_id"])
        permissions_service.check_manager_project_access(task["project_id"])
        return True

    @jwt_required()
    @swag_from(SPECS["PreviewFileResource_delete"])
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

        except (IntegrityError, StatementError) as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": build_db_error_message(exception)}, 400

        return "", 204
