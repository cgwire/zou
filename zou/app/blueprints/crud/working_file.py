from zou.app.blueprints.crud.base import BaseModelsResource, BaseModelResource

from zou.app.models.entity import Entity
from zou.app.models.project import Project
from zou.app.models.working_file import WorkingFile
from zou.app.services import user_service, tasks_service, files_service
from zou.app.utils import permissions


class WorkingFilesResource(BaseModelsResource):
    def __init__(self):
        BaseModelsResource.__init__(self, WorkingFile)

    def check_read_permissions(self):
        """
        Overriding so that people without admin credentials can still access
        this resource.
        """
        user_service.block_access_to_vendor()
        return True

    def add_project_permission_filter(self, query):
        """
        Filtering to keep only the files from projects available to the user's
        team. Allows projects that are no longer open.
        """
        if permissions.has_admin_permissions():
            return query
        else:
            query = (
                query.join(Entity, WorkingFile.entity_id == Entity.id)
                .join(Project)
                .filter(user_service.build_team_filter())
            )
            return query


class WorkingFileResource(BaseModelResource):
    def __init__(self):
        BaseModelResource.__init__(self, WorkingFile)

    def check_read_permissions(self, instance):
        working_file = files_service.get_working_file(instance["id"])
        task = tasks_service.get_task(working_file["task_id"])
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        return True

    def check_update_permissions(self, instance, data):
        working_file = files_service.get_working_file(instance["id"])
        task = tasks_service.get_task(working_file["task_id"])
        user_service.check_project_access(task["project_id"])
        user_service.check_entity_access(task["entity_id"])
        return True
