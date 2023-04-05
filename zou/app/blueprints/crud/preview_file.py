from zou.app.models.preview_file import PreviewFile
from zou.app.models.task import Task
from zou.app.models.project import Project
from zou.app.services import (
    user_service,
    tasks_service,
)
from zou.app.utils import permissions

from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource


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
