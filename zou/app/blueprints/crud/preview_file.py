from zou.app.models.preview_file import PreviewFile
from zou.app.services import (
    user_service,
    persons_service,
    tasks_service,
)
from zou.app.utils import permissions

from .base import BaseModelsResource, BaseModelResource


class PreviewFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, PreviewFile)

    def all_entries(self, query=None, relations=False):
        """
        If the user has at least manager permissions, return all previews
        If he's a vendor, return only previews for the tasks he's assigned to
        """
        if query is None:
            query = self.model.query

        projects = user_service.related_projects()
        all_previews = query.all()
        previews = []

        if permissions.has_manager_permissions():
            previews = all_previews

        elif permissions.has_vendor_permissions() or \
                permissions.has_client_permissions():
            current_user = persons_service.get_current_user()
            tasks = tasks_service.get_person_tasks(current_user["id"], projects)
            task_ids = [task["id"] for task in tasks]
            for preview in all_previews:
                if str(preview.task_id) in task_ids:
                    previews.append(preview)

        else:
            project_ids = [project["id"] for project in projects]
            for preview in all_previews:
                task = tasks_service.get_task(preview.task_id)
                if task["project_id"] in project_ids:
                    previews.append(preview)

        return self.model.serialize_list(previews, relations=relations)

    def check_read_permissions(self):
        return True


class PreviewFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, PreviewFile)

    def check_read_permissions(self, preview_file):
        """
        If it's a vendor, check if the user is working on the task
        If it's an artist, check if preview file belongs to user projects
        """
        projects = user_service.related_projects()
        if permissions.has_manager_permissions():
            pass
        elif permissions.has_vendor_permissions() or \
                permissions.has_client_permissions():
            current_user = persons_service.get_current_user()
            tasks = tasks_service.get_person_tasks(current_user["id"], projects)
            task_ids = [task["id"] for task in tasks]
            if not str(preview_file["task_id"]) in task_ids:
                raise permissions.PermissionDenied
        else:
            project_ids = [project["id"] for project in projects]
            task = tasks_service.get_task(preview_file["task_id"])
            if not task["project_id"] in project_ids:
                raise permissions.PermissionDenied
        return True

    def check_update_permissions(self, preview_file, data):
        task = tasks_service.get_task(preview_file["task_id"])
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        return True
