from flask import current_app
from flask_jwt_extended import jwt_required

from sqlalchemy.exc import IntegrityError, StatementError

from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task
from zou.app.models.project import Project
from zou.app.services import (
    user_service,
    tasks_service,
)
from zou.app.utils import permissions

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource
from zou.app.services import deletion_service


class PreviewFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, PreviewFile)

    def add_project_permission_filter(self, query):
        if permissions.has_vendor_permissions():
            query = (
                query.join(Task)
                .filter(user_service.build_assignee_filter())
                .filter(user_service.build_open_project_filter())
            )
        elif not permissions.has_admin_permissions():
            query = (
                query.join(Task)
                .join(Project)
                .filter(user_service.build_related_projects_filter())
                .filter(user_service.build_open_project_filter())
            )

        return query

    def check_read_permissions(self):
        return True


class PreviewFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, PreviewFile)

    def check_read_permissions(self, preview_file):
        """
        If it's a vendor, check if the user is working on the task.
        If it's an artist, check if preview file belongs to user projects.
        """
        if permissions.has_vendor_permissions():
            user_service.check_working_on_task(preview_file["task_id"])
        else:
            task = tasks_service.get_task(preview_file["task_id"])
            user_service.check_project_access(task["project_id"])
        return True

    def check_update_permissions(self, preview_file, data):
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_project_access(task["project_id"])
        if not permissions.has_manager_permissions():
            user_service.check_working_on_task(task["entity_id"])
        return True

    def check_delete_permissions(self, preview_file):
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_manager_project_access(task["project_id"])
        return True

    @jwt_required()
    def delete(self, instance_id):
        """
        Delete a preview file corresponding at given ID and retuns
        a 204 status code.
        ---
        tags:
          - Crud
        parameters:
          - in: path
            name: instance_id
            required: True
            type: string
            format: UUID
            x-example: a24a6ea4-ce75-4665-a070-57453082c25
        responses:
            204:
                description: Model deleted
            400:
                description: Statement or integrity error
            404:
                description: Instance non-existant
        """
        instance = self.get_model_or_404(instance_id)

        try:
            instance_dict = instance.serialize()
            self.check_delete_permissions(instance_dict)
            self.pre_delete(instance_dict)
            deletion_service.remove_preview_file(instance)
            self.emit_delete_event(instance_dict)
            self.post_delete(instance_dict)

        except IntegrityError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        except StatementError as exception:
            current_app.logger.error(str(exception), exc_info=1)
            return {"message": str(exception)}, 400

        return "", 204
